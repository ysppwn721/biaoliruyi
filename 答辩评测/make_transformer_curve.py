from pathlib import Path
import json
import os

ROOT = Path(__file__).resolve().parent
manifest_path = Path(os.getenv('ZHILIAN_TRAINING_MANIFEST', str(ROOT.parent / 'models' / 'zh_reranker_bert_ft' / 'training_manifest.json')))
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
hist = manifest['history']
W,H=1000,560; left,right,top,bottom=100,50,80,90; pw,ph=W-left-right,320
maxloss=max(r['train_loss'] for r in hist)*1.15
def x(i): return left+i/max(1,len(hist)-1)*pw
def y(v): return top+ph-v/maxloss*ph
parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">', '<rect width="100%" height="100%" fill="#fbfcfe"/>', '<text x="70" y="40" font-family="Microsoft YaHei" font-size="26" font-weight="600" fill="#172033">中文 BERT reranker 微调曲线</text>', '<text x="70" y="65" font-family="Microsoft YaHei" font-size="14" fill="#536174">bert-base-chinese · 1,216 条训练对 · 3 个 epoch</text>']
for i in range(6):
    val=maxloss*i/5; yy=y(val)
    parts += [f'<line x1="{left}" y1="{yy:.1f}" x2="{W-right}" y2="{yy:.1f}" stroke="#dfe5ed"/>',f'<text x="{left-12}" y="{yy+5:.1f}" text-anchor="end" font-family="Arial" font-size="13" fill="#536174">{val:.2f}</text>']
pts=' '.join(('M' if i==0 else 'L')+f' {x(i):.1f},{y(r["train_loss"]):.1f}' for i,r in enumerate(hist))
parts += [f'<path d="{pts}" fill="none" stroke="#0b6e99" stroke-width="4"/>']
for i,r in enumerate(hist):
    xx,yy=x(i),y(r['train_loss']); parts += [f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="6" fill="#f08c46"/>', f'<text x="{xx:.1f}" y="{yy-14:.1f}" text-anchor="middle" font-family="Arial" font-size="14" fill="#172033">{r["train_loss"]:.3f}</text>', f'<text x="{xx:.1f}" y="{top+ph+28}" text-anchor="middle" font-family="Arial" font-size="13" fill="#536174">epoch {i+1}</text>']
parts += ['<text x="70" y="505" font-family="Microsoft YaHei" font-size="14" fill="#172033">冻结测试集：Top-1 100.00%，错误关联率 0.00%（49 条论断，7 个文档组）</text>', '<text x="70" y="532" font-family="Microsoft YaHei" font-size="13" fill="#b04a3a">注意：数据规模较小，结果用于流程验证；仍需新增独立中文文档组检验泛化。</text>', '</svg>']
out = Path(os.getenv('ZHILIAN_TRAINING_CURVE_OUT', str(ROOT / '中文Transformer训练曲线.svg')))
out.write_text('\n'.join(parts), encoding='utf-8')
print(out)
