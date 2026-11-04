"""T4: the verified example bank. The LLM reads every train question with examples from other businesses only (as for
a business never seen); a plan is kept when it is verified:
- "answer": on a business with a hand mapping, the plan runs through the whole chain to the train answer;
- "template": elsewhere, the plan has the shape (plan_shape) of an answer-verified plan of the same T1 template.

    python -m datamate.eval.build_bank --llm-url http://127.0.0.1:8091          # ~3000 LLM calls, cached, resumable
    python -m datamate.eval.build_bank                                           # verify the plans already read

Writes outputs/bank/llm_plans.jsonl (every plan read) and assets/plans/verified_train.jsonl (the bank). Development
only: train questions, hand mappings.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from datamate import nlu, rules
from datamate.contracts import DataCard, QueryPlan
from datamate.nlu import prompt
from datamate.nlu.templates import NameIndex, plan_shape, template_text
from datamate.pipeline import prepare_business, rule_ids
from datamate.predict import connect_llm

from .check_plans import check
from .oracle import mapping_files, oracle_map_fn
from .scorer import score_line

ROOT = Path(__file__).resolve().parents[2]
PLANS = ROOT / "outputs" / "bank" / "llm_plans.jsonl"
BANK = ROOT / "assets" / "plans" / prompt.VERIFIED_FILE
TEMPLATES = ROOT / "assets" / "plans" / "templates_train.json"
NAMES = ROOT / "outputs" / "templates" / "names.json"  # names of the 30 train businesses (tools/research/templates.py)


def read_plans(questions: list[dict], llm) -> dict[str, dict | None]:
    """The LLM plan of every question, with examples of other businesses only; resumes from PLANS."""
    done: dict[str, dict | None] = {}
    if PLANS.exists():
        for line in PLANS.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            done[e["id"]] = e["plan"]
    todo = [q for q in questions if q["id"] not in done]
    if not todo or llm is None:
        return done
    business = {q["id"]: q["business_id"] for q in questions}
    bank = prompt.ExampleBank(prompt.HAND_FILES)
    same: dict[str, frozenset[str]] = defaultdict(frozenset)
    for b in set(business.values()):
        same[b] = frozenset(e["id"] for e in bank.items if business.get(e["id"]) == b)
    PLANS.parent.mkdir(parents=True, exist_ok=True)
    with PLANS.open("a", encoding="utf-8") as f:
        for n, q in enumerate(todo, 1):
            plan = nlu.llm_plan(q["question"], date.fromisoformat(q["as_of_date"]), DataCard(), llm, bank,
                                exclude_ids=same[q["business_id"]])
            done[q["id"]] = plan.model_dump(mode="json", exclude_none=True, exclude_defaults=True) if plan else None
            f.write(json.dumps({"id": q["id"], "plan": done[q["id"]]}, ensure_ascii=False) + "\n")
            f.flush()
            if n % 100 == 0:
                print(f"  LLM {n}/{len(todo)}", flush=True)
    return done


def current_plans(questions: list[dict], plans: dict[str, dict | None]) -> dict[str, dict | None]:
    """The stored plans through today's nlu.accept_plan: gates added after the LLM read the questions apply too."""
    out = {}
    for q in questions:
        p = plans.get(q["id"])
        plan = nlu.accept_plan(q["question"], QueryPlan.model_validate(p), date.fromisoformat(q["as_of_date"])) if p else None
        out[q["id"]] = plan.model_dump(mode="json", exclude_none=True, exclude_defaults=True) if plan else None
    return out


def verify_by_answer(questions: list[dict], plans: dict[str, dict | None], split: Path) -> dict[str, str]:
    """outcome (correct / wrong / abstain) of each plan of the businesses with a hand mapping."""
    files = mapping_files("train")
    refs = {a["id"]: a for a in map(json.loads, (split / "answers.jsonl").read_text(encoding="utf-8").splitlines())}
    rulebook = (split / "rulebook.md").read_text(encoding="utf-8-sig")
    rule_status = rules.check_rules(rulebook, rule_ids())
    by_business = defaultdict(list)
    for q in questions:
        if q["business_id"] in files and plans.get(q["id"]):
            by_business[q["business_id"]].append(q)
    out = {}
    for b, qs in sorted(by_business.items()):
        ctx = prepare_business(split / "data" / b, rulebook, None, oracle_map_fn("train"))
        for q in qs:
            got = check(q, QueryPlan.model_validate(plans[q["id"]]), ctx, split / "calendar.csv", rule_status)
            out[q["id"]] = score_line(got["line"], refs[q["id"]]).outcome
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--llm-url")
    ap.add_argument("--llm-cache", default=str(ROOT / "outputs" / "llm_cache.jsonl"))
    args = ap.parse_args(argv)

    split = Path(args.data_root) / "train"
    questions = [json.loads(line) for line in (split / "questions.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    llm = connect_llm(args.llm_url, cache=args.llm_cache) if args.llm_url else None
    if args.llm_url and llm is None:
        return 1
    plans = current_plans(questions, read_plans(questions, llm))
    outcome = verify_by_answer(questions, plans, split)

    if not NAMES.exists():
        print(f"thiếu {NAMES.relative_to(ROOT)}: chạy python tools/research/templates.py trước (tên của 30 cửa hàng)")
        return 1
    name_index = {b: NameIndex([tuple(x) for x in ns])
                  for b, ns in json.loads(NAMES.read_text(encoding="utf-8")).items()}
    cluster = {i: k["id"] for k in json.loads(TEMPLATES.read_text(encoding="utf-8"))["clusters"] for i in k["ids"]}
    shapes = {qid: plan_shape(QueryPlan.model_validate(p)) for qid, p in plans.items() if p}
    verified_shapes: dict[str, set[str]] = defaultdict(set)
    for qid, o in outcome.items():
        if o == "correct":
            verified_shapes[cluster.get(qid, qid)].add(shapes[qid])
    bank, how = [], Counter()
    for q in questions:
        qid = q["id"]
        if qid not in shapes:
            how["không có plan"] += 1
            continue
        if qid in outcome:
            by = "answer" if outcome[qid] == "correct" else None
            how[f"có mapping: {outcome[qid]}"] += 1
        else:
            by = "template" if shapes[qid] in verified_shapes.get(cluster.get(qid, qid), set()) else None
            how["không mapping: " + ("cùng dạng plan đã kiểm chứng" if by else "chưa kiểm chứng được")] += 1
        if by:
            names = name_index.get(q["business_id"])
            bank.append({"id": qid, "business_id": q["business_id"], "question": q["question"],
                         "as_of_date": q["as_of_date"], "plan": plans[qid], "verified_by": by,
                         "text": template_text(q["question"], names)})
    BANK.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in bank), encoding="utf-8")
    print(f"{len(questions)} câu train, {sum(1 for p in plans.values() if p)} plan LLM dùng được")
    for k, n in sorted(how.items()):
        print(f"  {k}: {n}")
    print(f"Kho đã kiểm chứng: {len(bank)} plan → {BANK.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
