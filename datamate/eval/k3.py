"""K3: how well the LLM writes plans. Every hand-written plan of the example bank (24 examples + 99 K2) is a test:
the LLM reads the question with the bank minus that question, and its plan is compared with the hand plan.

    python -m datamate.eval.k3 --base-url http://127.0.0.1:8080 --out outputs/k3/qwen3-8b-q4.jsonl
    python -m datamate.eval.k3 --mock --out outputs/k3/selftest.jsonl      # the hand plans as answers: must be 100%

Development only: train questions, never test data.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from datamate.contracts import DataCard, QueryPlan
from datamate.llm import LlamaServerLLM, MockLLM
from datamate.nlu import canonical_plan, llm_plan, prompt

PARTS = ("intent", "period", "measures", "rank", "compare", "threshold", "list_spec")


def score(bank: prompt.ExampleBank, llm, limit: int | None = None) -> list[dict]:
    rows = []
    for item in bank.items[:limit]:
        ref = QueryPlan.model_validate(item["plan"])
        t0 = time.perf_counter()
        got = llm_plan(item["question"], date.fromisoformat(item["as_of_date"]), DataCard(), llm, bank,
                       exclude_ids=frozenset({item["id"]}))
        row = {"id": item["id"], "question": item["question"], "intent": ref.intent, "valid": got is not None,
               "ms": round((time.perf_counter() - t0) * 1000)}
        if got is not None:
            a, b = canonical_plan(got), canonical_plan(ref)
            row["exact"] = a == b
            row["parts_ok"] = [p for p in PARTS if a.get(p) == b.get(p)]
            row["plan"] = a
        else:
            row["exact"] = False
            row["parts_ok"] = []
        row["ref"] = canonical_plan(ref)
        rows.append(row)
    return rows


def report(rows: list[dict]) -> None:
    n = len(rows)
    print(f"{n} câu · JSON hợp lệ {sum(r['valid'] for r in rows) / n:.1%} · plan khớp hoàn toàn "
          f"{sum(r['exact'] for r in rows) / n:.1%} · trung bình {sum(r['ms'] for r in rows) / n:.0f} ms/câu")
    print("Đúng từng phần: " + " · ".join(f"{p} {sum(p in r['parts_ok'] for r in rows) / n:.0%}" for p in PARTS))
    by = defaultdict(list)
    for r in rows:
        by[r["intent"]].append(r)
    print(f"\n  {'loại câu':<14}{'n':>4}{'khớp':>8}")
    for intent, rs in sorted(by.items(), key=lambda kv: sum(r['exact'] for r in kv[1]) / len(kv[1])):
        print(f"  {intent:<14}{len(rs):>4}{sum(r['exact'] for r in rs) / len(rs):>8.0%}")
    wrong = [r for r in rows if not r["exact"]][:10]
    if wrong:
        print("\nVí dụ lệch (xem đủ trong file --out):")
        for r in wrong:
            print(f"  {r['id']} {r['question'][:70]}\n     LLM: {json.dumps(r.get('plan'), ensure_ascii=False)[:160]}"
                  f"\n     tay: {json.dumps(r['ref'], ensure_ascii=False)[:160]}")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--base-url", help="llama-server, ví dụ http://127.0.0.1:8080")
    src.add_argument("--mock", action="store_true", help="dùng chính plan viết tay làm câu trả lời (tự kiểm tra)")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    bank = prompt.ExampleBank()
    if args.mock:
        llm = MockLLM([e["plan"] for e in bank.items[:args.limit]])
    else:
        llm = LlamaServerLLM(args.base_url, timeout_s=args.timeout)
        if not llm.healthy():
            print(f"không gọi được {args.base_url}/health: server chưa chạy hoặc chưa load xong model")
            return 1
    rows = score(bank, llm, args.limit)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
