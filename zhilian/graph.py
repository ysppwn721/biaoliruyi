"""事实依赖图：派生事实、传递闭包、受影响结论与健全性检查。

本模块只依赖标准库，刻意不引入 networkx / ortools：
拓扑排序、环检测与可达性分析均自行实现，既避免新增第三方依赖与许可负担，
也使这部分成为可完整解释、可现场演示的团队原创代码。

层次关系：
    engine.check()   判定单条论断与事实是否一致（不含依赖传播）
    graph.compute()  先按拓扑序重算派生事实，再由 engine.check() 判定论断

约定：
    - 基础事实来自 Excel；派生事实由受限表达式从其他事实算出。
    - 表达式集合是封闭白名单，不接受任意代码或模型生成的表达式。
    - 计算全程使用 Decimal，与 engine 保持一致，不使用浮点。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .engine import UNITS, convert, fmt, number

MAX_DERIVED = 2000
MAX_REACH = 200000

_MISSING = object()

# 表达式白名单：运算 → 参数个数与说明。参数个数用 `arity` 具名，
# 避免元组顺序在多处被误读。
OPERATIONS = {
    'sum': {'arity': 1, 'note': '合计：同口径同类别的多项求和，至少两项'},
    'diff': {'arity': 2, 'note': '差额：第一个事实减去第二个事实'},
    'ratio': {'arity': 2, 'note': '比率：本期除以上期，输出百分比'},
    'growth': {'arity': 2, 'note': '增长率：由上期与本期计算，输出百分比'},
}


class DerivationError(ValueError):
    """派生定义非法。错误信息面向用户，可直接在界面上展示。"""


def _quantize(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def parse_expr(text: str) -> dict:
    """把 `sum(a, b, c)` 形式的表达式解析为结构化定义。

    只接受 OPERATIONS 中的运算；参数必须是事实ID形态的标识符，
    不接受字面量、嵌套调用或任何可执行内容。
    """
    raw = (text or '').strip()
    if not raw.endswith(')') or '(' not in raw:
        raise DerivationError('表达式应形如 sum(a, b)')
    name, _, tail = raw.partition('(')
    name = name.strip()
    if name not in OPERATIONS:
        raise DerivationError('不支持的运算：%s；可用：%s' % (name or '空', '、'.join(OPERATIONS)))
    body = tail[:-1].strip()
    args = [a.strip() for a in body.split(',')] if body else []
    if any(not a for a in args):
        raise DerivationError('参数不能为空')
    for arg in args:
        if not arg.replace('_', '').replace('-', '').isalnum():
            raise DerivationError('参数必须是事实ID：%s' % arg)
    arity = OPERATIONS[name]['arity']
    if name == 'sum':
        if len(args) < 2:
            raise DerivationError('sum 至少需要两个事实')
    elif len(args) != arity:
        raise DerivationError('%s 需要 %d 个参数，实际给了 %d 个' % (name, arity, len(args)))
    if name != 'sum' and len(set(args)) != len(args):
        raise DerivationError('%s 的两个参数不能是同一个事实' % name)
    return {'op': name, 'inputs': args}


def eval_expr(op: str, sources: list) -> tuple:
    """按运算符计算派生值，返回 (Decimal 值, 单位, 计算说明)。

    任何不满足口径或数学前提的情况都抛出 DerivationError，
    由调用方转为"无法计算"并转人工复核，不做静默兜底。
    """
    if op not in OPERATIONS:
        raise DerivationError('不支持的运算：%s' % op)
    # 基础事实来自 Excel，数值是 float；派生值在内存里是 Decimal。
    # 统一经 number() 归一化，避免 float 与 Decimal 混算抛 TypeError。
    values = []
    for fact in sources:
        if fact.get('value') is None:
            raise DerivationError('来源事实「%s」缺少数值' % fact.get('id', '?'))
        values.append(number(fact['value']))
    if op != 'sum':
        values = [number(v) for v in values]

    if op == 'sum':
        first = sources[0]
        # 合计的语义是"同一指标在多个主体上相加"（A产品 + B产品），
        # 因此要求指标、期间、口径一致，主体允许不同；若有主体重复，
        # 需要调用方自行核对是否重复计数。
        for fact in sources[1:]:
            if (fact['metric'], fact['period'], fact['scope']) != (
                    first['metric'], first['period'], first['scope']):
                raise DerivationError('合计要求指标、期间、统计口径一致，可对不同主体求和')
        subjects = [f['subject'] for f in sources]
        if len(set(subjects)) != len(subjects):
            raise DerivationError('合计中存在重复主体（%s），请核对是否重复计数' % '、'.join(
                s for s in set(subjects) if subjects.count(s) > 1))
        total = sum((convert(v, f['unit'], first['unit']) for v, f in zip(values, sources)), Decimal(0))
        detail = ' + '.join('%s%s' % (fmt(f['value']), f['unit']) for f in sources)
        return _quantize(total, '.01'), first['unit'], '%s = %s %s' % (detail, fmt(total), first['unit'])

    a, b = sources
    if (a['subject'], a['scope']) != (b['subject'], b['scope']):
        raise DerivationError('两个事实的主体、统计口径必须一致')

    if op == 'diff':
        # 差额允许指标不同：如「销售额 − 成本 = 利润」。两侧按左侧单位对齐。
        left, right = values[0], convert(values[1], b['unit'], a['unit'])
        result = _quantize(left - right, '.01')
        detail = '%s − %s = %s %s' % (fmt(left), fmt(right), fmt(result), a['unit'])
        return result, a['unit'], detail

    # 增长率只接受一种形态：同主体、同指标、同口径的「本期 vs 上期」。
    # 不套用比率的同期放宽规则，否则两个本期事实也能算出一个无意义的百分比。
    if op == 'growth':
        if a['metric'] != b['metric']:
            raise DerivationError('增长率要求两个事实的指标一致，实际是「%s」与「%s」' % (
                a['metric'], b['metric']))
        if a['period'] != '本期' or b['period'] != '上期':
            raise DerivationError('增长率要求第一个是本期事实、第二个是上期事实，'
                                 '实际是「%s」与「%s」' % (a['period'], b['period']))
        before, after = convert(values[1], b['unit'], a['unit']), values[0]
        if before <= 0:
            raise DerivationError('上期数值必须大于零；零值或负基期转人工复核')
        result = _quantize((after - before) / before * 100, '.01')
        detail = '(%s − %s) ÷ %s × 100 = %s%%' % (fmt(after), fmt(before), fmt(before), fmt(result))
        return result, '%', detail

    # 比率比较两个数值的相对关系，有两种合法模式：
    #   A 同期不同指标：成本占比 = 成本 ÷ 销售额
    #   B 同指标跨期间：本期 ÷ 上期
    # 两者都不满足时视为口径不一致，转人工复核。
    same_period = a['period'] == b['period']
    same_metric = a['metric'] == b['metric']
    if not same_period and not same_metric:
        raise DerivationError(
            '比率的两个事实必须同期，或同指标不同期间；实际是'
            '「%s·%s」与「%s·%s」' % (a['metric'], a['period'], b['metric'], b['period']))

    if same_period and a['period'] != '本期':
        raise DerivationError('同期计算要求双方都是本期事实，实际是「%s」' % a['period'])

    left, right = values[0], convert(values[1], b['unit'], a['unit'])
    if right == 0:
        raise DerivationError('分母为零，无法计算比率')
    result = _quantize(left / right * 100, '.01')
    mode = '同期占比' if same_period else '跨期比值'
    detail = '%s ÷ %s × 100 = %s%%（%s）' % (fmt(left), fmt(right), fmt(result), mode)
    return result, '%', detail


class Derivations:
    """工作区里的派生事实定义集合，负责校验与拓扑排序。"""

    def __init__(self, records=None):
        self.records = []
        self._index = {}
        for record in records or []:
            self.add(record, _defer=True)
        self.order, self.cycles = self._topological()

    # ---- 构建 -------------------------------------------------------------
    def add(self, record: dict, _defer: bool = False):
        rid = (record.get('id') or '').strip()
        if not rid:
            raise DerivationError('派生事实必须有 ID')
        if rid in self._index:
            raise DerivationError('派生事实 ID 重复：%s' % rid)
        parsed = parse_expr(record.get('expr') if isinstance(record.get('expr'), str)
                            else _render(record.get('op'), record.get('inputs')))
        entry = {
            'id': rid,
            'op': parsed['op'],
            'inputs': parsed['inputs'],
            'unit': (record.get('unit') or '').strip(),
            'label': (record.get('label') or '').strip(),
        }
        if len(self.records) >= MAX_DERIVED:
            raise DerivationError('派生事实数量超出上限 %d' % MAX_DERIVED)
        self._index[rid] = entry
        self.records.append(entry)
        if not _defer:
            self.order, self.cycles = self._topological()
        return entry

    def remove(self, rid: str):
        if rid not in self._index:
            raise DerivationError('派生事实不存在：%s' % rid)
        users = [r['id'] for r in self.records if rid in r['inputs']]
        if users:
            raise DerivationError('「%s」仍被派生事实引用：%s' % (rid, '、'.join(users)))
        self.records = [r for r in self.records if r['id'] != rid]
        self._index.pop(rid, None)
        self.order, self.cycles = self._topological()

    def validate(self, base_ids):
        """校验引用完整性。返回问题清单，空列表表示通过。"""
        problems = []
        known = set(base_ids) | set(self._index)
        for record in self.records:
            for source in record['inputs']:
                if source == record['id']:
                    problems.append('%s 引用了自己' % record['id'])
                elif source not in known:
                    problems.append('%s 引用了不存在的事实 %s' % (record['id'], source))
            if record['op'] == 'sum' and len(record['inputs']) < 2:
                problems.append('%s 的合计至少需要两个事实' % record['id'])
        for cycle in self.cycles:
            problems.append('存在循环依赖：%s' % ' → '.join(cycle + [cycle[0]]))
        return problems

    # ---- 图算法 -----------------------------------------------------------
    def _topological(self):
        """Kahn 拓扑排序；无法排空的部分即为环依赖。

        返回 (有序ID列表, 环清单)。顺序保证任何派生事实都排在其来源之后。
        """
        indegree = {r['id']: 0 for r in self.records}
        dependents = {r['id']: [] for r in self.records}
        for record in self.records:
            for source in record['inputs']:
                if source in indegree:
                    indegree[record['id']] += 1
                    dependents[source].append(record['id'])
        ready = [r['id'] for r in self.records if indegree[r['id']] == 0]
        order = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            for nxt in dependents[current]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
        cycles = []
        leftover = [rid for rid in indegree if indegree[rid] > 0]
        while leftover:
            start = leftover[0]
            path, seen, node = [], {}, start
            while node is not None and node not in seen:
                seen[node] = len(path)
                path.append(node)
                node = next((s for s in self._index[node]['inputs'] if s in indegree and indegree[s] > 0), None)
            if node is not None and node in seen:
                cycle = path[seen[node]:]
                cycles.append(cycle)
                leftover = [x for x in leftover if x not in cycle]
            else:
                leftover = [x for x in leftover if x != start]
        return order, cycles

    def reachable(self, changed_ids, limit=MAX_REACH):
        """从变化的事实出发，返回所有直接或间接受影响的派生事实ID（按拓扑序）。"""
        frontier = list(changed_ids)
        seen = set()
        while frontier:
            current = frontier.pop()
            for record in self.records:
                if current in record['inputs'] and record['id'] not in seen:
                    seen.add(record['id'])
                    frontier.append(record['id'])
                    if len(seen) > limit:
                        raise DerivationError('依赖传播规模超出上限 %d' % limit)
        return [rid for rid in self.order if rid in seen]

    def dependents_of(self, fact_id):
        return [r['id'] for r in self.records if fact_id in r['inputs']]


def _render(op, inputs):
    if op not in OPERATIONS:
        raise DerivationError('不支持的运算：%s' % op)
    return '%s(%s)' % (op, ', '.join(inputs or []))


def compute(base_facts, derivations, changed=(), overrides=None, previous=None):
    """按拓扑序重算派生事实。

    参数：
        changed    本次变化的基础事实ID
        overrides  基础事实ID → 新数值
        previous   上一轮的值表（values），用于判定派生值是否真的发生了变化

    返回 dict：
        facts        基础事实与派生事实合并后的新列表（派生事实追加在后面）
        values       事实ID → 本轮值（含基础事实）
        details      派生事实ID → 计算说明
        errors       派生事实ID → 无法计算的原因
        changed      数值真正发生变化的派生事实ID（与 previous 对比）
        affected     所有受影响的派生事实ID（含未变化者，按拓扑序）
        radius       影响半径：受影响节点数 ÷ 全图节点数
    """
    overrides = dict(overrides or {})
    # previous 允许传「值字典」或「事实列表」；两种写法都不应让调用方踩坑。
    if isinstance(previous, (list, tuple)):
        previous = {f['id']: f.get('value') for f in previous if isinstance(f, dict) and 'id' in f}
    base = []
    for fact in base_facts:
        item = dict(fact)
        if item['id'] in overrides:
            item['value'] = overrides[item['id']]
        base.append(item)
    byid = {f['id']: f for f in base}

    values, details, errors, derived_facts, computed = {}, {}, {}, [], {}
    for rid in derivations.order:
        record = derivations._index[rid]
        try:
            sources = []
            for source in record['inputs']:
                if source in byid:
                    sources.append(byid[source])
                elif source in errors:
                    raise DerivationError('来源 %s 无法计算，本项一并转人工复核' % source)
                elif source in computed:
                    sources.append(computed[source])
                else:
                    raise DerivationError('引用了不存在的事实 %s' % source)
            value, unit, detail = eval_expr(record['op'], sources)
            if record['unit'] and record['unit'] != unit:
                raise DerivationError('产出单位是 %s，与声明的 %s 不一致' % (unit, record['unit']))
            values[rid] = value
            details[rid] = detail
            first = sources[0]
            computed[rid] = {
                'id': rid, 'subject': first['subject'], 'metric': record['label'] or first['metric'],
                'period': first['period'], 'value': value, 'unit': unit, 'scope': first['scope'],
                'derived': True, 'op': record['op'], 'inputs': record['inputs'],
                'sheet': first.get('sheet', ''), 'cell': first.get('cell', ''),
            }
            derived_facts.append(computed[rid])
        except DerivationError as exc:
            errors[rid] = str(exc)
            values[rid] = None

    known_ids = set(byid) | set(values)
    before = dict(previous or {})
    for fid, fact in byid.items():
        before.setdefault(fid, fact.get('value'))

    def _moved(rid):
        old, new = before.get(rid, _MISSING), values.get(rid)
        if old is _MISSING or new is None:
            return new is not None
        try:
            return number(old) != new
        except (InvalidOperation, ValueError, TypeError):
            return True

    changed_derived = [rid for rid in derivations.order if rid in known_ids and _moved(rid)]
    affected = derivations.reachable(changed) if changed else []
    total_nodes = len(base) + len(derivations.records)
    return {
        'facts': base + derived_facts,
        'values': {**{f['id']: f.get('value') for f in base}, **values},
        'details': details,
        'errors': errors,
        'changed': changed_derived,
        'affected': affected,
        'radius': (len(affected) / total_nodes) if total_nodes else 0.0,
    }


def impact(derivations, claims, changed_ids):
    """给定变化的事实，返回受影响的论断分组。

    - 直接受影响：论断的 refs 命中变化事实
    - 间接受影响：论断的 refs 命中受影响派生事实
    """
    affected = set(derivations.reachable(changed_ids))
    direct, indirect = [], []
    for claim in claims:
        refs = set(claim.get('refs') or [])
        if refs & set(changed_ids):
            direct.append(claim['id'])
        elif refs & affected:
            indirect.append(claim['id'])
    return {'direct': direct, 'indirect': indirect,
            'affected_facts': sorted(affected), 'total': len(direct) + len(indirect)}
