"""Score a submission against a split's answers and print the breakdown by answer type, industry and business.

    python -m datamate.eval.run --pred outputs/submission.jsonl              # split train by default
    python -m datamate.eval.run --gold                                       # self-check: answers vs themselves
    python -m datamate.eval.run --pred outputs/x.jsonl --save outputs/eval/x_verdicts.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from .scorer import Verdict, penalized_accuracy, read_jsonl, score_submission

INDUSTRIES_FILE = Path(__file__).with_name("industries_train.json")


def load_industries() -> dict[str, str]:
    data = json.loads(INDUSTRIES_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def summarize(verdicts: list[Verdict], group_of: dict[str, str]) -> list[tuple]:
    """One row per group: (group, n, correct, wrong, abstain, PA, precision, coverage), worst PA first."""
    groups: dict[str, list[Verdict]] = defaultdict(list)
    for v in verdicts:
        groups[group_of.get(v.id, "?")].append(v)
    rows = []
    for g, vs in groups.items():
        c = sum(v.outcome == "correct" for v in vs)
        w = sum(v.outcome == "wrong" for v in vs)
        answered = c + w
        rows.append((g, len(vs), c, w, len(vs) - answered, penalized_accuracy(vs),
                     c / answered if answered else None, answered / len(vs)))
    return sorted(rows, key=lambda r: (r[5], r[0]))


def print_table(title: str, rows: list[tuple]) -> None:
    print(f"\n{title}")
    print(f"  {'nhóm':<22}{'n':>6}{'đúng':>7}{'sai':>6}{'trống':>7}{'PA':>9}{'chính xác':>11}{'trả lời':>9}")
    for g, n, c, w, a, pa, prec, cov in rows:
        prec_s = f"{prec:.1%}" if prec is not None else "-"
        print(f"  {str(g):<22}{n:>6}{c:>7}{w:>6}{a:>7}{pa:>+9.4f}{prec_s:>11}{cov:>9.1%}")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pred", help="submission.jsonl cần chấm")
    src.add_argument("--gold", action="store_true", help="chấm đáp án với chính nó (kiểm tra scorer)")
    ap.add_argument("--split", default="train", help="split có answers.jsonl (mặc định: train)")
    ap.add_argument("--data-root", default="data", help="thư mục chứa các split (mặc định: data)")
    ap.add_argument("--save", help="ghi kết quả từng câu ra file JSONL")
    args = ap.parse_args(argv)

    split_dir = Path(args.data_root) / args.split
    refs, _ = read_jsonl(split_dir / "answers.jsonl")
    questions, _ = read_jsonl(split_dir / "questions.jsonl")
    business_of = {q["id"]: q["business_id"] for q in questions}
    if args.gold:
        pred, read_warnings = refs, []
    else:
        pred, read_warnings = read_jsonl(args.pred)
    verdicts, warnings = score_submission(pred, refs)
    warnings = read_warnings + warnings

    total = summarize(verdicts, {v.id: "tất cả" for v in verdicts})[0]
    print(f"Split {args.split}: {total[1]} câu · đúng {total[2]} · sai {total[3]} · bỏ trống {total[4]}")
    print(f"PA = {total[5]:+.4f}   (đúng − sai = {total[2] - total[3]:+d})")
    ref_type = {r["id"]: r["type"] for r in refs}
    print_table("Theo kiểu đáp án", summarize(verdicts, ref_type))
    if args.split == "train":
        industries = load_industries()
        print_table("Theo ngành", summarize(verdicts, {q: industries.get(b, "?") for q, b in business_of.items()}))
    print_table("Theo cửa hàng", summarize(verdicts, business_of))
    if warnings:
        print(f"\nCảnh báo ({len(warnings)}):")
        for w in warnings[:10]:
            print("  -", w)

    if args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            for v in verdicts:
                fh.write(json.dumps({"id": v.id, "business_id": business_of.get(v.id), "ref_type": ref_type[v.id],
                                     "outcome": v.outcome, "reason": v.reason}, ensure_ascii=False) + "\n")
        print(f"\nĐã ghi {len(verdicts)} dòng vào {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
