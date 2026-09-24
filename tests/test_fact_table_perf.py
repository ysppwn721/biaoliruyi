"""事实表读取：坐标正确性与行数扩展性回归。

背景：在 load_workbook(read_only=True) 下每行调用 sheet.cell() 会重新解析
工作表 XML，整体是 O(行数²)。实测 800 行约 19 秒、1999 行约 2 分钟，
接近产品宣称的 2000 行上限时用户会以为程序卡死。改用列字母拼坐标后
降到毫秒级，坐标字符串完全一致。本文件锁定该行为。
"""
import time

from openpyxl import Workbook

from zhilian.office import HEADERS, read_facts


def build(path, rows, columns_order=HEADERS, value_column='数值'):
    wb = Workbook()
    sheet = wb.active
    sheet.title = '事实表'
    sheet.append(columns_order)
    for i in range(rows):
        record = {h: '' for h in columns_order}
        record.update({'事实ID': f'f{i}', '主体': '主体甲', '指标': '销售额',
                       '期间': '本期', '数值': 100 + i, '单位': '万元', '统计口径': '口径A'})
        sheet.append([record[h] for h in columns_order])
    wb.save(path)
    return path


def test_cell_coordinate_matches_column_and_row(tmp_path):
    path = build(tmp_path / 'f.xlsx', 3)
    facts = read_facts(path, 'F')
    assert [f['cell'] for f in facts] == ['E2', 'E3', 'E4']
    assert [f['id'] for f in facts] == ['f0', 'f1', 'f2']


def test_cell_coordinate_follows_neither_row_order_nor_column_position(tmp_path):
    """列顺序变化时坐标仍应指向"数值"所在列。"""
    # 把"数值"从默认第 5 列挪到第 2 列（B 列）
    order = ['事实ID', '数值', '主体', '指标', '期间', '单位', '统计口径']
    assert order.index('数值') != HEADERS.index('数值')
    path = build(tmp_path / 'g.xlsx', 5, order)
    facts = read_facts(path, 'F')
    assert [f['cell'] for f in facts] == [f'B{r}' for r in range(2, 7)]
    assert facts[0]['value'] == 100.0


def test_numeric_value_column_beyond_e_uses_two_letters(tmp_path):
    """数值列落在第 27 列时应给出 AA2 这样的坐标，而不是越界或错列。"""
    filler = [f'填充{i}' for i in range(25)]
    order = filler + ['事实ID', '数值', '主体', '指标', '期间', '单位', '统计口径']
    # A—Y 为填充列，Z 为事实ID，第 27 列 AA 才是数值
    assert order.index('数值') == 26
    path = build(tmp_path / 'h.xlsx', 2, order)
    facts = read_facts(path, 'F')
    assert [f['cell'] for f in facts] == ['AA2', 'AA3']


def test_large_fact_table_loads_in_linear_time(tmp_path):
    """1999 行（产品上限）必须秒级完成；原实现约 2 分钟。"""
    path = build(tmp_path / 'big.xlsx', 1999)
    start = time.perf_counter()
    facts = read_facts(path, 'F')
    elapsed = time.perf_counter() - start
    assert len(facts) == 1999
    assert facts[0]['cell'] == 'E2' and facts[-1]['cell'] == 'E2000'
    # 阈值取得很宽松：正确实现约 0.12s，平方级实现约 120s，两者相差千倍
    assert elapsed < 10, f'1999 行耗时 {elapsed:.1f}s，疑似退化为 O(行数²)'
