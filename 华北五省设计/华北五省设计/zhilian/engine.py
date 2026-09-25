"""Deterministic, typed claim checks. No eval, generated code or model arithmetic."""
from __future__ import annotations

import hashlib
import math
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

KINDS = {'quote': '数值引用', 'growth': '增长率', 'ranking': '排名', 'threshold': '阈值', 'chart': '图表'}
EXTRACTION_VERSION = 2
UNITS = {'元': ('currency', Decimal(1)), '万元': ('currency', Decimal(10000)),
         '亿元': ('currency', Decimal(100000000)), '件': ('count', Decimal(1)),
         '人': ('people', Decimal(1)), '%': ('percentage', Decimal(1))}
NUM = r'-?\d+(?:\.\d+)?'
UNIT = r'亿元|万元|元|件|人|%'


class CheckError(ValueError):
    """带诊断码的校验错误，让错误分类走结构化 code 而非文案精确匹配。"""
    def __init__(self, reason, code='needs_review'):
        super().__init__(reason)
        self.code = code


def number(value) -> Decimal:
    if isinstance(value, bool):
        raise ValueError('布尔值不能作为数值')
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('请输入有效数字')
    if not n.is_finite() or abs(n) > Decimal('1e15'):
        raise ValueError('数字必须有限且绝对值不超过 10^15')
    return n


def fmt(value) -> str:
    n = number(value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    s = format(n, 'f')
    return s.rstrip('0').rstrip('.') if '.' in s else s


def convert(value, unit, target):
    if unit == target:
        return number(value)
    a, b = UNITS.get(unit), UNITS.get(target)
    if not a or not b or a[0] != b[0]:
        raise ValueError(f'单位不兼容：{unit} 与 {target}')
    return number(value) * a[1] / b[1]


def stable_id(*parts):
    return hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:18]


def best_facts(text, facts, *, period=None):
    scored = []
    for fact in facts:
        score = 0
        if fact['metric'] and fact['metric'] in text:
            score += 5
        if fact['subject'] not in ('总计', '整体', '全部') and fact['subject'] in text:
            score += 4
        if fact['period'] and fact['period'] in text:
            score += 3
        if period and fact['period'] != period:
            continue
        if score >= 5:
            scored.append((score, fact))
    if not scored:
        return []
    top = max(s for s, _ in scored)
    return [f for s, f in scored if s == top]


def extract_claims(block, facts):
    """Extract separate, non-overlapping assertions, retaining their exact text anchors."""
    result = []
    context = ''
    patterns = [
        ('growth', r'(?:较上期|环比)(增长|下降|持平)(?:(' + NUM + r')%)?'),
        ('ranking', r'(.+?)(销售额|销量|收入|支出|得分)(?:并列)?最高'),
        ('threshold', r'(未超过|不超过|超过|不少于|低于)\s*(' + NUM + r')\s*(' + UNIT + r')'),
        ('budget', r'支出(未超过|不超过|超过)预算'),
        ('quote', r'(?:为|是|达到)\s*(' + NUM + r')\s*(' + UNIT + r')'),
    ]
    candidate_matches = []
    sentence_meta = []
    for sentence_index, sentence in enumerate(re.finditer(r'[^。！？；;\n]+', block['text'])):
        sentence_meta.append(sentence.group())
        matches = sorted((m.start(), m.end(), kind, m)
                         for kind, pattern in patterns for m in re.finditer(pattern, sentence.group()))
        previous_end = 0
        for marker_start, marker_end, kind, match in matches:
            if marker_start < previous_end:
                continue
            prefix = sentence.group()[previous_end:marker_start]
            # A comma or connector belongs to neither adjacent assertion. Text after
            # the final predicate remains uncovered instead of inheriting its status.
            offset = max(prefix.rfind('，'), prefix.rfind(',')) + 1
            leading = prefix[offset:]
            trim = re.match(r'^[\s、]*(?:(?:并且|而且|同时|以及|且|并)[\s、]*)?', leading).end()
            local_start = previous_end + offset + trim
            start = sentence.start() + local_start
            end = sentence.start() + marker_end
            text = block['text'][start:end]
            leading_punctuation = len(text) - len(text.lstrip(' \t、，,'))
            if leading_punctuation:
                start += leading_punctuation
                text = text[leading_punctuation:]
            local_match = re.search(dict(patterns)[kind], text)
            candidate_matches.append((sentence_index, start, end, text, kind, local_match))
            previous_end = marker_end

    # The old extractor produced one claim per sentence. Preserve those IDs when
    # the old primary kind is still present, while assigning deterministic IDs to
    # additional assertions introduced by compound extraction.
    legacy_kind, legacy_id_index = {}, {}
    legacy_counter = 0
    for sentence_index, sentence_text in enumerate(sentence_meta):
        if re.search(patterns[0][1], sentence_text):
            legacy_kind[sentence_index] = 'growth'
        elif re.search(patterns[1][1], sentence_text):
            legacy_kind[sentence_index] = 'ranking'
        elif re.search(patterns[2][1], sentence_text):
            legacy_kind[sentence_index] = 'threshold'
        elif re.search(patterns[3][1], sentence_text):
            legacy_kind[sentence_index] = 'budget'
        elif re.search(patterns[4][1], sentence_text):
            legacy_kind[sentence_index] = 'quote'
        if legacy_kind.get(sentence_index):
            legacy_id_index[sentence_index] = legacy_counter
            legacy_counter += 1
    compound_counter, legacy_assigned = 0, set()
    for sentence_index, start, end, text, marker_kind, match in candidate_matches:
        refs, spec, kind, issue = [], {}, None, ''
        source_text = text if best_facts(text, facts) else context
        if marker_kind == 'growth':
            growth = match
            kind = 'growth'
            curr = best_facts(source_text, facts, period='本期')
            prev = best_facts(source_text, facts, period='上期')
            if len(curr) == len(prev) == 1:
                refs = [prev[0]['id'], curr[0]['id']]
            else:
                issue = '未唯一确定同口径的上期与本期数据，请确认关联'
            spec = {'span': [growth.start(1), growth.end()], 'reported': float(growth[2] or 0) * (-1 if growth[1] == '下降' else 1),
                    'qualitative': growth[2] is None, 'direction': {'增长': 1, '下降': -1, '持平': 0}[growth[1]]}
        elif marker_kind == 'ranking':
            rank = match
            kind = 'ranking'
            metric = rank[2]
            rank_facts = [f for f in facts if f['metric'] == metric and f['period'] == '本期']
            refs = [f['id'] for f in rank_facts]
            spec = {'metric': metric, 'winners': rank[1].strip().split('、'), 'span': [rank.start(), rank.end()]}
            issue = '' if len(refs) >= 2 else '排名至少需要两个可比较对象'
        elif marker_kind == 'threshold':
            threshold = match
            kind = 'threshold'
            fs = best_facts(source_text, facts)
            refs = [fs[0]['id']] if len(fs) == 1 else []
            positive, negative, op = ('超过', '未超过', '>')
            if threshold[1] in ('不少于', '低于'):
                positive, negative, op = ('不少于', '低于', '>=')
            spec = {'limit': float(threshold[2]), 'unit': threshold[3], 'positive': positive,
                    'negative': negative, 'op': op, 'reported_positive': threshold[1] == positive,
                    'span': [threshold.start(1), threshold.end(1)]}
        elif marker_kind == 'budget':
            kind = 'threshold'
            # Resolve each side from an explicit metric phrase; both period and
            # metric are required so similarly named facts stay ambiguous.
            fs1, fs2 = best_facts('本期支出', facts), best_facts('本期预算', facts)
            refs = [fs1[0]['id'], fs2[0]['id']] if len(fs1) == len(fs2) == 1 else []
            m = match
            spec = {'positive': '超过', 'negative': '未超过', 'op': '>', 'reported_positive': m[1] == '超过', 'span': [m.start(), m.end()]}
            spec['span'] = [m.start(1), m.end(1)]
        elif marker_kind == 'quote':
            quote = match
            kind = 'quote'
            fs = best_facts(source_text, facts)
            refs = [fs[0]['id']] if len(fs) == 1 else []
            spec = {'reported': float(quote[1]), 'unit': quote[2], 'span': [quote.start(1), quote.end(1)]}
        if kind:
            if not refs:
                issue = issue or '未找到唯一来源，需手动关联事实'
            if legacy_kind.get(sentence_index) == kind and sentence_index not in legacy_assigned:
                legacy_assigned.add(sentence_index)
                source_key = stable_id(block['file_id'], block['location'], kind, legacy_id_index[sentence_index])
            else:
                source_key = stable_id(block['file_id'], block['location'], 'compound-v2', compound_counter, kind)
            compound_counter += 1
            result.append({'id': source_key,
                           'file_id': block['file_id'], 'location': block['location'], 'label': block['label'],
                           'original': text, 'start': start, 'end': end,
                           'kind': kind, 'refs': refs, 'spec': spec, 'confirmed': False,
                           'extraction': '规则识别', 'issue': issue})
        context = text if best_facts(text, facts) else context
    return result


def unmatched_spans(blocks, claims):
    """Return uncovered prose, including gaps in otherwise recognized paragraphs."""
    result = []
    for block in blocks:
        ranges = sorted((c['start'], c['end']) for c in claims if c['kind'] != 'chart'
                        and c['file_id'] == block['file_id'] and c['location'] == block['location'])
        offset = 0
        for start, end in ranges + [(len(block['text']), len(block['text']))]:
            raw = block['text'][offset:start]
            text = raw.strip(' \t\r\n。！？；;，,、')
            if text and not re.fullmatch(r'(?:并且|而且|同时|以及|且|并)', text):
                leading = len(raw) - len(raw.lstrip(' \t\r\n。！？；;，,、'))
                result.append(dict(block, text=text, start=offset + leading, end=start))
            offset = max(offset, end)
    return result


def replace_span(text, span, replacement):
    return text[:span[0]] + replacement + text[span[1]:]


def check(claim, facts):
    byid = {f['id']: f for f in facts}
    out = {'claim_id': claim['id'], 'status': 'unverifiable', 'code': 'needs_review', 'expected': None, 'reason': '', 'evidence': []}
    try:
        refs = [byid[i] for i in claim['refs']]
        out['evidence'] = [{k: f.get(k) for k in ('id', 'subject', 'metric', 'period', 'value', 'unit', 'scope', 'sheet', 'cell')} for f in refs]
        if not refs or any(f.get('value') is None for f in refs):
            raise CheckError('来源缺失或数值不可计算', 'missing_data')
        k, s, old = claim['kind'], claim['spec'], claim['original']
        expected, ok, calculation = old, False, ''
        if k == 'quote':
            if len(refs) != 1:
                raise CheckError('数值引用必须关联一个事实', 'source_count')
            value = convert(refs[0]['value'], refs[0]['unit'], s['unit'])
            ok = value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP) == number(s['reported']).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            expected = replace_span(old, s['span'], fmt(value))
            calculation = f"{refs[0]['value']} {refs[0]['unit']} = {fmt(value)} {s['unit']}"
        elif k == 'growth':
            if len(refs) != 2:
                raise CheckError('增长率需要上期、本期两个事实',
                                 'source_count' if len(refs) > 2 else 'missing_data')
            a, b = refs
            if any(a[x] != b[x] for x in ('subject', 'metric', 'scope')) or a['period'] != '上期' or b['period'] != '本期':
                raise CheckError('增长率的主体、指标、口径或上期本期顺序不一致', 'scope_mismatch')
            before, after = number(a['value']), convert(b['value'], b['unit'], a['unit'])
            if before <= 0:
                raise ValueError('上期数值必须大于零；零值或负基期转人工复核')
            rate = (after - before) / before * 100
            rounded = rate.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            if s.get('qualitative'):
                direction = 1 if rate > 0 else -1 if rate < 0 else 0
                ok = direction == s['direction']
                wording = {1: '增长', -1: '下降', 0: '持平'}[direction]
            else:
                ok = rounded == number(s['reported']).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                wording = '持平' if rounded == 0 else ('增长' if rounded > 0 else '下降') + fmt(abs(rounded)) + '%'
            expected = replace_span(old, s['span'], wording)
            calculation = f'({fmt(after)} − {fmt(before)}) / {fmt(before)} × 100 = {fmt(rate)}%'
        elif k == 'ranking':
            if len(refs) < 2:
                raise CheckError('排名至少需要两个对象', 'source_conflict')
            first = refs[0]
            if any(any(f[x] != first[x] for x in ('metric', 'period', 'scope')) for f in refs):
                raise CheckError('排名对象的指标、期间或统计口径不一致', 'scope_mismatch')
            if len({f['subject'] for f in refs}) != len(refs):
                raise CheckError('排名对象重复，请核对比较集合', 'source_conflict')
            values = [convert(f['value'], f['unit'], first['unit']) for f in refs]
            winners = [f['subject'] for f, v in zip(refs, values) if v == max(values)]
            ok = set(winners) == set(s['winners'])
            target = '、'.join(winners) + s['metric'] + ('并列最高' if len(winners) > 1 else '最高')
            expected = replace_span(old, s['span'], target)
            calculation = '；'.join(f"{f['subject']} {fmt(v)}{first['unit']}" for f, v in zip(refs, values)) + '（仅针对已确认的比较集合）'
        elif k == 'threshold':
            if 'limit' in s:
                if len(refs) != 1:
                    raise CheckError('固定阈值需要一个事实',
                                     'source_count' if len(refs) > 1 else 'missing_data')
                value, limit, unit = convert(refs[0]['value'], refs[0]['unit'], s['unit']), number(s['limit']), s['unit']
            else:
                if len(refs) != 2:
                    raise CheckError('支出与预算需要两个事实',
                                     'source_count' if len(refs) > 2 else 'missing_data')
                a, b = refs
                if any(a[x] != b[x] for x in ('subject', 'period', 'scope')) or a['metric'] != '支出' or b['metric'] != '预算':
                    raise CheckError('支出与预算的主体、期间、口径或指标不一致', 'scope_mismatch')
                value, limit, unit = number(a['value']), convert(b['value'], b['unit'], a['unit']), a['unit']
            truth = value > limit if s['op'] == '>' else value >= limit
            ok = truth == s['reported_positive']
            expected = replace_span(old, s['span'], s['positive'] if truth else s['negative'])
            calculation = f"{fmt(value)}{unit} {s['op']} {fmt(limit)}{unit} → {'成立' if truth else '不成立'}"
        elif k == 'chart':
            if len(refs) != len(s['values']):
                raise CheckError('图表关联数量与原始类别不一致', 'source_conflict')
            values = [convert(f['value'], f['unit'], s['unit']) for f in refs]
            if any(f['metric'] != refs[0]['metric'] or f['scope'] != refs[0]['scope'] or f['subject'] != refs[0]['subject'] for f in refs):
                raise CheckError('图表系列的指标、主体或口径不一致', 'scope_mismatch')
            if [f['period'] for f in refs] != s['categories']:
                raise CheckError('图表类别与来源期间不匹配', 'scope_mismatch')
            ok = all(number(x) == y for x, y in zip(s['values'], values))
            expected = s['series'] + '：' + '，'.join(f'{c} {fmt(v)}{s["unit"]}' for c, v in zip(s['categories'], values))
            calculation = '按已确认的系列与类别重建原生图表数据'
        else:
            raise ValueError('不支持的论断类型')
        out.update(status='consistent' if ok else 'inconsistent',
                   code='consistent' if ok else 'inconsistent',
                   expected=old if ok else expected, reason=calculation)
    except CheckError as exc:
        out['reason'] = str(exc)
        out['code'] = exc.code
    except (ValueError, KeyError, IndexError, InvalidOperation, TypeError) as exc:
        out['reason'] = str(exc)
        out['code'] = 'missing_data' if any(i not in byid for i in claim['refs']) else 'needs_review'
    return out


def inspect(workspace):
    checks = [dict(check(c, workspace['facts']), confirmed=c['confirmed']) for c in workspace['claims']]
    summary = {'claims': len(checks), 'consistent': 0, 'inconsistent': 0, 'unverifiable': 0,
               'pending': 0, 'repairable': 0, 'documents': len(workspace['documents']), 'facts': len(workspace['facts'])}
    for r in checks:
        summary[r['status']] += 1
        summary['pending'] += not r['confirmed']
        summary['repairable'] += r['confirmed'] and r['status'] == 'inconsistent'
    return checks, summary
