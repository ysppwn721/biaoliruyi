from pathlib import Path
OUT=Path(__file__).resolve().parent/'中文模型迭代泛化对比.svg'
W,H=1100,600; left,bottom,top=150,105,80; ph=350
data=[('BERT v1\n独立组合',0.0,'#c85a54'),('BERT v2\n新增组合',100.0,'#0b6e99'),('BERT v2\n压力集',87.5,'#f08c46')]
parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">','<rect width="100%" height="100%" fill="#fbfcfe"/>','<text x="70" y="42" font-family="Microsoft YaHei" font-size="26" font-weight="600" fill="#172033">中文模型迭代后的泛化验证</text>','<text x="70" y="68" font-family="Microsoft YaHei" font-size="14" fill="#536174">v2 增加 48 个训练文档组和 12 个开发文档组，测试集保持冻结</text>']
for i in range(6):
 v=i*20;y=H-bottom-v/100*ph;parts += [f'<line x1="{left}" y1="{y:.1f}" x2="{W-60}" y2="{y:.1f}" stroke="#dfe5ed"/>',f'<text x="{left-12}" y="{y+5:.1f}" text-anchor="end" font-family="Arial" font-size="13" fill="#536174">{v}%</text>']
for i,(label,val,color) in enumerate(data):
 x=left+30+i*300;y=H-bottom-val/100*ph;h=H-bottom-y
 parts += [f'<rect x="{x}" y="{y:.1f}" width="210" height="{h:.1f}" rx="8" fill="{color}"/>',f'<text x="{x+105}" y="{max(y-14,95):.1f}" text-anchor="middle" font-family="Arial" font-size="23" font-weight="600" fill="#172033">{val:.2f}%</text>']
 for j,line in enumerate(label.split('\\n')): parts.append(f'<text x="{x+105}" y="{H-bottom+30+j*21}" text-anchor="middle" font-family="Microsoft YaHei" font-size="15" fill="#172033">{line}</text>')
parts += ['<text x="70" y="555" font-family="Microsoft YaHei" font-size="13" fill="#536174">结论：扩充训练组后，模型从独立组合失效恢复到压力集87.5%，但仍需真实文档组复核。</text>','</svg>']
OUT.write_text('\n'.join(parts),encoding='utf-8');print(OUT)
