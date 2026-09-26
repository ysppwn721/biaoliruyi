from pathlib import Path

OUT = Path(__file__).resolve().parent / '中文reranker指标对比.svg'
W,H=1000,560
data=[('规则基线',75.51,'#536174'),('字符级训练',75.51,'#0b6e99'),('BERT微调',100.00,'#f08c46')]
left, bottom, top = 160, 100, 80
bar_w, gap = 230, 110
parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">',
       '<rect width="100%" height="100%" fill="#fbfcfe"/>',
       '<text x="70" y="44" font-family="Microsoft YaHei" font-size="26" font-weight="600" fill="#172033">冻结测试集 Top-1 对比</text>',
       '<text x="70" y="68" font-family="Microsoft YaHei" font-size="14" fill="#536174">同一 7 个文档组、49 条论断 · 第一轮中文学习基线</text>']
chart_h=H-top-bottom
for tick in range(0,6):
    v=tick*20; y=H-bottom-v/100*chart_h
    parts += [f'<line x1="{left}" y1="{y:.1f}" x2="{W-70}" y2="{y:.1f}" stroke="#dfe5ed"/>', f'<text x="{left-12}" y="{y+5:.1f}" text-anchor="end" font-family="Arial" font-size="13" fill="#536174">{v}%</text>']
for i,(label,val,color) in enumerate(data):
    x=left+20+i*(bar_w+gap); y=H-bottom-val/100*chart_h; h=H-bottom-y
    parts += [f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" rx="8" fill="{color}"/>', f'<text x="{x+bar_w/2}" y="{y-14:.1f}" text-anchor="middle" font-family="Arial" font-size="24" font-weight="600" fill="#172033">{val:.2f}%</text>', f'<text x="{x+bar_w/2}" y="{H-bottom+35}" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" fill="#172033">{label}</text>']
parts += ['<text x="70" y="530" font-family="Microsoft YaHei" font-size="13" fill="#536174">结论：BERT 微调在当前冻结测试集上达到100%，仍需新增独立文档组验证泛化。</text>', '</svg>']
OUT.write_text('\n'.join(parts),encoding='utf-8')
print(OUT)
