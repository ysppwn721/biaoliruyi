from pathlib import Path

OUT = Path(__file__).resolve().parent / "真实年报外部验证对比_36份.svg"
W, H = 1050, 580
left, bottom = 150, 105
plot_h = 330
data = [("BERT v2", 41.32, "#c85a54"), ("BGE ONNX", 96.18, "#0b6e99")]
parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">',
    '<rect width="100%" height="100%" fill="#fbfcfe"/>',
    '<text x="70" y="42" font-family="Microsoft YaHei" font-size="26" font-weight="600" fill="#172033">真实年报 PDF 外部验证</text>',
    '<text x="70" y="68" font-family="Microsoft YaHei" font-size="14" fill="#536174">36 份公开年报 · 576 条论断 · 1,728 个候选对 · 未参与训练</text>',
]
for tick in range(0, 101, 20):
    y = H - bottom - tick / 100 * plot_h
    parts += [
        f'<line x1="{left}" y1="{y:.1f}" x2="{W - 60}" y2="{y:.1f}" stroke="#dfe5ed"/>',
        f'<text x="{left - 12}" y="{y + 5:.1f}" text-anchor="end" font-family="Arial" font-size="13" fill="#536174">{tick}%</text>',
    ]
for i, (label, value, color) in enumerate(data):
    x = left + 130 + i * 400
    y = H - bottom - value / 100 * plot_h
    height = H - bottom - y
    parts += [
        f'<rect x="{x}" y="{y:.1f}" width="240" height="{height:.1f}" rx="8" fill="{color}"/>',
        f'<text x="{x + 120}" y="{max(y - 14, 95):.1f}" text-anchor="middle" font-family="Arial" font-size="24" font-weight="600" fill="#172033">{value:.2f}%</text>',
        f'<text x="{x + 120}" y="{H - bottom + 35}" text-anchor="middle" font-family="Microsoft YaHei" font-size="17" fill="#172033">{label}</text>',
    ]
parts += [
    '<text x="70" y="535" font-family="Microsoft YaHei" font-size="13" fill="#b04a3a">程序化标签来自 PDF 文本层与相邻财务字段，不能替代人工真值；BGE 保持线上默认。</text>',
    '</svg>',
]
OUT.write_text("\n".join(parts), encoding="utf-8")
print(OUT)
