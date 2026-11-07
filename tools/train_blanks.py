"""Train only: where the blank answers stop (mapping, plan, function, gate), mirroring eval.mapping without the LLM
(mapping by column names and README, the stored LLM plans). Lists "no result" by intent:metric:entity, the list
that showed N29 (05/11). Development only: train answers.

    python tools/train_blanks.py
"""
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from datamate import decide, metrics, nlu, rules, temporal, verify  # noqa: E402
from datamate.contracts import QueryPlan  # noqa: E402
from datamate.eval.build_bank import PLANS, current_plans  # noqa: E402
from datamate.mapping import transfer  # noqa: E402
from datamate.pipeline import prepare_business, rule_ids  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
split = ROOT / "data" / "train"
qs = [json.loads(x) for x in (split / "questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
refs = {a["id"]: a for a in map(json.loads, (split / "answers.jsonl").read_text(encoding="utf-8").splitlines())}
plans = current_plans(qs, {e["id"]: e["plan"] for e in map(json.loads, PLANS.read_text(encoding="utf-8").splitlines())})
rb = (split / "rulebook.md").read_text(encoding="utf-8-sig")
status = rules.check_rules(rb, rule_ids())
by = {}
for q in qs:
    by.setdefault(q["business_id"], []).append(q)
stage, fn_none = Counter(), Counter()
for b in sorted(by):
    pool = transfer.examples(leave_out=b)

    def map_fn(raw, profile, r, _llm=None, pool=pool):
        m, tried = transfer.map_by_transfer(raw, pool, llm=None)
        return m if m is not None else transfer.failed(tried)
    ctx = prepare_business(split / "data" / b, rb, None, map_fn)
    for q in by[b]:
        ref = refs[q["id"]]["type"]
        if not ctx.mapping.ok:
            stage["1 mapping hỏng"] += 1
            continue
        p = plans.get(q["id"])
        if p is None:
            stage["2 không plan"] += 1
            continue
        plan = QueryPlan.model_validate(p)
        res = temporal.resolve(plan, date.fromisoformat(q["as_of_date"]), split / "calendar.csv", ctx.db)
        if res is None:
            stage["3 không resolve kỳ"] += 1
            continue
        res = nlu.link_entities(res, ctx.db, q["question"])
        result = metrics.execute(res, ctx.db) if plan.intent != "out_of_scope" else None
        s = verify.collect_signals(res, result, ctx.db, ctx.mapping, status, q["question"])
        d = decide.decide(s, result)
        if d.kind != "abstain":
            continue
        if plan.intent == "out_of_scope":
            stage["4 ngoài phạm vi" + (" (đáp án unanswerable)" if ref == "unanswerable" else "")] += 1
        elif result is None:
            key = f"{plan.intent}:{metrics.metric_name(res)}:{metrics.metric_entity(res)}"
            stage["5 hàm không ra kết quả" + (" (đáp án unanswerable)" if ref == "unanswerable" else "")] += 1
            fn_none[key] += 1
        else:
            stage["6 " + d.reason[:60]] += 1
for k, v in sorted(stage.items()):
    print(f"{v:5}  {k}")
print("\nhàm không ra kết quả, theo intent:metric:entity")
for k, v in fn_none.most_common(25):
    print(f"{v:5}  {k}")
