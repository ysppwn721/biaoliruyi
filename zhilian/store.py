"""Local persistent workspaces and transactional versions."""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from .engine import extract_claims, inspect, check, number, unmatched_spans
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
        ws['facts'] = read_facts(folder / source['stored_name'], source['id'])
        claims, blocks, old = [], [], {c['id']: c for c in old_claims}
        for d in ws['documents']:
            d['sha256'] = digest(folder / d['stored_name'])
            if d['kind'] == 'xlsx':
                continue
            bs, cs, warnings = read_document(folder / d['stored_name'], d['id'], ws['facts'])
            d['warnings'] = warnings
            blocks.extend(bs)
            for block in bs:
                cs.extend(extract_claims(block, ws['facts']))
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
        return ws

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
            facts = {f['id']: f for f in ws['facts']}
            if not values or any(i not in facts for i in values):
                raise ValueError('没有有效的事实更新')
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
                update_workbook(root / ws['generation'] / source['stored_name'], target / source['stored_name'], ws['facts'], changes)
                self.scan(ws, target, ws['claims'])
                ws['history'].append({'revision': previous['revision'], 'generation': previous['generation'], 'action': '数据变更',
                                      'changes': [{'id': i, 'before': facts[i]['value'], 'after': v} for i, v in changes.items()], 'time': now()})
                ws['generation'] = generation
                ws['revision'] += 1
                ws['last_repair'] = None
                ws['audit'].append({'time': now(), 'event': '数据变更', 'detail': '；'.join(f'{i}: {facts[i]["value"]} → {v}' for i, v in changes.items())})
                (target / 'previous-state.json').write_text(json.dumps(previous, ensure_ascii=False), encoding='utf-8')
                self.write(ws)
                return self.public(ws)
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
                checks, summary = inspect(ws)
                lines = ['# 知链核验报告', '', f'项目：{ws["name"]}', f'版本：{ws["revision"]}', '',
                         f'已检查论断 {summary["claims"]}；一致 {summary["consistent"]}；不一致 {summary["inconsistent"]}；无法验证 {summary["unverifiable"]}。',
                         '本报告仅涵盖已识别、受支持的论断，不能作为整个文档正确性的保证。', '']
                for c, r in zip(ws['claims'], checks):
                    lines.extend([f'## {c["label"]}', c['original'], f'状态：{r["status"]}；来源已确认：{c["confirmed"]}', r['reason'], ''])
                z.writestr('核验报告.md', '\n'.join(lines))
            return root / name
