"""Local persistent workspaces and transactional versions."""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from decimal import Decimal

from .engine import extract_claims, facts_index, inspect, check, number, unmatched_spans
from .graph import Derivations, compute, impact
from .office import read_facts, read_document, digest, apply_document, update_workbook


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def folder(self, wid):
        if not re.fullmatch(r'[a-f0-9]{32}', wid):
            raise ValueError('无效的项目ID')
        return self.root / wid

    def read(self, wid):
        path = self.folder(wid) / 'state.json'
        if not path.is_file():
            raise FileNotFoundError('项目不存在')
        return json.loads(path.read_text(encoding='utf-8'))

    def write(self, ws):
        folder = self.folder(ws['id'])
        tmp = folder / 'state.tmp'
        tmp.write_text(json.dumps(ws, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        os.replace(tmp, folder / 'state.json')

    def list(self):
        out = []
        for path in self.root.glob('*/state.json'):
            try:
                ws = json.loads(path.read_text(encoding='utf-8'))
                out.append({k: ws[k] for k in ('id', 'name', 'created_at', 'revision')})
            except (ValueError, KeyError):
                continue
        return sorted(out, key=lambda x: x['created_at'], reverse=True)

    def scan(self, ws, folder, old_claims=()):
        source = next(d for d in ws['documents'] if d['kind'] == 'xlsx')
        base = read_facts(folder / source['stored_name'], source['id'])
        ws['source_facts'] = base
        # 上一轮的派生值必须先取出来：build_facts 会覆盖 graph_values，
        # 而判断"哪个派生值真的变了"正需要它。
        previous_values = ws.get('graph_values')
        ws['facts'] = self.build_facts(base, ws, previous=previous_values)
        claims, blocks, old = [], [], {c['id']: c for c in old_claims}
        # 索引在这里构造一次并全程复用：否则每个正文块都要重新构造一次。
        index = facts_index(ws['facts'])
        for d in ws['documents']:
            d['sha256'] = digest(folder / d['stored_name'])
            if d['kind'] == 'xlsx':
                continue
            bs, cs, warnings = read_document(folder / d['stored_name'], d['id'], ws['facts'])
            d['warnings'] = warnings
            blocks.extend(bs)
            for block in bs:
                cs.extend(extract_claims(block, ws['facts'], index=index))
            for c in cs:
                previous = old.get(c['id'])
                if previous:
                    # Keep only reviewed dependencies which still exist in the current source.
                    available = {f['id'] for f in ws['facts']}
                    if all(r in available for r in previous['refs']):
                        c['refs'] = previous['refs']
                        c['confirmed'] = previous['confirmed']
                        c['extraction'] = previous['extraction']
                claims.append(c)
        ws['claims'], ws['blocks'] = claims, blocks
        # 级联标记只对触发它的那一次变更有效，扫完即清，避免后续操作误报。
        ws['graph_changed'] = []
        return ws

    # ---- 事实依赖图 --------------------------------------------------------
    def derivations_of(self, ws):
        return Derivations(ws.get('derivations') or [])

    def build_facts(self, base, ws, previous=None, overrides=None):
        """在基础事实之上按拓扑序算出派生事实，返回合并后的完整事实表。

        论证与图表都可以引用派生事实（如「成本占比」「利润」），
        因此合并结果才是 engine.check() 应该看到的事实集合。
        """
        derivations = self.derivations_of(ws)
        if not derivations.records:
            ws['graph'] = {'derived': [], 'errors': {}, 'details': {}, 'affected': [],
                           'changed': [], 'radius': 0.0, 'cycles': []}
            ws['graph_values'] = {}
            return list(base)
        outcome = compute(base, derivations, changed=ws.get('graph_changed') or [],
                          overrides=overrides, previous=previous)
        ws['graph'] = {
            # 派生值是 Decimal，落盘前必须转 float，否则 json.dumps 会拒绝序列化。
            'derived': [{'id': f['id'], 'op': f['op'], 'inputs': f['inputs'], 'unit': f['unit'],
                         'metric': f['metric'], 'value': float(f['value'])} for f in outcome['facts']
                        if f.get('derived')],
            'errors': outcome['errors'], 'details': outcome['details'],
            'affected': outcome['affected'], 'changed': outcome['changed'],
            'radius': round(outcome['radius'], 4),
            'cycles': [c for c in derivations.cycles],
        }
        # 保存本轮值供下一次变更做对比：没有它就无法判断派生值究竟有没有变。
        ws['graph_values'] = {k: (float(v) if isinstance(v, Decimal) else v)
                              for k, v in outcome['values'].items()}
        # 事实表里的派生值同样要给下游 JSON（HTTP 响应）用，统一降为 float。
        return [dict(f, value=float(f['value'])) if f.get('derived') and f.get('value') is not None else f
                for f in outcome['facts']]

    def save_derivations(self, ws, records):
        """替换派生定义前先做完整校验，非法定义不写盘。"""
        derivations = Derivations(records)
        base_ids = {f['id'] for f in ws.get('source_facts') or ws['facts']}
        problems = derivations.validate(base_ids)
        if problems:
            raise ValueError('；'.join(problems))
        ws['derivations'] = derivations.records
        return derivations

    def graph_summary(self, ws):
        graph = ws.get('graph') or {}
        return {'derived': len(graph.get('derived') or []),
                'errors': len(graph.get('errors') or {}),
                'affected': len(graph.get('affected') or []),
                'radius': graph.get('radius', 0.0),
                'cycles': len(graph.get('cycles') or [])}

    def create(self, name, paths, demo=False):
        with self.lock:
            if len(paths) < 2 or len(paths) > 10 or sum(Path(p).suffix.lower() == '.xlsx' for p in paths) != 1:
                raise ValueError('请选择一份Excel数据源和至少一份Word/PPT成果，最多10份文件')
            wid = uuid.uuid4().hex
            folder = self.folder(wid)
            current = folder / 'v0'
            current.mkdir(parents=True)
            ws = {'id': wid, 'name': name.strip()[:100] or '未命名项目', 'created_at': now(),
                  'revision': 0, 'generation': 'v0', 'demo': demo, 'documents': [],
                  'derivations': [], 'graph': None, 'graph_changed': [],
                  'history': [], 'audit': [], 'last_repair': None}
            try:
                for i, path in enumerate(paths):
                    path = Path(path)
                    fid = uuid.uuid4().hex[:16]
                    stored = f'{fid}{path.suffix.lower()}'
                    shutil.copyfile(path, current / stored)
                    ws['documents'].append({'id': fid, 'name': path.name, 'kind': path.suffix.lower()[1:],
                                            'stored_name': stored, 'warnings': []})
                self.scan(ws, current)
                if not ws['blocks']:
                    raise ValueError('成果文件没有可处理的正文或幻灯片文字')
                ws['audit'].append({'time': now(), 'event': '导入文件', 'detail': f'{len(paths)}份文件；关联尚待人工确认'})
                self.write(ws)
                return self.public(ws)
            except Exception:
                shutil.rmtree(folder)
                raise

    def public(self, ws):
        result = copy.deepcopy(ws)
        result['checks'], result['summary'] = inspect(ws)
        segments = unmatched_spans(ws['blocks'], ws['claims'])
        result['unmatched_segments'] = segments
        result['summary']['unmatched_segments'] = len(segments)
        # Keep the original block count for clients that used the first API.
        result['summary']['unmatched_blocks'] = sum(not any(c['file_id'] == b['file_id'] and c['location'] == b['location'] for c in ws['claims']) for b in ws['blocks'])
        # 派生事实、依赖图与实际使用的值是过程数据，不重复下发给前端。
        result.pop('source_facts', None)
        result.pop('graph_changed', None)
        result['summary'].update(self.graph_summary(ws))
        for d in result['documents']:
            d.pop('stored_name', None)
            d['download_url'] = f'/api/projects/{ws["id"]}/files/{d["id"]}'
        return result

    def verify(self, ws, revision):
        if ws['revision'] != revision:
            raise ValueError('项目已在其他窗口更新，请刷新后重试')
        folder = self.folder(ws['id']) / ws['generation']
        for d in ws['documents']:
            if digest(folder / d['stored_name']) != d['sha256']:
                raise ValueError('源文件在分析后发生变化，已停止操作，请重新导入')

    def confirm(self, wid, revision, links):
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, revision)
            claims = {c['id']: c for c in ws['claims']}
            facts = {f['id'] for f in ws['facts']}
            if not links:
                raise ValueError('请选择至少一条关联')
            for item in links:
                cid, refs = item['claim_id'], item['refs']
                if cid not in claims or any(r not in facts for r in refs) or not refs:
                    raise ValueError('关联包含无效事实或论断')
                candidate = copy.deepcopy(claims[cid])
                candidate['refs'] = list(dict.fromkeys(refs))
                checked = check(candidate, ws['facts'])
                if checked['status'] == 'unverifiable':
                    raise ValueError('无法确认此关联：' + checked['reason'])
                claims[cid]['refs'] = candidate['refs']
                claims[cid]['confirmed'] = True
                claims[cid]['issue'] = ''
            ws['revision'] += 1
            ws['audit'].append({'time': now(), 'event': '确认来源', 'detail': f'确认{len(links)}项关联；排名结论限于选定比较集合'})
            self.write(ws)
            return self.public(ws)

    def change(self, wid, revision, values):
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, revision)
            # 只允许改基础事实：派生事实由表达式决定，直接写入会与其定义矛盾。
            base = ws.get('source_facts') or ws['facts']
            facts = {f['id']: f for f in base}
            if not values or any(i not in facts for i in values):
                raise ValueError('没有有效的事实更新；派生事实由表达式决定，不能直接修改')
            changes = {i: float(number(v)) for i, v in values.items() if float(number(v)) != facts[i]['value']}
            if not changes:
                raise ValueError('数值没有变化')
            previous = copy.deepcopy(ws)
            root = self.folder(wid)
            source = next(d for d in ws['documents'] if d['kind'] == 'xlsx')
            with self.apply_generation(ws, previous) as target:
                update_workbook(root / ws['generation'] / source['stored_name'],
                                target / source['stored_name'], base, changes)
                ws['graph_changed'] = sorted(changes)
                self.scan(ws, target, ws['claims'])
                affected = self.last_impact(ws, sorted(changes))
                ws['history'].append({'revision': previous['revision'], 'generation': previous['generation'],
                                      'action': '数据变更',
                                      'changes': [{'id': i, 'before': facts[i]['value'], 'after': v}
                                                  for i, v in changes.items()], 'time': now()})
                ws['revision'] += 1
                ws['last_repair'] = None
                ws['audit'].append({'time': now(), 'event': '数据变更',
                                    'detail': '；'.join(f'{i}: {facts[i]["value"]} → {v}'
                                                        for i, v in changes.items())})
            result = self.public(ws)
            result['cascade'] = affected
            return result

    def last_impact(self, ws, changed_ids):
        """本次变更的级联结果：派生事实变化、直接与间接受影响的论断。"""
        derivations = self.derivations_of(ws)
        grouped = impact(derivations, ws['claims'], changed_ids) if derivations.records else {
            'direct': [c['id'] for c in ws['claims'] if set(c['refs']) & set(changed_ids)],
            'indirect': [], 'affected_facts': [], 'total': 0}
        graph = ws.get('graph') or {}
        return {'changed_facts': changed_ids,
                'changed_derived': graph.get('changed') or [],
                'affected_facts': grouped['affected_facts'],
                'direct_claims': grouped['direct'],
                'indirect_claims': grouped['indirect'],
                'radius': graph.get('radius', 0.0)}

    def source_update(self, ws, revision, path):
        """Validate an edited workbook for both preview and transactional import."""
        self.verify(ws, revision)
        source = next(d for d in ws['documents'] if d['kind'] == 'xlsx')
        incoming = read_facts(path, source['id'])
        old = {f['id']: f for f in ws['facts']}
        new = {f['id']: f for f in incoming}
        if old.keys() != new.keys():
            raise ValueError('更新表的事实ID集合发生变化。此入口只更新原有事实；增删事实请重新建立项目并确认关联')
        fields = ('subject', 'metric', 'period', 'unit', 'scope')
        if any(old[i][k] != new[i][k] for i in old for k in fields):
            raise ValueError('主体、指标、期间、单位或统计口径发生变化，请重新建立项目并确认关联')
        changes = [{'id': i, 'before': old[i]['value'], 'after': new[i]['value']}
                   for i in old if old[i]['value'] != new[i]['value']]
        if not changes:
            raise ValueError('Excel 中的事实数值没有变化，请确认已保存并选择了更新后的文件')
        return source, incoming, changes

    def preview_source(self, wid, revision, path):
        """Check existing dependent claims against incoming facts without writing state."""
        with self.lock:
            ws = self.read(wid)
            _, incoming, changes = self.source_update(ws, revision, path)
            changed = {c['id'] for c in changes}
            # 派生事实必须在同一事务性内存里联动重算：只比基础事实会漏掉
            # 「改成本 → 成本占比失效 → 引用占比的句子失效」这类间接影响。
            graph_before = copy.deepcopy(ws.get('graph'))
            values_before = copy.deepcopy(ws.get('graph_values'))
            after_facts = self.build_facts(incoming, ws, previous=values_before,
                                           overrides={c['id']: c['after'] for c in changes})
            graph_state = copy.deepcopy(ws.get('graph'))
            ws['graph'] = graph_before
            ws['graph_values'] = values_before
            derivations = self.derivations_of(ws)
            grouped = impact(derivations, ws['claims'], sorted(changed)) if derivations.records else {
                'direct': [c['id'] for c in ws['claims'] if changed.intersection(c['refs'])],
                'indirect': [], 'affected_facts': []}
            relevant = set(grouped['direct']) | set(grouped['indirect'])
            affected = []
            summary = {'changed_facts': len(changes), 'affected_claims': 0,
                       'consistent': 0, 'inconsistent': 0, 'unverifiable': 0, 'repairable': 0}
            for claim in ws['claims']:
                if claim['id'] not in relevant:
                    continue
                before = check(claim, ws['facts'])
                after = check(claim, after_facts)
                affected.append({'claim_id': claim['id'],
                                 'cascade': 'indirect' if claim['id'] in set(grouped['indirect']) else 'direct',
                                 'before': before, 'after': after,
                                 # Keep the compact fields for API consumers that
                                 # only need a status summary.
                                 'before_status': before['status'], 'after_status': after['status'],
                                 'expected': after['expected'], 'reason': after['reason']})
                summary[after['status']] += 1
                summary['repairable'] += int(claim['confirmed'] and after['status'] == 'inconsistent')
            summary['affected_claims'] = len(affected)
            return {'revision': ws['revision'], 'changes': changes, 'affected': affected, 'summary': summary,
                    'cascade': {'changed_facts': sorted(changed),
                                'changed_derived': graph_state.get('changed') or [],
                                'affected_facts': grouped['affected_facts'],
                                'direct_claims': len(grouped['direct']),
                                'indirect_claims': len(grouped['indirect']),
                                'radius': graph_state.get('radius', 0.0)}}

    def import_source(self, wid, revision, path):
        """Import an externally edited workbook without silently reusing changed meanings."""
        with self.lock:
            ws = self.read(wid)
            source, _, changes = self.source_update(ws, revision, path)
            previous = copy.deepcopy(ws)
            changed_ids = sorted(c['id'] for c in changes)
            with self.apply_generation(ws, previous) as target:
                shutil.copyfile(path, target / source['stored_name'])
                ws['graph_changed'] = changed_ids
                self.scan(ws, target, ws['claims'])
                cascade = self.last_impact(ws, changed_ids)
                ws['revision'] += 1
                ws['last_repair'] = None
                ws.pop('suggestions', None)
                ws['history'].append({'revision': previous['revision'], 'generation': previous['generation'],
                                      'action': '导入更新表', 'changes': changes, 'time': now()})
                ws['audit'].append({'time': now(), 'event': '导入更新表',
                                    'detail': '；'.join(f'{c["id"]}: {c["before"]} → {c["after"]}'
                                                        for c in changes)})
            result = self.public(ws)
            result['cascade'] = cascade
            return result

    # ---- 事务性文件写入 -----------------------------------------------------
    @contextmanager
    def apply_generation(self, ws, previous):
        """在文件副本上完成一次写入，成功才切换 generation。

        原先 change / import_source / repair 各自抄了一遍这段样板：复制目录、
        失败时删除、写 previous-state.json。抽成一处后三者的失败语义必然一致，
        不会出现"只在其中一个入口忘了清理"的情况。
        """
        root = self.folder(ws['id'])
        generation = 'v' + uuid.uuid4().hex[:12]
        target = root / generation
        shutil.copytree(root / ws['generation'], target)
        try:
            yield target
            ws['generation'] = generation
            (target / 'previous-state.json').write_text(
                json.dumps(previous, ensure_ascii=False), encoding='utf-8')
            self.write(ws)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise

    # ---- 派生事实定义的增删 -------------------------------------------------
    def _rescan_and_commit(self, ws, event, detail):
        """派生定义变化后在原目录上重扫并落盘：不产生新 generation。"""
        self.scan(ws, self.folder(ws['id']) / ws['generation'], ws['claims'])
        ws['revision'] += 1
        ws['last_repair'] = None
        ws['audit'].append({'time': now(), 'event': event, 'detail': detail})
        self.write(ws)
        return self.public(ws)

    def set_derivations(self, wid, revision, records):
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, revision)
            self.save_derivations(ws, records)
            return self._rescan_and_commit(ws, '定义派生事实',
                                           f'共{len(ws["derivations"])}项派生事实；引用完整性校验通过')

    def remove_derivation(self, wid, revision, rid):
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, revision)
            derivations = self.derivations_of(ws)
            derivations.remove(rid)
            ws['derivations'] = derivations.records
            return self._rescan_and_commit(ws, '删除派生事实', rid)

    def repair(self, wid, revision, ids):
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, revision)
            checks, _ = inspect(ws)
            checked = {c['claim_id']: c for c in checks}
            claims = {c['id']: c for c in ws['claims']}
            ids = list(dict.fromkeys(ids))
            if not ids or any(i not in claims for i in ids):
                raise ValueError('请选择有效的修改项')
            if any(not claims[i]['confirmed'] or checked[i]['status'] != 'inconsistent' for i in ids):
                raise ValueError('只可修复来源已确认且检查不一致的论断')
            previous = copy.deepcopy(ws)
            root = self.folder(wid)
            changes = [dict(claims[i], expected=checked[i]['expected']) for i in ids]
            with self.apply_generation(ws, previous) as target:
                for d in ws['documents']:
                    patches = [c for c in changes if c['file_id'] == d['id']]
                    if patches:
                        apply_document(root / ws['generation'] / d['stored_name'],
                                       target / d['stored_name'], patches, ws['facts'])
                old_blocks = {(b['file_id'], b['location']): b['text'] for b in ws['blocks']}
                expected_blocks = dict(old_blocks)
                for key, original in old_blocks.items():
                    edits = [c for c in changes if (c['file_id'], c['location']) == key and c['kind'] != 'chart']
                    for c in sorted(edits, key=lambda x: x['start'], reverse=True):
                        original = original[:c['start']] + c['expected'] + original[c['end']:]
                    expected_blocks[key] = original
                self.scan(ws, target, ws['claims'])
                new_blocks = {(b['file_id'], b['location']): b['text'] for b in ws['blocks']}
                if new_blocks != expected_blocks:
                    raise ValueError('导出复核失败：目标修改以外的正文发生变化，已撤销本次生成')
                new_checks = {c['id']: check(c, ws['facts']) for c in ws['claims']}
                if any(i not in new_checks or new_checks[i]['status'] != 'consistent' for i in ids):
                    raise ValueError('导出后的论断复核未通过，已撤销本次生成')
                ws['revision'] += 1
                ws['last_repair'] = {'time': now(), 'count': len(ids), 'verified': True,
                                     'unchanged_blocks_verified': sum(expected_blocks[k] == old_blocks[k]
                                                                      for k in old_blocks),
                                     'patches': [{'claim_id': c['id'], 'location': c['label'],
                                                  'before': c['original'], 'after': c['expected']}
                                                 for c in changes]}
                ws['history'].append({'revision': previous['revision'], 'generation': previous['generation'],
                                      'action': '修复文件', 'time': now()})
                ws['audit'].append({'time': now(), 'event': '修复并复核',
                                    'detail': f'{len(ids)}项；重新读取Office文件后验证通过，'
                                              '其他支持范围内的正文保持一致'})
            return self.public(ws)

    def undo(self, wid, revision):
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, revision)
            file = self.folder(wid) / ws['generation'] / 'previous-state.json'
            if not file.exists():
                raise ValueError('没有可以撤销的文件变更')
            old = json.loads(file.read_text(encoding='utf-8'))
            old['revision'] = ws['revision'] + 1
            old['audit'] = ws['audit'] + [{'time': now(), 'event': '撤销', 'detail': '恢复上一次文件变更之前的数据和成果'}]
            self.write(old)
            return self.public(old)

    def archive(self, wid):
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, ws['revision'])
            root = self.folder(wid)
            name = f'export-{ws["revision"]}.zip'
            with ZipFile(root / name, 'w', ZIP_DEFLATED) as z:
                for d in ws['documents']:
                    z.write(root / ws['generation'] / d['stored_name'], d['name'])
                report = self.public(ws)
                z.writestr('知链核验记录.json', json.dumps(report, ensure_ascii=False, indent=2))
                checks, summary = inspect(ws)
                lines = ['# 知链核验报告', '', f'项目：{ws["name"]}', f'版本：{ws["revision"]}', '',
                         f'已检查论断 {summary["claims"]}；一致 {summary["consistent"]}；不一致 {summary["inconsistent"]}；无法验证 {summary["unverifiable"]}。',
                         '本报告仅涵盖已识别、受支持的论断，不能作为整个文档正确性的保证。', '']
                for c, r in zip(ws['claims'], checks):
                    lines.extend([f'## {c["label"]}', c['original'], f'状态：{r["status"]}；来源已确认：{c["confirmed"]}', r['reason'], ''])
                z.writestr('核验报告.md', '\n'.join(lines))
            return root / name
