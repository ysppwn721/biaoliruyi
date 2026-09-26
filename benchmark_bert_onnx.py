import time
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parent
t = Tokenizer.from_file(str(ROOT / 'models' / 'zh_reranker_bert_ft_v2_onnx' / 'tokenizer.json'))
t.enable_padding(pad_id=0, pad_token='<pad>')
pairs = [('本期营业收入为100万元', 'subject=华北能源01号；metric=营业收入；period=2025年；unit=万元；scope=合并口径')] * 16
e = t.encode_batch(pairs)
x = {'input_ids': np.asarray([a.ids for a in e], dtype=np.int64),
     'attention_mask': np.asarray([a.attention_mask for a in e], dtype=np.int64),
     'token_type_ids': np.asarray([a.type_ids for a in e], dtype=np.int64)}
s = ort.InferenceSession(str(ROOT / 'models' / 'zh_reranker_bert_ft_v2_onnx' / 'model_fp32.onnx'), providers=['CPUExecutionProvider'])
for _ in range(2):
    s.run(None, x)
times = []
for _ in range(10):
    start = time.perf_counter()
    s.run(None, x)
    times.append(time.perf_counter() - start)
median = float(np.median(times)) * 1000
print({'batch16_median_ms': round(median, 2), 'per_pair_ms': round(median / 16, 2)})
