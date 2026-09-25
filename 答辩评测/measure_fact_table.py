from pathlib import Path
import csv
import statistics
import sys
import time

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zhilian.office import HEADERS, read_facts


OUT = Path(__file__).resolve().parent
ROWS = [50, 100, 250, 500, 1000, 1500, 1999]


def make_book(path: Path, rows: int) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = '事实表'
    sheet.append(HEADERS)
    for index in range(rows):
        sheet.append([f'f{index}', '主体甲', '销售额', '本期', 100 + index, '万元', '口径A'])
    workbook.save(path)
    workbook.close()


def main() -> None:
    records = []
    for rows in ROWS:
        path = OUT / f'fact_table_{rows}.xlsx'
        make_book(path, rows)
        samples = []
        for _ in range(3):
            started = time.perf_counter()
            facts = read_facts(path, 'bench')
            samples.append(time.perf_counter() - started)
        records.append({
            'rows': rows,
            'seconds_median': round(statistics.median(samples), 6),
            'seconds_min': round(min(samples), 6),
            'facts': len(facts),
        })
    with (OUT / 'fact_table_performance.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0])
        writer.writeheader()
        writer.writerows(records)
    print(records)


if __name__ == '__main__':
    main()
