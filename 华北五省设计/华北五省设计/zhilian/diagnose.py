"""确定性异常分类与证据溯源，不重新计算论断。"""
from __future__ import annotations

from collections import Counter


CATEGORY = {
    'consistent': '通过',
    'inconsistent': '结论失效',
    'missing_data': '数据缺失',
    'source_count': '来源冲突',
    'source_conflict': '来源冲突',
    'scope_mismatch': '口径不一致',
    'needs_review': '需人工复核',
}


def template_explanation(record):
    code = record.get('code', 'needs_review')
    if code == 'missing_data':
        return '该论断引用的来源缺失或数值为空，无法核验；请先在 Excel 事实表中补全对应数据，再确认来源。'
    if code in ('source_count', 'source_conflict'):
        return '该论断存在多个候选来源或引用数量与论断类型不符，需人工确认唯一、完整的比较集合。'
    if code == 'scope_mismatch':
        return '所引用事实的主体、指标、期间或统计口径不一致，无法比较；请核对并选择同口径的来源。'
    if code == 'needs_review':
        return '该情形需人工复核（如零/负基期或暂不支持的表达）。'
    if code == 'inconsistent':
        expected = record.get('expected')
        return f'计算结果与原文不一致，建议改写为：{expected}。' if expected else '计算结果与原文不一致，请核对来源后预览修复。'
    return '计算一致，无需处理。'


def template_fix_hint(code):
    return {
        'consistent': '无需处理。',
        'inconsistent': '确认来源后预览并批准修复。',
        'missing_data': '补全 Excel 事实表中的数据，并重新确认来源。',
        'source_count': '人工核对并选择唯一、完整的来源集合。',
        'source_conflict': '人工核对并选择唯一、完整的比较集合。',
        'scope_mismatch': '核对主体、指标、期间和统计口径，重新选择同口径事实。',
        'needs_review': '人工复核该表达或基期数据，必要时调整论断或来源。',
    }.get(code, '请人工复核。')


def diagnose(ws, checks):
    """复用传入的检查结果，生成诊断记录与分类汇总。"""
    documents = {d['id']: d for d in ws.get('documents', [])}
    claims = {c['id']: c for c in ws.get('claims', [])}
    records = []
    for checked in checks:
        claim = claims.get(checked.get('claim_id'), {})
        document = documents.get(claim.get('file_id'), {})
        code = checked.get('code') or ('consistent' if checked.get('status') == 'consistent' else 'needs_review')
        record = {
            'claim_id': claim.get('id', checked.get('claim_id')),
            'kind': claim.get('kind'),
            'original': claim.get('original', ''),
            'status': checked.get('status'),
            'confirmed': claim.get('confirmed', False),
            'code': code,
            'category': CATEGORY.get(code, '需人工复核'),
            'file_id': claim.get('file_id'),
            'file_name': document.get('name', ''),
            'label': claim.get('label', ''),
            'location': claim.get('location', ''),
            'start': claim.get('start'),
            'end': claim.get('end'),
            'evidence': checked.get('evidence', []),
            'reason': checked.get('reason', ''),
            'expected': checked.get('expected') if checked.get('status') == 'inconsistent' else None,
            'fix_hint': template_fix_hint(code),
        }
        record['explanation'] = template_explanation(record)
        if claim.get('source') == 'ocr':
            record.update(source='ocr', repairable=False, image_id=claim['image_id'])
            record['fix_hint'] = '图片论断仅用于只读验证；请人工核对图片及候选事实，需要修改时请编辑原图片后重新导入。'
            record['explanation'] += ' 图片文字已人工核对，事实关联仍是规则候选，不能自动修复图片。'
        records.append(record)
    counts = Counter(r['code'] for r in records)
    summary = {
        'total': len(records),
        'consistent': counts.get('consistent', 0),
        'inconsistent': counts.get('inconsistent', 0),
        'missing_data': counts.get('missing_data', 0),
        'source_conflict': counts.get('source_conflict', 0) + counts.get('source_count', 0),
        'scope_mismatch': counts.get('scope_mismatch', 0),
        'needs_review': counts.get('needs_review', 0),
    }
    return records, summary
