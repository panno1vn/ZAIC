"""Diagnostic submissions by kind of answer: from a run (or replay) with logs, one file per group of answers turned
into abstain. Submitted beside the run, wrong answers of a group = (n − (score_run − score_group) × 1000) / 2.

    python tools/ablate_groups.py outputs/replay/run10_s27 --out outputs/public_ablation12 \
        [--submission outputs/replay/run10_s27m/submission.jsonl] [--only-shops dev_001 dev_002 …]

Groups (by the answering function and plan): compare, rank, count_where, value with filters, share/series/trend/debt/
stock/industry, value without filters. --only-shops limits every group to those shops (the others' answers kept).
Counts only, no question or answer printed (the public data rule: CAI_DAT.md, "Luật bắt buộc").
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

GROUPS = ("bo_compare", "bo_rank", "bo_count_where", "bo_value_loc", "bo_share_series_no_kho", "bo_value_tron")


def group(log: dict) -> str:
    f = (log.get("result") or {}).get("function") or "?"
    ms = (log.get("plan") or {}).get("measures") or []
    if f == "sales.compare":
        return "bo_compare"
    if f == "sales.rank":
        return "bo_rank"
    if f == "sales.count_where":
        return "bo_count_where"
    if f == "sales.value_of" and any(m.get("filters") for m in ms):
        return "bo_value_loc"
    if f in ("sales.share", "sales.series", "sales.trend") or f.startswith(("debt.", "stock.", "industry.")):
        return "bo_share_series_no_kho"
    return "bo_value_tron"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path, help="thư mục có logs/ (lượt chạy hoặc bản chạy lại)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--submission", type=Path, help="file nộp gốc (mặc định: <run>/submission.jsonl)")
    ap.add_argument("--only-shops", nargs="*", default=[])
    args = ap.parse_args(argv)
    logs = {}
    for f in (args.run / "logs").glob("q_*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        logs[d["id"]] = d
    lines = [json.loads(x) for x in (args.submission or args.run / "submission.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()]
    keep = set(args.only_shops)

    def name(line: dict) -> str | None:
        d = logs.get(line["id"])
        if d is None or line["type"] == "abstain" or (keep and d["business_id"] not in keep):
            return None
        return group(d)

    args.out.mkdir(parents=True, exist_ok=True)
    sizes = Counter(n for n in map(name, lines) if n)
    for g in GROUPS:
        out = [{"id": x["id"], "type": "abstain"} if name(x) == g else x for x in lines]
        (args.out / f"{g}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out),
                                             encoding="utf-8")
        print(f"{g:24} bỏ trống {sizes.get(g, 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
