"""Run given plans of train questions through the rest of the chain and score them: what the metric library [D1]
gets right once the plan is right, and (T4) which plans are verified by the answer.

    python -m datamate.eval.check_plans --out outputs/check_plans/run.jsonl
    python -m datamate.eval.check_plans --plans outputs/linking/llm_plans.jsonl --out outputs/check_plans/run.jsonl

Plans: the hand plans of assets/plans, then each --plans file (jsonl of {"id", "plan"}), the first one found for a
question wins. Default --plans: the LLM plans cached by T1 and T2. Chain: temporal → linking → metrics → [V] → [E]
→ formatter, with the hand mappings of the businesses (assets/mappings/train). Development only: train data.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from datamate import decide, formatter, metrics, nlu, rules, temporal, verify
from datamate.contracts import QueryPlan
from datamate.nlu.templates import plan_shape
from datamate.pipeline import prepare_business, rule_ids

from .oracle import mapping_files, oracle_map_fn
from .scorer import score_line

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLANS = [ROOT / "outputs" / "linking" / "llm_plans.jsonl", ROOT / "outputs" / "templates" / "llm_plans.jsonl"]


def load_plans(files: list[Path]) -> dict[str, tuple[str, dict]]:
    """id -> (source, plan): hand plans first, then the files in order."""
    out: dict[str, tuple[str, dict]] = {}
    for f in nlu.prompt.HAND_FILES:  # not the verified bank (T4): hand plans only
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                out.setdefault(e["id"], ("tay", e["plan"]))
    for f in files:
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                e = json.loads(line)
                if e.get("plan"):
                    out.setdefault(e["id"], (f.parent.name, e["plan"]))
    return out


def check(q: dict, plan: QueryPlan, ctx, calendar: Path, rule_status: dict[str, bool]) -> dict:
    as_of = date.fromisoformat(q["as_of_date"])
    resolved = temporal.resolve(plan, as_of, calendar, ctx.db)
    if resolved is not None:
        resolved = nlu.link_entities(resolved, ctx.db, q["question"])
    result = None
    if resolved is not None and plan.intent != "out_of_scope":
        result = metrics.execute(resolved, ctx.db)
    signals = verify.collect_signals(resolved, result, ctx.db, ctx.mapping, rule_status)
    decision = decide.decide(signals, result)
    line = formatter.to_line(q["id"], decision, result).to_dict()
    gates = [g for g in decide.GATES if not getattr(signals, g)]
    return {"line": line, "function": result.function if result else None, "gates": gates,
            "value": result.value if result is not None and not hasattr(result.value, "to_dict") else None}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--plans", nargs="*", type=Path, default=DEFAULT_PLANS)
    ap.add_argument("--business", nargs="*")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    split = Path(args.data_root) / "train"
    files = mapping_files("train")
    chosen = set(args.business or files)
    questions = [json.loads(line) for line in (split / "questions.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    refs = {a["id"]: a for a in map(json.loads, (split / "answers.jsonl").read_text(encoding="utf-8").splitlines())}
    plans = load_plans(args.plans)
    rulebook = (split / "rulebook.md").read_text(encoding="utf-8-sig")
    rule_status = rules.check_rules(rulebook, rule_ids())
    map_fn = oracle_map_fn("train")

    rows = []
    by_business = defaultdict(list)
    for q in questions:
        if q["business_id"] in chosen and q["id"] in plans:
            by_business[q["business_id"]].append(q)
    for b, qs in sorted(by_business.items()):
        ctx = prepare_business(split / "data" / b, rulebook, None, map_fn)
        for q in qs:
            source, raw = plans[q["id"]]
            plan = QueryPlan.model_validate(raw)
            if source != "tay":  # an LLM plan passes the pipeline's grounding gate first
                plan = nlu.accept_plan(q["question"], plan, date.fromisoformat(q["as_of_date"]))
                if plan is None:
                    refs_line = {"id": q["id"], "type": "abstain"}
                    rows.append({"id": q["id"], "business_id": b, "question": q["question"], "source": source,
                                 "shape": "(plan bị cổng căn cứ loại)", "outcome": "abstain", "why": "grounding",
                                 "gates": ["grounding"], "function": None, "pred": refs_line,
                                 "ref": {k: refs[q["id"]][k] for k in ("type", "answer")}})
                    continue
            got = check(q, plan, ctx, split / "calendar.csv", rule_status)
            v = score_line(got["line"], refs[q["id"]])
            rows.append({"id": q["id"], "business_id": b, "question": q["question"], "source": source,
                         "shape": plan_shape(plan, period=False), "outcome": v.outcome, "why": v.reason,
                         "gates": got["gates"], "function": got["function"], "pred": got["line"],
                         "ref": {k: refs[q["id"]][k] for k in ("type", "answer")}})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows), encoding="utf-8")
    total = Counter(r["outcome"] for r in rows)
    print(f"{len(rows)} câu có plan ở {len(by_business)} cửa hàng · đúng {total['correct']} · sai {total['wrong']} · "
          f"bỏ trống {total['abstain']} · PA trên các câu này {(total['correct'] - total['wrong']) / max(len(rows), 1):+.3f}")
    by_shape: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_shape[r["shape"]][r["outcome"]] += 1
    print(f"\n  {'dạng plan':<70}{'n':>4}{'đúng':>6}{'sai':>5}{'trống':>7}")
    for shape, c in sorted(by_shape.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {shape[:70]:<70}{sum(c.values()):>4}{c['correct']:>6}{c['wrong']:>5}{c['abstain']:>7}")
    wrong = [r for r in rows if r["outcome"] == "wrong"]
    if wrong:
        print("\nCâu sai:")
        for r in wrong:
            print(f"  {r['id']} {r['business_id']} [{r['source']}] {r['question'][:90]}\n     {r['shape']} | "
                  f"{r['why']} | dự đoán {json.dumps(r['pred'].get('answer'), ensure_ascii=False)[:60]} "
                  f"| đáp án {json.dumps(r['ref'], ensure_ascii=False)[:80]}")
    gates = Counter(g for r in rows if r["outcome"] == "abstain" for g in r["gates"])
    print("\nBỏ trống vì cổng:", dict(gates.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
