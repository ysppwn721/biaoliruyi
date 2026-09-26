from pathlib import Path
OUT=Path(__file__).resolve().parent/'真实年报外部验证对比.svg'
W,H=1050,580; left,bottom,top=150,105,80; ph=330
data=[('BERT v2',25.00,'#c85a54'),('BGE ONNX',96.67,'#0b6e99')]
parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">','<rect width="100%" height="100%" fill="#fbfcfe"/>','<text x="70" y="42" font-family="Microsoft YaHei" font-size="26" font-weight="600" fill="#172033">真实年报程序化外部验证</text>','<text x="70" y="68" font-family="Microsoft YaHei" font-size="14" fill="#536174">5 份公开年报 · 60 条论断 · 180 个候选对 · 未参与训练</text>']
for i in range(6):
 v=i*20;y=H-bottom-v/100*ph;parts += [f'<line x1="{left}" y1="{y:.1f}" x2="{W-60}" y2="{y:.1f}" stroke="#dfe5ed"/>',f'<text x="{left-12}" y="{y+5:.1f}" text-anchor="end" font-family="Arial" font-size="13" fill="#536174">{v}%</text>']
for i,(label,val,color) in enumerate(data):
 x=left+130+i*400;y=H-bottom-val/100*ph;h=H-bottom-y
 parts += [f'<rect x="{x}" y="{y:.1f}" width="240" height="{h:.1f}" rx="8" fill="{color}"/>',f'<text x="{x+120}" y="{max(y-14,95):.1f}" text-anchor="middle" font-family="Arial" font-size="24" font-weight="600" fill="#172033">{val:.2f}%</text>',f'<text x="{x+120}" y="{H-bottom+35}" text-anchor="middle" font-family="Microsoft YaHei" font-size="17" fill="#172033">{label}</text>']
parts += ['<text x="70" y="535" font-family="Microsoft YaHei" font-size="13" fill="#b04a3a">结论：BERT v2 在项目合成数据上高分，但真实年报外部验证仅25%；BGE ONNX 暂保留为线上默认。</text>','</svg>']
OUT.write_text('\n'.join(parts),encoding='utf-8');print(OUT)
