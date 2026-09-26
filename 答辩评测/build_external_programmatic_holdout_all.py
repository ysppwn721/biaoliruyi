"""Build a larger, reproducible external holdout from local annual-report PDFs.

This is intentionally a programmatic evaluation set.  PyMuPDF reads the text
layer, extracts the first two numeric values after financial metric labels, and
creates current/prior/wrong-period candidates.  It is useful when human
annotation cannot be completed before a deadline, but it must not be called
human ground truth.
"""
from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "cn_reports"
OUT = ROOT / "external_programmatic_holdout_all.jsonl"
STATS = ROOT / "external_programmatic_holdout_all_stats.json"

METRICS = [
    "归属于上市公司股东的净利润", "经营活动产生的现金流量净额",
    "归属于上市公司股东的净资产", "基本每股收益", "营业收入",
    "营业成本", "净利润", "利润总额", "资产总计", "负债合计",
    "总资产", "研发费用", "销售费用", "管理费用", "货币资金",
]
NUM = re.compile(r"^[-−]?\(?[\d,]+(?:\.\d+)?\)?%?$")
YEAR = re.compile(r"20\d{2}")


def clean(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def number(value: str) -> str | None:
    value = clean(value).replace("−", "-")
    if not NUM.fullmatch(value):
        return None
    return value


def report_year(path: Path) -> int:
    # The six-digit stock code can itself contain a 20xx-looking substring
    # (002097 -> 2097).  A report year is followed by 年 and is not preceded
    # by another digit, which also handles names such as 公司2021年年度报告.
    years = [int(x) for x in re.findall(r"(?<!\d)(20\d{2})年", path.stem)]
    return years[0] if years else 2023


def parse_report(path: Path) -> list[dict]:
    """Read a text-layer report and keep one robust first occurrence per metric."""
    doc = pymupdf.open(path)
    rows: list[dict] = []
    seen: set[str] = set()
    for page_no, page in enumerate(doc, 1):
        lines = [clean(line) for line in page.get_text().splitlines() if clean(line)]
        for index, line in enumerate(lines):
            metric = next((m for m in METRICS if m in line), None)
            if not metric or metric in seen:
                continue
            values: list[str] = []
            for candidate in lines[index + 1:index + 8]:
                parsed = number(candidate)
                if parsed is not None:
                    values.append(parsed)
                if len(values) >= 3:
                    break
            if len(values) < 2:
                continue
            unit = "%" if "率" in metric else ("元/股" if "每股" in metric else "元")
            rows.append({
                "metric": metric,
                "current": values[0],
                "prior": values[1],
                "change": next((v for v in values[2:] if v.endswith("%")), None),
                "page": page_no,
                "unit": unit,
            })
            seen.add(metric)
    doc.close()
    return rows


def fact_text(fact: dict) -> str:
    return "；".join(f"{key}={fact[key]}" for key in ("subject", "metric", "period", "unit", "scope"))


def build_rows(path: Path) -> tuple[list[dict], dict]:
    code = path.stem[:6]
    year = report_year(path)
    subject = f"上市公司{code}"
    suffix = hashlib.sha1(path.name.encode("utf-8")).hexdigest()[:6]
    group = f"external-pdf-{code}-{year}-{suffix}"
    parsed = parse_report(path)
    rows: list[dict] = []
    for metric_index, item in enumerate(parsed[:8], 1):
        current = {"id": f"{group}-m{metric_index}-current", "subject": subject,
                   "metric": item["metric"], "period": f"{year}年", "unit": item["unit"], "scope": "合并口径"}
        prior = {"id": f"{group}-m{metric_index}-prior", "subject": subject,
                 "metric": item["metric"], "period": f"{year - 1}年", "unit": item["unit"], "scope": "合并口径"}
        wrong = {"id": f"{group}-m{metric_index}-wrongperiod", "subject": subject,
                 "metric": item["metric"], "period": f"{year - 2}年", "unit": item["unit"], "scope": "合并口径"}
        candidates = (current, prior, wrong)
        claims = [
            (f"{subject}{year}年{item['metric']}为{item['current']}{item['unit']}", {current["id"]}),
            (f"{subject}{year}年{item['metric']}较上年变化{item.get('change') or ''}", {current["id"], prior["id"]}),
        ]
        for claim_index, (claim, gold) in enumerate(claims, 1):
            claim_id = f"{group}-m{metric_index}-c{claim_index}"
            for fact in candidates:
                rows.append({
                    "claim_id": claim_id,
                    "claim_text": claim,
                    "fact_id": fact["id"],
                    "fact_text": fact_text(fact),
                    "group_id": group,
                    "label": int(fact["id"] in gold),
                    "negative_type": "positive" if fact["id"] in gold else "hard_negative_wrong_period",
                    "source_file": path.name,
                    "source_page": item["page"],
                    "programmatic": True,
                })
    return rows, {"file": path.name, "group_id": group, "year": year, "metrics": len(parsed[:8]), "claims": len(parsed[:8]) * 2}


def main() -> None:
    all_rows: list[dict] = []
    report_stats: list[dict] = []
    for path in sorted(REPORT_DIR.glob("*.pdf")):
        # Skip a short summary and an English-language report; keep annual reports.
        if "摘要" in path.name or "英文" in path.name or path.stat().st_size < 1_500_000:
            continue
        try:
            rows, info = build_rows(path)
        except Exception as exc:  # keep one broken PDF from stopping the batch
            report_stats.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if rows:
            all_rows.extend(rows)
            report_stats.append(info)
    with OUT.open("w", encoding="utf-8") as stream:
        for row in all_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    stats = {
        "rows": len(all_rows),
        "claims": len({row["claim_id"] for row in all_rows}),
        "groups": len({row["group_id"] for row in all_rows}),
        "reports": len([r for r in report_stats if "error" not in r]),
        "programmatic": True,
        "source": "local public annual-report PDFs read with PyMuPDF",
        "reports_detail": report_stats,
    }
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("rows", "claims", "groups", "reports", "programmatic")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
