"""Export the trained Chinese BERT reranker to ONNX and create an INT8 copy."""
from __future__ import annotations
import json
from pathlib import Path
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / 'models' / 'zh_reranker_bert_ft_v2'
OUT = ROOT / 'models' / 'zh_reranker_bert_ft_v2_onnx'
OUT.mkdir(parents=True, exist_ok=True)
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForSequenceClassification.from_pretrained(MODEL)
model.eval()
model.config.return_dict = False
sample = tok(['本期营业收入为100万元'],
             ['subject=华北能源01号；metric=营业收入；period=2025年；unit=万元；scope=合并口径'],
             padding=True, truncation=True, max_length=64, return_tensors='pt')
names = tuple(k for k in ('input_ids', 'attention_mask', 'token_type_ids') if k in sample)
inputs = tuple(sample[k] for k in names)
onnx_path = OUT / 'model_fp32.onnx'
dynamic = {k: {0: 'batch', 1: 'sequence'} for k in names}
dynamic['logits'] = {0: 'batch'}
torch.onnx.export(model, inputs, onnx_path, input_names=list(names),
                  output_names=['logits'], dynamic_axes=dynamic, opset_version=17)
try:
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8_path = OUT / 'model_int8.onnx'
    quantize_dynamic(str(onnx_path), str(int8_path), weight_type=QuantType.QInt8)
except Exception as exc:
    int8_path = None
tok.save_pretrained(OUT)
manifest = {'source_model': str(MODEL), 'fp32': str(onnx_path),
            'int8': str(int8_path) if int8_path else None, 'input_names': list(names)}
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(manifest, ensure_ascii=False))
