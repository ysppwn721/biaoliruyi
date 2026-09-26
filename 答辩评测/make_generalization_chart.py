from pathlib import Path

OUT = Path(__file__).resolve().parent / '中文模型泛化验证对比.svg'
W,H=1050,580; left,bottom,top=150,105,80; pw=W-left-60; ph=330
data=[('BERT微调\n独立合成集',0.00,'#f08c46'),('BGE ONNX\n独立合成集',56.67,'#0b6e99')]
parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">','<rect width="100%" height="100%" fill="#fbfcfe"/>','<text x="70" y="42" font-family="Microsoft YaHei" font-size="26" font-weight="600" fill="#172033">独立文档组泛化验证</text>','<text x="70" y="68" font-family="Microsoft YaHei" font-size="14" fill="#536174">12 个全新合成文档组 · 60 条论断 · 不参与训练和冻结测试</text>']
for i in range(6):
    v=i*20; y=H-bottom-v/100*ph; parts += [f'<line x1="{left}" y1="{y:.1f}" x2="{W-60}" y2="{y:.1f}" stroke="#dfe5ed"/>', f'<text x="{left-12}" y="{y+5:.1f}" text-anchor="end" font-family="Arial" font-size="13" fill="#536174">{v}%</text>']
for i,(label,val,color) in enumerate(data):
    x=left+100+i*380; y=H-bottom-val/100*ph; h=H-bottom-y
    parts += [f'<rect x="{x}" y="{y:.1f}" width="240" height="{h:.1f}" rx="8" fill="{color}"/>', f'<text x="{x+120}" y="{max(y-14,95):.1f}" text-anchor="middle" font-family="Arial" font-size="24" font-weight="600" fill="#172033">{val:.2f}%</text>']
    for j,line in enumerate(label.split('\\n')): parts.append(f'<text x="{x+120}" y="{H-bottom+30+j*21}" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" fill="#172033">{line}</text>')
parts += ['<text x="70" y="535" font-family="Microsoft YaHei" font-size="13" fill="#b04a3a">结论：BERT 在当前训练分布内表现很好，但独立组合上的泛化为0%，说明需要扩大训练文档组并重新训练。</text>','</svg>']
OUT.write_text('\n'.join(parts),encoding='utf-8')
print(OUT)
