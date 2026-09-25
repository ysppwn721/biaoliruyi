"""依据项目数据生成成果与变更报告，不调用模型。"""
from __future__ import annotations

from datetime import datetime, timezone

from .diagnose import diagnose
from .engine import check, inspect


def now():
    return datetime.now(timezone.utc).isoformat()


def _value(value):
    return '缺失' if value is None else str(value)


def build_report(ws) -> str:
    """基于确定性核验数据生成完整成果与变更报告，不调用模型。"""
    # public 视图已合并图片论断；按 ID 去重，保证原始状态与公开状态的报告一致。
    text_claims = [c for c in ws['claims'] if c.get('source') != 'ocr']
    images = {c['id']: c for c in ws['claims'] + ws.get('ocr_claims', []) if c.get('source') == 'ocr'}
    snapshot = dict(ws, claims=text_claims)
    checks, summary = inspect(snapshot)
    for claim in images.values():
        checked = dict(check(claim, ws['facts']), confirmed=False)
        if checked['status'] == 'unverifiable':
            checked['code'] = 'needs_review'
        checks.append(checked)
        summary['claims'] += 1
        summary[checked['status']] += 1
        summary['pending'] += 1
    snapshot['claims'] = text_claims + [dict(c, confirmed=False) for c in images.values()]
    records, diagnosis_summary = diagnose(snapshot, checks)
    repair = ws.get('last_repair') or {}
    lines = [
        '# 知链成果与变更报告', '',
        f'项目：{ws.get("name", "未命名项目")}',
        f'版本：{ws.get("revision", 0)}',
        f'生成时间：{now()}', '',
        '## 一、概览',
        f'- 检查论断 {summary["claims"]} 项：一致 {summary["consistent"]}、结论失效 {summary["inconsistent"]}、无法判断 {summary["unverifiable"]}。',
        f'- 本次修复 {repair.get("count", 0)} 项；来源待确认 {summary["pending"]} 项。',
        '- 本报告仅涵盖已识别、受支持的论断，不能作为整份文档正确性的保证。', '',
        '## 二、数据变更',
        '以下列出当前项目历史中的数据变更；修改前后对照仅列最近一次文件修复。',
    ]
    facts = {f.get('id'): f for f in ws.get('facts', [])}
    changes = []
    for entry in ws.get('history', []):
        if entry.get('action') not in ('数据变更', '导入更新表'):
            continue
        for change in entry.get('changes', []):
            fact = facts.get(change.get('id'), {})
            position = f'{fact.get("sheet", "未知表")}!{fact.get("cell", "未知单元格")}'
            changes.append(f'- {change.get("id", "未知事实")}：{_value(change.get("before"))} → {_value(change.get("after"))} '
                           f'（{fact.get("subject", "未知主体")}·{fact.get("metric", "未知指标")}·{fact.get("period", "未知期间")}，{position}）')
    lines.extend(changes or ['本次无数据变更'])
    lines.extend(['', '## 三、修改前后对照'])
    patches = repair.get('patches') or []
    if patches:
        for patch in patches:
            lines.extend([f'- {patch.get("location", "未知位置")}',
                          f'  原文：{patch.get("before", "")}',
                          f'  改为：{patch.get("after", "")}'])
    else:
        lines.append('本次无文件修复')
    lines.extend(['', '## 四、逐条核验与依据'])
    for record in records:
        lines.extend([f'### {record["label"]}（{record["file_name"]}）',
                      f'- 原文：{record["original"]}',
                      f'- 状态：{record["category"]}（{record["status"]}）；来源已确认：{"是" if record["confirmed"] else "否"}'])
        evidence = record.get('evidence') or []
        if evidence:
            text = '；'.join(f'{f.get("id", "")} {f.get("subject", "")}·{f.get("metric", "")}·{f.get("period", "")} = '
                            f'{_value(f.get("value"))}{f.get("unit", "")}（{f.get("scope", "")}，{f.get("sheet", "")}!{f.get("cell", "")}）'
                            for f in evidence)
        else:
            text = '暂无可用 Excel 单元格依据'
        lines.extend([f'- 依据：{text}', f'- 说明：{record.get("reason", "") or "无"}',
                      f'- 建议：{record.get("fix_hint", "请人工复核。")}', ''])
    if not records:
        lines.extend(['暂无已识别的受支持论断', ''])
    lines.extend(['## 五、人工待办'])
    pending = []
    for record in records:
        if not record.get('confirmed'):
            pending.append(f'- [ ] 未确认来源：{record["original"]}（{record["file_name"]}·{record["label"]}）')
    for code, title in [('missing_data', '数据缺失'), ('source_conflict', '来源冲突'),
                        ('scope_mismatch', '口径不一致'), ('needs_review', '需人工复核')]:
        if diagnosis_summary[code]:
            pending.extend(['', f'### 无法判断 · {title}'])
            for record in records:
                group = 'source_conflict' if record['code'] == 'source_count' else record['code']
                if record['status'] == 'unverifiable' and group == code:
                    pending.append(f'- [ ] 无法判断：{record["original"]} —— {record["fix_hint"]}（{record["file_name"]}·{record["label"]}）')
    for record in records:
        if record.get('source') == 'ocr':
            pending.append(f'- [ ] 图片论断（只读）：{record["original"]} —— 需编辑原图后重新导入')
        elif record['status'] == 'inconsistent':
            pending.append(f'- [ ] 待修复结论：{record["original"]} —— {record["fix_hint"]}（{record["file_name"]}·{record["label"]}）')
    lines.extend(pending or ['无待办，可交付'])
    return '\n'.join(lines) + '\n'
