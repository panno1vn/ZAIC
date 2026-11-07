"""One shard of the train questions read by an LLM, exactly as eval/build_bank.read_plans reads them (hand plans of
other businesses as examples), so two GPUs can read the 3000 questions in half the time (Kaggle T4 x2, plan §11).
Resumable: questions already in --out are skipped. Merge the shards into outputs/bank/llm_plans.jsonl afterwards.

    python tools/read_plans_shard.py --llm-url http://127.0.0.1:8091 --shard 0 --of 2 \
        --out outputs/bank/shard0.jsonl --cache outputs/llm_cache_14b_0.jsonl

Development only: train questions.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datamate import nlu  # noqa: E402
from datamate.contracts import DataCard  # noqa: E402
from datamate.nlu import prompt  # noqa: E402
from datamate.predict import connect_llm  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm-url", required=True)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--of", type=int, default=1)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", help="cache riêng cho model này (khoá cache không gồm tên model)")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--data-root", type=Path, default=ROOT / "data")
    args = ap.parse_args(argv)

    questions = [json.loads(x) for x in (args.data_root / "train" / "questions.jsonl").read_text(encoding="utf-8")
                 .splitlines() if x.strip()]
    mine = [q for i, q in enumerate(questions) if i % args.of == args.shard]
    done = set()
    if args.out.exists():
        done = {json.loads(x)["id"] for x in args.out.read_text(encoding="utf-8").splitlines() if x.strip()}
    todo = [q for q in mine if q["id"] not in done]
    llm = connect_llm(args.llm_url, timeout_s=args.timeout, cache=args.cache)
    if llm is None:
        return 1
    bank = prompt.ExampleBank(prompt.HAND_FILES)
    business = {q["id"]: q["business_id"] for q in questions}
    same: dict[str, frozenset[str]] = defaultdict(frozenset)
    for b in set(business.values()):
        same[b] = frozenset(e["id"] for e in bank.items if business.get(e["id"]) == b)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with args.out.open("a", encoding="utf-8") as f:
        for n, q in enumerate(todo, 1):
            plan = nlu.llm_plan(q["question"], date.fromisoformat(q["as_of_date"]), DataCard(), llm, bank,
                                exclude_ids=same[q["business_id"]])
            dumped = plan.model_dump(mode="json", exclude_none=True, exclude_defaults=True) if plan else None
            f.write(json.dumps({"id": q["id"], "plan": dumped}, ensure_ascii=False) + "\n")
            f.flush()
            if n % 100 == 0:
                print(f"  shard {args.shard}: {n}/{len(todo)} · {(time.time() - t0) / n:.1f}s/câu", flush=True)
    print(f"shard {args.shard}: xong {len(todo)} câu trong {(time.time() - t0) / 60:.1f} phút")
    return 0


if __name__ == "__main__":
    sys.exit(main())
