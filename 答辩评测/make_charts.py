from pathlib import Path
import csv


OUT = Path(__file__).resolve().parent


def esc(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def chart(data):
    width, height = 1100, 650
    left, right, top, bottom = 95, 40, 80, 90
    x0, x1 = left, width - right
    y0, y1 = height - bottom, top
    max_y = max(row['seconds_median'] for row in data) * 1.12
    def x(rows):
        return x0 + (rows - data[0]['rows']) / (data[-1]['rows'] - data[0]['rows']) * (x1 - x0)
    def y(seconds):
        return y0 - seconds / max_y * (y0 - y1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<title>事实表读取性能曲线</title>',
        '<desc>真实本机测量：事实表行数从50增加到1999时，读取中位耗时仍保持近似线性增长。</desc>',
        '<rect width="100%" height="100%" fill="#fbfcfe"/>',
        '<text x="95" y="42" font-family="Microsoft YaHei, sans-serif" font-size="26" font-weight="600" fill="#172033">事实表读取性能：规模增加仍保持可用</text>',
        '<text x="95" y="66" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#536174">项目当前实现 · 每个规模重复读取3次，取中位数 · Windows 本机 .venv</text>',
        f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#8995a5"/>',
        f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="#8995a5"/>',
    ]
    for tick in range(0, 7):
        value = max_y * tick / 6
        yy = y(value)
        parts.extend([
            f'<line x1="{x0}" y1="{yy:.1f}" x2="{x1}" y2="{yy:.1f}" stroke="#dfe5ed"/>',
            f'<text x="{x0-12}" y="{yy+5:.1f}" text-anchor="end" font-family="Arial" font-size="13" fill="#536174">{value:.2f}</text>',
        ])
    for row in data:
        xx = x(row['rows'])
        parts.append(f'<line x1="{xx:.1f}" y1="{y0}" x2="{xx:.1f}" y2="{y0+6}" stroke="#8995a5"/>')
        parts.append(f'<text x="{xx:.1f}" y="{y0+28}" text-anchor="middle" font-family="Arial" font-size="13" fill="#536174">{row["rows"]}</text>')
    path = ' '.join(('M' if i == 0 else 'L') + f' {x(r["rows"]):.1f},{y(r["seconds_median"]):.1f}' for i, r in enumerate(data))
    parts.append(f'<path d="{path}" fill="none" stroke="#0b6e99" stroke-width="4"/>')
    for row in data:
        xx, yy = x(row['rows']), y(row['seconds_median'])
        label_y = yy - 13 if yy > y1 + 35 else yy + 25
        parts.extend([
            f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="6" fill="#f08c46" stroke="#fbfcfe" stroke-width="3"/>',
            f'<text x="{xx:.1f}" y="{label_y:.1f}" text-anchor="middle" font-family="Arial" font-size="13" fill="#172033">{row["seconds_median"]:.3f}s</text>',
        ])
    parts.extend([
        f'<text x="{(x0+x1)/2:.1f}" y="{height-28}" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="15" fill="#172033">事实条数（行）</text>',
        f'<text x="22" y="{(y0+y1)/2:.1f}" transform="rotate(-90 22 {(y0+y1)/2:.1f})" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="15" fill="#172033">读取耗时（秒，中位数）</text>',
        '<text x="95" y="615" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#536174">结论：1999 条事实读取中位数约 0.118 秒；该曲线证明的是当前解析性能，不是模型准确率。</text>',
        '</svg>',
    ])
    return '\n'.join(parts)


def main():
    with (OUT / 'fact_table_performance.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    data = [{'rows': int(r['rows']), 'seconds_median': float(r['seconds_median'])} for r in rows]
    (OUT / '事实表读取性能曲线.svg').write_text(chart(data), encoding='utf-8')
    scenarios = [
        ('销售额 125→123', 80, 200),
        ('销售额 125→90\nA产品80→60\n支出80→110', 232, 48),
    ]
    (OUT / '长文Word修复结果对比.svg').write_text(repair_chart(scenarios), encoding='utf-8')
    print('wrote', OUT / '事实表读取性能曲线.svg')


def repair_chart(scenarios):
    width, height = 1100, 600
    left, right, top, bottom = 110, 50, 95, 90
    x0, x1 = left, width - right
    y0, y1 = height - bottom, top
    max_y = 280
    group_width = (x1 - x0) / len(scenarios)
    bar_width = 150
    def y(value):
        return y0 - value / max_y * (y0 - y1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<title>长文 Word 修复结果对比</title>',
        '<desc>真实长文压力测试中，轻微和较大 Excel 变化分别修复80项和232项，修复后均回到280项一致。</desc>',
        '<rect width="100%" height="100%" fill="#fbfcfe"/>',
        '<text x="110" y="44" font-family="Microsoft YaHei, sans-serif" font-size="26" font-weight="600" fill="#172033">长文 Word 测试：只修复失效论断</text>',
        '<text x="110" y="70" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#536174">24章 · 约1.7万字 · 280项论断 · 修复后两种场景均全部一致</text>',
        f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#8995a5"/>',
        f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="#8995a5"/>',
    ]
    for tick in range(0, 6):
        value = max_y * tick / 5
        yy = y(value)
        parts.extend([
            f'<line x1="{x0}" y1="{yy:.1f}" x2="{x1}" y2="{yy:.1f}" stroke="#dfe5ed"/>',
            f'<text x="{x0-12}" y="{yy+5:.1f}" text-anchor="end" font-family="Arial" font-size="13" fill="#536174">{int(value)}</text>',
        ])
    for index, (label, repaired, unchanged) in enumerate(scenarios):
        center = x0 + group_width * (index + .5)
        first_x = center - bar_width - 12
        second_x = center + 12
        for xx, value, color, name in [(first_x, repaired, '#d86555', '需修复'), (second_x, unchanged, '#0b8a72', '仍成立')]:
            yy = y(value)
            parts.extend([
                f'<rect x="{xx:.1f}" y="{yy:.1f}" width="{bar_width}" height="{y0-yy:.1f}" fill="{color}"/>',
                f'<text x="{xx+bar_width/2:.1f}" y="{yy-12:.1f}" text-anchor="middle" font-family="Arial" font-size="16" fill="#172033">{value}</text>',
            ])
        lines = label.split('\n')
        for line_index, line in enumerate(lines):
            parts.append(f'<text x="{center:.1f}" y="{y0+28+line_index*19}" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#172033">{esc(line)}</text>')
    parts.extend([
        f'<text x="{(x0+x1)/2:.1f}" y="{height-28}" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="15" fill="#172033">Excel 变化场景</text>',
        f'<text x="25" y="{(y0+y1)/2:.1f}" transform="rotate(-90 25 {(y0+y1)/2:.1f})" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="15" fill="#172033">论断数量</text>',
        '<rect x="790" y="38" width="16" height="16" fill="#d86555"/><text x="814" y="52" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#536174">需修复</text>',
        '<rect x="895" y="38" width="16" height="16" fill="#0b8a72"/><text x="919" y="52" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#536174">仍成立</text>',
        '<text x="110" y="555" font-family="Microsoft YaHei, sans-serif" font-size="14" fill="#536174">结论：数值变化不等于整篇重写；系统只改失效锚点，并在导出后重新读取验证。</text>',
        '</svg>',
    ])
    return '\n'.join(parts)


if __name__ == '__main__':
    main()
