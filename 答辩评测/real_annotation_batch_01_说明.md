# 真实评测人工标注批次 01

本批次包含长文夹具前 5 个文档组、64 条候选论断。当前所有样本仍是 `adjudicated=false` 的待标注项；它们不能用于训练或最终测试。

## 两名标注者分别填写

每名标注者复制 `real_annotation_batch_01.jsonl`，文件名建议为 `real_annotation_batch_01_A.jsonl` 和 `real_annotation_batch_01_B.jsonl`，只修改以下字段：

- `gold_action`：`link` 或 `abstain`。
- `gold_refs`：按事实表 ID 填写来源；增长率、排名、阈值等可填写多个 ID。
- `category`：`ordinary`、`ambiguous` 或 `adversarial`。
- `annotator_id`：填写自己的标识，例如 `annotator_A`。
- `annotation_note`：标注理由，尤其记录口径冲突、缺失事实和无法唯一匹配。

不得根据 `real_eval_dataset.jsonl` 的已有标签抄写答案。标注者只看原始 Word、Excel 和候选元数据。

## 仲裁规则

两份结果一致时，第三人或负责人将 `adjudicated` 改为 `true` 并保留两名标注者标识；不一致时记录分歧和最终决定，不能静默覆盖。只有完成仲裁的样本才能进入正式 dev/test 或训练集。

可用项目脚本自动合并并显式列出分歧：

```powershell
.\.venv\Scripts\python.exe 答辩评测\merge_annotations.py `
  --a 答辩评测\real_annotation_batch_01_A.jsonl `
  --b 答辩评测\real_annotation_batch_01_B.jsonl `
  --output 答辩评测\real_annotation_batch_01_merged.jsonl
```

脚本只会把完全一致的样本标记为 `adjudicated=true`；分歧样本保留 A/B 两边的决定并标记 `needs_adjudication`，不会悄悄选一边。

## 当前进度

`real_annotation_queue.jsonl`：280 条待人工复核，0 条完成双人仲裁。批次 01 只是降低启动成本，后续仍需覆盖其余 20 个文档组。
