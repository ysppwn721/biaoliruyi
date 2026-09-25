"""Extract candidate labels from the supplied long Word evaluation material.

This does not claim independent ground truth. It creates an annotation queue
from the real Word/XLSX pair so two reviewers can verify references and mark
ambiguity before the rows enter the held-out evaluation set.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zhilian.engine import extract_claims
from zhilian.office import docx_paragraphs, read_facts
from docx import Document


ROOT = Path(__file__).resolve().parent
DOC = ROOT.parent / "长文Word测试" / "长文测试_原始报告.docx"
XLSX = ROOT.parent / "长文Word测试" / "配套数据_初始.xlsx"
OUT = ROOT / "real_annotation_queue.jsonl"


def main() -> None:
    facts = read_facts(XLSX, "long-word")
    metadata = [{key: fact[key] for key in ("id", "subject", "metric", "period", "unit", "scope")}
                for fact in facts]
    rows = []
    for block_index, (location, label, paragraph) in enumerate(docx_paragraphs(Document(DOC))):
        text = paragraph.text
        if not text.strip():
            continue
        claims = extract_claims({"file_id": "long-word-doc", "location": location,
                                 "label": label, "text": text}, facts)
        group_id = f"longword-{block_index // 14 + 1:02d}"
        for claim_index, claim in enumerate(claims, 1):
            refs = [ref["id"] if isinstance(ref, dict) else ref for ref in claim.get("refs", [])]
            rows.append({
                "group_id": group_id,
                "split": "annotation",
                "claim_id": f"lw-{block_index:03d}-{claim_index:02d}",
                "claim_text": claim["original"],
                "kind": claim["kind"],
                "facts": metadata,
                "candidate_refs": refs,
                "gold_refs": [],
                "gold_action": "unreviewed",
                "category": "unreviewed",
                "source_file": str(DOC.relative_to(ROOT.parent)),
                "source_location": location,
                "annotators": [],
                "adjudicated": False,
                "notes": "来自真实长文 Word 与配套 Excel；需两人独立确认标准答案",
            })
    with OUT.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {OUT}: {len(rows)} real claim candidates")
    print(f"groups={len({row['group_id'] for row in rows})}")


if __name__ == "__main__":
    main()
