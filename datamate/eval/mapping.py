"""T5: score the automatic mapping on train. Each business is mapped by transfer with its own hand mapping left out of
the examples (as a shop never seen), the LLM plans of eval/build_bank.py (read with other businesses' examples only)
go through the whole chain, and the answers are scored against the train answers.

    python -m datamate.eval.mapping                      # every train business
    python -m datamate.eval.mapping --business biz_102   # some
    python -m datamate.eval.mapping --readme-only        # only the mapping built from the README (N23)

Prints, per business, the example the mapping came from (or why none passed) and right / wrong / blank; then the
wrong answers. Development only: train answers, hand mappings.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from datamate import loader, metrics, rules
from datamate.contracts import QueryPlan
from datamate.mapping import transfer
from datamate.pipeline import prepare_business
from datamate.predict import connect_llm

from .build_bank import PLANS, current_plans
from .check_plans import check
from .oracle import mapping_files
from .scorer import score_line


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--business", nargs="*")
    ap.add_argument("--llm-url", help="llama-server để ghép cột theo nghĩa (mặc định: chỉ ghép theo tên cột)")
    ap.add_argument("--llm-cache", default="outputs/llm_cache_mapping.jsonl")
    ap.add_argument("--readme-only", action="store_true",
                    help="chỉ dựng mapping từ mô tả cột trong README (N23), không dùng mapping mẫu: đo riêng đường này")
    args = ap.parse_args(argv)
    llm = connect_llm(args.llm_url, cache=args.llm_cache) if args.llm_url else None
    if args.llm_url and llm is None:
        return 1

    split = Path(args.data_root) / "train"
    questions = [json.loads(line) for line in (split / "questions.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    refs = {a["id"]: a for a in map(json.loads, (split / "answers.jsonl").read_text(encoding="utf-8").splitlines())}
    plans = current_plans(questions, {e["id"]: e["plan"]
                                      for e in map(json.loads, PLANS.read_text(encoding="utf-8").splitlines())})
    rulebook = (split / "rulebook.md").read_text(encoding="utf-8-sig")
    rule_status = rules.check_rules(rulebook, tuple(sorted({r for s in metrics.REGISTRY.values() for r in s.rules})))
    hand = set(mapping_files("train"))
    by_business: dict[str, list[dict]] = {}
    for q in questions:
        by_business.setdefault(q["business_id"], []).append(q)

    total, wrong = Counter(), []
    print(f"  {'cửa hàng':10}{'đúng':>6}{'sai':>5}{'trống':>7}  mapping")
    for b in sorted(args.business or by_business):
        pool = [] if args.readme_only else transfer.examples(leave_out=b)

        def map_fn(raw, profile, rulebook_text, _llm=None, pool=pool):
            m, tried = transfer.map_by_transfer(raw, pool, llm=None if args.readme_only else llm)
            return m if m is not None else transfer.failed(tried)
        ctx = prepare_business(split / "data" / b, rulebook, None, map_fn)
        outcome = Counter()
        for q in by_business[b]:
            p = plans.get(q["id"])
            if not ctx.mapping.ok or p is None:
                outcome["abstain"] += 1
                continue
            got = check(q, QueryPlan.model_validate(p), ctx, split / "calendar.csv", rule_status)
            o = score_line(got["line"], refs[q["id"]]).outcome
            outcome[o] += 1
            if o == "wrong":
                wrong.append((b, q["question"], got["line"], refs[q["id"]], got["function"]))
        total += outcome
        how = ctx.mapping.notes[0] if ctx.mapping.ok and ctx.mapping.notes else (
            "; ".join(c.detail for c in ctx.mapping.checks if not c.passed)[:110] or "không qua kiểm tra")
        print(f"  {b + ('*' if b in hand else ''):10}{outcome['correct']:>6}{outcome['wrong']:>5}{outcome['abstain']:>7}"
              f"  {how}")
    n = sum(total.values())
    print(f"\n{n} câu · đúng {total['correct']} · sai {total['wrong']} · bỏ trống {total['abstain']} · "
          f"PA {(total['correct'] - total['wrong']) / max(n, 1):+.3f}   (* có mapping tay, bị bỏ ra khỏi ví dụ)")
    if wrong:
        print("\nCâu sai:")
        for b, question, line, ref, fn in wrong:
            print(f"  {b} {question[:90]}\n     {fn} | dự đoán {json.dumps(line, ensure_ascii=False)[:120]} | "
                  f"đáp án {json.dumps(ref.get('answer'), ensure_ascii=False)[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
