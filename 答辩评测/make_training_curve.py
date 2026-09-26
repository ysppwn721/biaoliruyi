"""Render the lightweight Chinese reranker training history as an SVG."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
history = json.loads((ROOT / "char_reranker_results" / "metrics.json").read_text(encoding="utf-8"))["history"]
W, H = 1100, 680
left, right, top, bottom = 100, 50, 80, 70
plot_w, plot_h = W-left-right, 220

def path(values, ytop, ymax):
    pts=[]
    for i, val in enumerate(values):
        x=left + i/(len(values)-1)*(plot_w)
        y=ytop+plot_h-(val/ymax)*plot_h
        pts.append((x,y))
    return ' '.join(('M' if i==0 else 'L')+f' {x:.1f},{y:.1f}' for i,(x,y) in enumerate(pts))

loss_max=max(max(r['train_loss'],r['dev_loss'],r['test_loss']) for r in history)*1.05
acc_max=1.0
parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">',
       '<rect width="100%" height="100%" fill="#fbfcfe"/>',
       '<text x="100" y="38" font-family="Microsoft YaHei" font-size="26" font-weight="600" fill="#172033">中文轻量 reranker 训练曲线</text>',
       '<text x="100" y="62" font-family="Microsoft YaHei" font-size="14" fill="#536174">14个训练文档组 · 4个开发文档组 · 7个冻结测试文档组</text>']
for top_y, title, series, ymax in [(90,'损失曲线',[('train_loss','#0b6e99'),('dev_loss','#f08c46'),('test_loss','#7a5af8')],loss_max),(390,'Top-1准确率',[('dev.top1_accuracy','#0b6e99'),('test.top1_accuracy','#f08c46')],acc_max)]:
    parts.append(f'<text x="{left}" y="{top_y-18}" font-family="Microsoft YaHei" font-size="18" fill="#172033">{title}</text>')
    for tick in range(6):
        value=ymax*tick/5; y=top_y+plot_h-(value/ymax)*plot_h
        parts += [f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_w}" y2="{y:.1f}" stroke="#dfe5ed"/>',
                  f'<text x="{left-12}" y="{y+5:.1f}" text-anchor="end" font-family="Arial" font-size="12" fill="#536174">{value:.2f}</text>']
    for i in range(len(history)):
        x=left+i/(len(history)-1)*plot_w
        parts.append(f'<text x="{x:.1f}" y="{top_y+plot_h+24}" text-anchor="middle" font-family="Arial" font-size="12" fill="#536174">{i+1}</text>')
    for key,color in series:
        vals=[]
        for row in history:
            obj=row
            for part in key.split('.'):
                obj=obj[part]
            vals.append(float(obj))
        parts.append(f'<path d="{path(vals,top_y,ymax)}" fill="none" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{left+plot_w-5}" y="{top_y+18+series.index((key,color))*18}" text-anchor="end" font-family="Arial" font-size="13" fill="{color}">{key}</text>')
parts += ['<text x="100" y="665" font-family="Microsoft YaHei" font-size="13" fill="#536174">说明：该曲线来自字符级本地学习基线；Transformer 微调模型需另行下载 PyTorch 基础权重。</text>', '</svg>']
(ROOT / '中文reranker训练曲线.svg').write_text('\n'.join(parts), encoding='utf-8')
print(ROOT / '中文reranker训练曲线.svg')
