"""Read again, with today's code, the train questions the plan bank stores without a plan (None: the code of the day
refused the LLM output). The rewrites added since (N137-N147…) can only fix a plan that is there: a None stays None
until the question is read again. The LLM cache answers the calls whose prompt has not changed; the others need the
llama-server.

    python tools/reread_no_plan.py --llm-url http://127.0.0.1:8091 [--backup-tag N137]

Keeps a copy of the bank (outputs/bank/llm_plans.before_<tag>.jsonl), rewrites outputs/bank/llm_plans.jsonl with the
new plans, and leaves assets/ alone (the verified bank is rebuilt by datamate.eval.build_bank only). Train only.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from datamate.eval import build_bank  # noqa: E402
from datamate.predict import connect_llm  # noqa: E402


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm-url", required=True)
    ap.add_argument("--llm-cache", default=str(ROOT / "outputs" / "llm_cache.jsonl"))
    ap.add_argument("--backup-tag", default="reread")
    args = ap.parse_args(argv)

    bank = build_bank.PLANS
    entries = [json.loads(x) for x in bank.read_text(encoding="utf-8").splitlines() if x.strip()]
    none_ids = {e["id"] for e in entries if e["plan"] is None}
    backup = bank.with_name(f"llm_plans.before_{args.backup_tag}.jsonl")
    if not backup.exists():
        shutil.copy2(bank, backup)
    llm = connect_llm(args.llm_url, cache=args.llm_cache)
    if llm is None:
        return 1
    questions = [json.loads(x) for x in (ROOT / "data" / "train" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
                 if x.strip()]
    bank.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries if e["id"] not in none_ids),
                    encoding="utf-8")
    plans = build_bank.read_plans(questions, llm)
    got = sum(1 for i in none_ids if plans.get(i))
    print(f"{len(none_ids)} câu không có plan, đọc lại: {got} có plan, {len(none_ids) - got} vẫn không. Kho cũ: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
