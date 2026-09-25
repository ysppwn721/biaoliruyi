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
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from .engine import extract_claims, facts_index, inspect, check, number, unmatched_spans
from .graph import Derivations, compute, impact
from .diagnose import diagnose
from .report import build_report
from .office import read_facts, read_document, read_images, digest, apply_document, update_workbook
from . import ocr


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
        # 基础事实与完整事实分开保存：Excel 只承载基础事实，派生事实由表达式
        # 定义，既不能被写回 Excel，也不能被直接改数值。
        base = read_facts(folder / source['stored_name'], source['id'])
        ws['source_facts'] = base
        previous_values = ws.get('graph_values')
        ws['facts'] = self.build_facts(base, ws, previous=previous_values)
        claims, blocks, old = [], [], {c['id']: c for c in old_claims}
        # 事实定位索引一次构造、全程复用，避免每个正文块重新构造。
        index = facts_index(ws['facts'])
        for d in ws['documents']:
            d['sha256'] = digest(folder / d['stored_name'])
            if d['kind'] == 'xlsx' or '.' + d['kind'] in ocr.IMAGE_EXTENSIONS:
                continue
            bs, cs, warnings = read_document(folder / d['stored_name'], d['id'], ws['facts'])
            d['warnings'] = warnings
            blocks.extend(bs)
            for block in bs:
                cs.extend(extract_claims(block, ws['facts'], index=index))
            for c in cs:
                previous = old.get(c['id'])
                if previous:
                    # 论断 ID 锚点记忆保留同位置的已确认来源；link_rules 仅为不同论断提供偏好。
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

        论断与图表都可以引用派生事实（如「利润」「成本占比」），
        因此合并结果才是 engine.check() 应该看到的完整事实集合。
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
        # 保存本轮值供下一次变更比对：没有它就无法判断派生值究竟有没有变。
        ws['graph_values'] = {k: (float(v) if isinstance(v, Decimal) else v)
                              for k, v in outcome['values'].items()}
        return [dict(f, value=float(f['value'])) if f.get('derived') and f.get('value') is not None else f
                for f in outcome['facts']]

    def save_derivations(self, ws, records):
        """替换派生定义前先完整校验，非法定义不写盘。"""
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

    def last_impact(self, ws, changed_ids):
        """本次变更的级联结果：真正变化的派生事实、直接影响与间接受影响的论断。"""
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

    def _rescan_and_commit(self, ws, event, detail):
        """派生定义变化后在原目录上重扫并落盘：不产生新 generation。"""
        self.scan(ws, self.folder(ws['id']) / ws['generation'], ws['claims'])
        ws['revision'] += 1
        ws['last_repair'] = None
        ws['audit'].append({'time': now(), 'event': event, 'detail': detail})
        self.write(ws)
        return self.public(ws)

    def create(self, name, paths, demo=False):
        with self.lock:
            if len(paths) < 2 or len(paths) > 10 or sum(Path(p).suffix.lower() == '.xlsx' for p in paths) != 1:
                raise ValueError('请选择一份Excel数据源和至少一份Word/PPT或图片文件，最多10份文件')
            wid = uuid.uuid4().hex
            folder = self.folder(wid)
            current = folder / 'v0'
            current.mkdir(parents=True)
            ws = {'id': wid, 'name': name.strip()[:100] or '未命名项目', 'created_at': now(),
                  'revision': 0, 'generation': 'v0', 'demo': demo, 'documents': [],
                  'history': [], 'audit': [], 'last_repair': None, 'link_rules': []}
            try:
                for i, path in enumerate(paths):
                    path = Path(path)
                    fid = uuid.uuid4().hex[:16]
                    stored = f'{fid}{path.suffix.lower()}'
                    shutil.copyfile(path, current / stored)
                    ws['documents'].append({'id': fid, 'name': path.name, 'kind': path.suffix.lower()[1:],
                                            'stored_name': stored, 'warnings': []})
                self.scan(ws, current)
                ws['images'], ws['ocr_blocks'], ws['ocr_claims'] = [], [], []
                for document in ws['documents']:
                    if document['kind'] == 'xlsx':
                        continue
                    ext = '.' + document['kind']
                    if ext in ocr.IMAGE_EXTENSIONS:
                        img_id = 'img' + uuid.uuid4().hex[:16]
                        mime = ocr.IMAGE_EXTENSIONS[ext]
                        stored = 'images/' + img_id + '.' + ocr.MIME_EXT.get(mime, 'bin')
                        path = current / stored
                        path.parent.mkdir(exist_ok=True)
                        shutil.copyfile(current / document['stored_name'], path)
                        ws['images'].append({'id': img_id, 'file_id': document['id'],
                                            'location': json.dumps(['image']), 'label': document['name'],
                                            'mime': mime, 'stored_name': stored, 'sha256': digest(path),
                                            'ocr_text': None, 'ocr_status': 'pending', 'ocr_error': None})
                    else:
                        images, warnings = read_images(current / document['stored_name'], document['id'])
                        document['warnings'].extend(warnings)
                        for item in images:
                            stored = 'images/' + item['id'] + '.' + ocr.MIME_EXT.get(item['mime'], 'bin')
                            path = current / stored
                            path.parent.mkdir(exist_ok=True)
                            path.write_bytes(item.pop('blob'))
                            item.update(stored_name=stored, sha256=digest(path), ocr_text=None,
                                        ocr_status='pending', ocr_error=None)
                            ws['images'].append(item)
                if not ws['blocks'] and not ws['images']:
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
        result['claims'].extend(copy.deepcopy(ws.get('ocr_claims', [])))
        for claim in ws.get('ocr_claims', []):
            checked = dict(check(claim, ws['facts']), ocr=True, confirmed=claim.get('confirmed', False))
            if checked['status'] == 'unverifiable':
                checked['code'] = 'needs_review'
            result['checks'].append(checked)
            result['summary']['claims'] += 1
            result['summary'][checked['status']] += 1
            result['summary']['pending'] += not checked['confirmed']
            # 图片论断（source='ocr'）无法回写，不进入可修复计数。
            result['summary']['repairable'] += (not checked['ocr']) and checked['confirmed'] and checked['status'] == 'inconsistent'
        result['diagnosis'], result['diagnosis_summary'] = diagnose(result, result['checks'])
        # 解释仅适用于生成时的版本；数据更新、确认、修复及撤销后使用当前模板。
        explanation_audit = next((a for a in reversed(ws['audit']) if a['event'] == '诊断解释'), {})
        if explanation_audit.get('revision') != ws['revision']:
            result['diagnosis_explanations'] = {}
        segments = unmatched_spans(ws['blocks'], ws['claims'])
        segments.extend(unmatched_spans(ws.get('ocr_blocks', []), ws.get('ocr_claims', [])))
        result['unmatched_segments'] = segments
        result['summary']['unmatched_segments'] = len(segments)
        # Keep the original block count for clients that used the first API.
        result['summary']['unmatched_blocks'] = sum(not any(c['file_id'] == b['file_id'] and c['location'] == b['location'] for c in ws['claims']) for b in ws['blocks'])
        # 派生事实与实际使用的值表是过程数据，不重复下发给前端。
        result.pop('source_facts', None)
        result.pop('graph_values', None)
        result['summary'].update(self.graph_summary(ws))
        for d in result['documents']:
            d.pop('stored_name', None)
            d['download_url'] = f'/api/projects/{ws["id"]}/files/{d["id"]}'
        result.setdefault('images', [])
        for item in result['images']:
            item.pop('stored_name', None)
            item['image_url'] = f'/api/projects/{ws["id"]}/images/{item["id"]}'
        return result

    def image_path(self, ws, image):
        """图片读取和确认前校验抽取时的摘要。"""
        path = self.folder(ws['id']) / ws['generation'] / image['stored_name']
        if digest(path) != image['sha256']:
            raise ValueError('图片在抽取后发生变化，已停止操作，请重新导入')
        return path

    def ocr_run(self, wid, revision, image_ids=None):
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, revision)
            images = {i['id']: i for i in ws.get('images', [])}
            if image_ids is not None and any(i not in images for i in image_ids):
                raise ValueError('图片不存在或不属于当前项目')
            selected = [i for i in images.values() if (image_ids is None or i['id'] in image_ids)
                        and i['ocr_status'] in ('pending', 'failed')]
            settings = ocr.config()
            if not selected or not settings['enabled']:
                return self.public(ws)
            paths = {i['id']: self.image_path(ws, i) for i in selected}
        # 网络请求不持锁；提交前重新校验版本，避免覆盖其他窗口的修改。
        results = {}
        for item in selected:
            try:
                text = ocr.ocr_image(paths[item['id']], item['mime'])
                results[item['id']] = ('done', text, None)
            except ValueError as exc:
                error = str(exc) if str(exc) in (ocr.DISABLED, ocr.UNSUPPORTED, ocr.FAILED) else ocr.FAILED
                results[item['id']] = ('failed', None, error)
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, revision)
            for item in ws.get('images', []):
                if item['id'] not in results:
                    continue
                self.image_path(ws, item)
                item['ocr_status'], item['ocr_text'], item['ocr_error'] = results[item['id']]
                ws['audit'].append({'time': now(), 'event': 'OCR 识别',
                                    'detail': f'{item["label"]}；后端 {settings["backend"]}；模型 {settings["model"]}；'
                                              + ('完成，等待人工核对' if item['ocr_status'] == 'done' else '失败，未确认文字不参与验证')})
            ws['revision'] += 1
            self.write(ws)
            return self.public(ws)

    def ocr_confirm(self, wid, revision, items):
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, revision)
            images = {i['id']: i for i in ws.get('images', [])}
            ids = [i.get('image_id') for i in items]
            if not ids or len(set(ids)) != len(ids) or any(i not in images for i in ids):
                raise ValueError('请选择当前项目的图片，且不可重复确认')
            for item in items:
                image = images[item['image_id']]
                if image['ocr_status'] == 'pending':
                    raise ValueError('请先运行 OCR，再核对文字')
                if not isinstance(item.get('text'), str) or not item['text'].strip() or len(item['text']) > ocr.MAX_TEXT:
                    raise ValueError('确认文字不能为空，且不能超过20000字')
                self.image_path(ws, image)
            blocks = [b for b in ws.get('ocr_blocks', []) if b['image_id'] not in ids]
            claims = [c for c in ws.get('ocr_claims', []) if c['image_id'] not in ids]
            for item in items:
                image = images[item['image_id']]
                text = item['text'].strip()
                block = {k: image[k] for k in ('file_id', 'location', 'label')}
                block.update(image_id=image['id'], text=text, source='ocr')
                blocks.append(block)
                for claim in extract_claims(block, ws['facts']):
                    # 图片论断只做只读核验：文字写在图片像素里，程序无法回写，
                    # 因此 repairable=False 且不计入可修复统计；人工核对的是图片文字本身，
                    # 它到事实 ID 的来源关联仍是候选，不能通过 links 接口确认，故 confirmed=False。
                    claim.update(extraction='OCR识别', source='ocr', repairable=False, image_id=image['id'], confirmed=False)
                    claims.append(claim)
                image.update(ocr_status='confirmed', ocr_text=text, ocr_error=None)
                ws['audit'].append({'time': now(), 'event': '确认图片文字',
                                    'detail': f'{image["label"]}；人工核对文字，仅参与只读核验，修改需回原图'})
            ws['ocr_blocks'], ws['ocr_claims'] = blocks, claims
            ws['revision'] += 1
            self.write(ws)
            return self.public(ws)

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
            fact_by_id = {f['id']: f for f in ws['facts']}
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
                for fid in candidate['refs']:
                    rule = self._remember(ws, claims[cid], fact_by_id[fid])
                    if rule:
                        ws['audit'].append({'time': rule['created_at'], 'event': '记录关联规则',
                                            'detail': f'规则 {rule["key"]}；事实 {rule["fact_id"]}'})
            ws['revision'] += 1
            ws['audit'].append({'time': now(), 'event': '确认来源', 'detail': f'确认{len(links)}项关联；排名结论限于选定比较集合'})
            self.write(ws)
            return self.public(ws)

    def _remember(self, ws, claim, fact):
        """记录规则级来源偏好；与 scan 的论断 ID 锚点记忆彼此独立。"""
        kind, claim_id = claim.get('kind'), claim.get('id')
        subject, metric, period, fact_id, scope = (fact.get(k) for k in ('subject', 'metric', 'period', 'id', 'scope'))
        if not all(isinstance(v, str) and v for v in (kind, claim_id, subject, metric, period, fact_id, scope)):
            return
        rules = ws.get('link_rules', [])
        if not isinstance(rules, list):
            return
        key = '|'.join((kind, subject, metric, period))
        matches = [r for r in rules if isinstance(r, dict) and r.get('key') == key]
        hits = matches[-1].get('hits', 0) if matches else 0
        rule = {'key': key, 'kind': kind, 'subject': subject, 'metric': metric, 'period': period,
                'scope': scope, 'fact_id': fact_id, 'source_claim_id': claim_id, 'created_at': now(),
                'hits': (hits if type(hits) is int and hits >= 0 else 0) + 1}
        ws['link_rules'] = [r for r in rules if not isinstance(r, dict) or r.get('key') != key] + [rule]
        return rule

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
            generation = 'v' + uuid.uuid4().hex[:12]
            root = self.folder(wid)
            target = root / generation
            shutil.copytree(root / ws['generation'], target)
            try:
                source = next(d for d in ws['documents'] if d['kind'] == 'xlsx')
                update_workbook(root / ws['generation'] / source['stored_name'], target / source['stored_name'], base, changes)
                ws['graph_changed'] = sorted(changes)
                self.scan(ws, target, ws['claims'])
                cascade = self.last_impact(ws, sorted(changes))
                ws['history'].append({'revision': previous['revision'], 'generation': previous['generation'], 'action': '数据变更',
                                      'changes': [{'id': i, 'before': facts[i]['value'], 'after': v} for i, v in changes.items()], 'time': now()})
                ws['generation'] = generation
                ws['revision'] += 1
                ws['last_repair'] = None
                ws['audit'].append({'time': now(), 'event': '数据变更', 'detail': '；'.join(f'{i}: {facts[i]["value"]} → {v}' for i, v in changes.items())})
                (target / 'previous-state.json').write_text(json.dumps(previous, ensure_ascii=False), encoding='utf-8')
                self.write(ws)
                result = self.public(ws)
                result['cascade'] = cascade
                return result
            except Exception:
                shutil.rmtree(target)
                raise

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
            affected = []
            summary = {'changed_facts': len(changes), 'affected_claims': 0,
                       'consistent': 0, 'inconsistent': 0, 'unverifiable': 0, 'repairable': 0}
            for claim in ws['claims']:
                if not changed.intersection(claim['refs']):
                    continue
                before = check(claim, ws['facts'])
                after = check(claim, incoming)
                affected.append({'claim_id': claim['id'],
                                 'before': before, 'after': after,
                                 # Keep the compact fields for API consumers that
                                 # only need a status summary.
                                 'before_status': before['status'], 'after_status': after['status'],
                                 'expected': after['expected'], 'reason': after['reason']})
                summary[after['status']] += 1
                summary['repairable'] += int(claim['confirmed'] and after['status'] == 'inconsistent')
            summary['affected_claims'] = len(affected)
            return {'revision': ws['revision'], 'changes': changes, 'affected': affected, 'summary': summary}

    def import_source(self, wid, revision, path):
        """Import an externally edited workbook without silently reusing changed meanings."""
        with self.lock:
            ws = self.read(wid)
            source, _, changes = self.source_update(ws, revision, path)
            previous = copy.deepcopy(ws)
            root = self.folder(wid)
            generation = 'v' + uuid.uuid4().hex[:12]
            target = root / generation
            shutil.copytree(root / ws['generation'], target)
            try:
                shutil.copyfile(path, target / source['stored_name'])
                self.scan(ws, target, ws['claims'])
                ws['generation'] = generation
                ws['revision'] += 1
                ws['last_repair'] = None
                ws.pop('suggestions', None)
                ws['history'].append({'revision': previous['revision'], 'generation': previous['generation'],
                                      'action': '导入更新表', 'changes': changes, 'time': now()})
                ws['audit'].append({'time': now(), 'event': '导入更新表',
                                    'detail': '；'.join(f'{c["id"]}: {c["before"]} → {c["after"]}' for c in changes)})
                (target / 'previous-state.json').write_text(json.dumps(previous, ensure_ascii=False), encoding='utf-8')
                self.write(ws)
                return self.public(ws)
            except Exception:
                shutil.rmtree(target)
                raise

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
            generation = 'v' + uuid.uuid4().hex[:12]
            target = root / generation
            shutil.copytree(root / ws['generation'], target)
            changes = [dict(claims[i], expected=checked[i]['expected']) for i in ids]
            try:
                for d in ws['documents']:
                    patches = [c for c in changes if c['file_id'] == d['id']]
                    if patches:
                        apply_document(root / ws['generation'] / d['stored_name'], target / d['stored_name'], patches, ws['facts'])
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
                ws['generation'] = generation
                ws['revision'] += 1
                ws['last_repair'] = {'time': now(), 'count': len(ids), 'verified': True,
                                     'unchanged_blocks_verified': sum(expected_blocks[k] == old_blocks[k] for k in old_blocks),
                                     'patches': [{'claim_id': c['id'], 'location': c['label'], 'before': c['original'], 'after': c['expected']} for c in changes]}
                ws['history'].append({'revision': previous['revision'], 'generation': previous['generation'], 'action': '修复文件', 'time': now()})
                ws['audit'].append({'time': now(), 'event': '修复并复核', 'detail': f'{len(ids)}项；重新读取Office文件后验证通过，其他支持范围内的正文保持一致'})
                (target / 'previous-state.json').write_text(json.dumps(previous, ensure_ascii=False), encoding='utf-8')
                self.write(ws)
                return self.public(ws)
            except Exception:
                shutil.rmtree(target)
                raise

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
                z.writestr('核验报告.md', build_report(ws))
            return root / name

    def export_local(self, wid):
        """把当前版本成果复制到本地受控输出目录。"""
        with self.lock:
            ws = self.read(wid)
            self.verify(ws, ws['revision'])
            base = Path(os.getenv('ZHILIAN_OUTPUT_DIR', str(Path(__file__).resolve().parent.parent / '导出成果')))
            safe_name = re.sub(r'[<>:"|?*\\/]', '_', str(ws.get('name', ''))).strip() or '项目'
            safe_name = safe_name[:40]
            folder = base / f'{safe_name}_r{ws["revision"]}'
            staging = base / f'.{folder.name}.tmp-{uuid.uuid4().hex[:12]}'
            try:
                staging.mkdir(parents=True, exist_ok=False)
                files = []
                source_root = self.folder(wid) / ws['generation']
                for document in ws['documents']:
                    source = source_root / document['stored_name']
                    target = staging / document['name']
                    shutil.copyfile(source, target)
                    files.append({'name': document['name'], 'path': str(folder / document['name'])})
                (staging / '变更报告.md').write_text(build_report(ws), encoding='utf-8')
                files.append({'name': '变更报告.md', 'path': str(folder / '变更报告.md')})
                if folder.exists():
                    shutil.rmtree(folder)
                staging.rename(folder)
            except (OSError, ValueError):
                shutil.rmtree(staging, ignore_errors=True)
                raise ValueError('无法写入本地输出目录，请检查路径和权限')
            ws['audit'].append({'time': now(), 'event': '导出到本地',
                                'detail': f'{folder}，{len(files)}份文件'})
            ws['revision'] += 1
            self.write(ws)
            return {'folder': str(folder), 'files': files}
