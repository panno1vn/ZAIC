"""Check a submission's format before uploading; works on splits without answers (public_test, private_test).

    python -m datamate.eval.validate --pred outputs/submission.jsonl --split public_test

Exit code 1 when the file has a problem that costs points or breaks the upload: unreadable lines, unknown or
duplicate ids, or answers in the wrong format. Missing questions are reported but allowed (they score as abstain).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from .scorer import format_error, read_jsonl


def validate(pred_lines: list[dict], question_ids: list[str]) -> tuple[list[str], list[str], Counter]:
    """(errors, notes, count of lines per type)."""
    errors, notes = [], []
    known = set(question_ids)
    seen: Counter = Counter(obj["id"] for obj in pred_lines)
    for qid, n in seen.items():
        if n > 1:
            errors.append(f"id {qid} xuất hiện {n} lần")
        if qid not in known:
            errors.append(f"id {qid} không có trong questions.jsonl")
    types: Counter = Counter()
    for obj in pred_lines:
        types[obj.get("type")] += 1
        if "reason" in obj and not isinstance(obj["reason"], str):
            notes.append(f"id {obj['id']}: reason không phải chuỗi, câu này sẽ bị tính như bỏ trống")
            continue
        err = format_error(obj)
        if err:
            errors.append(f"id {obj['id']}: {err}")
    missing = known - set(seen)
    if missing:
        notes.append(f"thiếu {len(missing)} câu: sẽ tính là bỏ trống")
    return errors, notes, types


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", required=True, help="submission.jsonl cần kiểm tra")
    ap.add_argument("--split", default="public_test", help="split chứa questions.jsonl (mặc định: public_test)")
    ap.add_argument("--data-root", default="data", help="thư mục chứa các split (mặc định: data)")
    args = ap.parse_args(argv)

    questions, _ = read_jsonl(Path(args.data_root) / args.split / "questions.jsonl")
    pred, read_warnings = read_jsonl(args.pred)
    errors, notes, types = validate(pred, [q["id"] for q in questions])
    errors = read_warnings + errors

    print(f"{args.pred}: {len(pred)} dòng đọc được / {len(questions)} câu hỏi")
    print("Theo type: " + ", ".join(f"{t}={n}" for t, n in types.most_common()))
    for n in notes:
        print("  lưu ý:", n)
    if errors:
        print(f"LỖI ({len(errors)}):")
        for e in errors[:20]:
            print("  -", e)
        return 1
    print("OK: file đúng định dạng")
    return 0


if __name__ == "__main__":
    sys.exit(main())
