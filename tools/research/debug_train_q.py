"""Run train questions through the eval chain (leave-one-shop-out mapping, cached LLM column matching, stored plans)
and print plan, gates, decision and the shop's mapped tables: to see why a question is blank. Train only.

    python tools/research/debug_train_q.py <question id> [...]
"""
from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from datamate import rules, verify  # noqa: E402
from datamate.contracts import QueryPlan  # noqa: E402
from datamate.eval.build_bank import PLANS, current_plans  # noqa: E402
from datamate.eval.check_plans import check  # noqa: E402
from datamate.eval.scorer import score_line  # noqa: E402
from datamate.llm import CachedLLM  # noqa: E402
from datamate.mapping import transfer  # noqa: E402
from datamate.pipeline import prepare_business, rule_ids  # noqa: E402


class _Offline:
    def generate_json(self, messages, schema):
        raise urllib.error.URLError("offline")

    def healthy(self):
        return True


def main(ids: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    split = ROOT / "data" / "train"
    qs = {q["id"]: q for q in map(json.loads, (split / "questions.jsonl").read_text(encoding="utf-8").splitlines())}
    refs = {a["id"]: a for a in map(json.loads, (split / "answers.jsonl").read_text(encoding="utf-8").splitlines())}
    stored = {e["id"]: e["plan"] for e in map(json.loads, PLANS.read_text(encoding="utf-8").splitlines())}
    plans = current_plans([qs[i] for i in ids], stored)
    rulebook = (split / "rulebook.md").read_text(encoding="utf-8-sig")
    rule_status = rules.check_rules(rulebook, rule_ids())
    llm = CachedLLM(_Offline(), str(ROOT / "outputs" / "llm_cache_mapping.jsonl"))
    ctxs = {}
    for i in ids:
        q = qs[i]
        b = q["business_id"]
        if b not in ctxs:
            pool = transfer.examples(leave_out=b)

            def map_fn(raw, profile, rb, _llm=None, pool=pool):
                m, tried = transfer.map_by_transfer(raw, pool, llm=llm)
                return m if m is not None else transfer.failed(tried)
            ctxs[b] = prepare_business(split / "data" / b, rulebook, None, map_fn)
        ctx = ctxs[b]
        print(f"\n{b} {i} {q['question']}\n  đáp án: {json.dumps(refs[i], ensure_ascii=False)[:150]}")
        print(f"  bảng: {sorted(t for t in ctx.db.tables) if hasattr(ctx.db, 'tables') else '?'}")
        p = plans.get(i)
        print(f"  plan: {json.dumps(p, ensure_ascii=False)[:300]}")
        if p is None:
            print(f"  not_recorded(None): {verify.not_recorded(None, q['question'], ctx.db)}")
            continue
        print(f"  not_recorded: {verify.not_recorded(QueryPlan.model_validate(p), q['question'], ctx.db)}")
        got = check(q, QueryPlan.model_validate(p), ctx, split / "calendar.csv", rule_status)
        print(f"  fn={got['function']} gates={got['gates']} reason={got['reason']} no_result={got['no_result']}")
        print(f"  line={json.dumps(got['line'], ensure_ascii=False)[:150]} → {score_line(got['line'], refs[i]).outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
