"""T4: choose the twin threshold. For each business with a hand mapping, its own questions are taken out of the
verified bank, its LLM plans are gated by twins from the other businesses only, and the answers they would give are
scored. A plan the rule-based baseline reads the same way passes without a twin.

    python -m datamate.eval.twin_gate                    # after python -m datamate.eval.build_bank

Prints, for each threshold, right / wrong / answered on the mapped businesses, and the threshold with the most
answers at ≥ 95% precision; the chosen one goes into configs/default.json ("twin_threshold"). When no threshold has
a wrong answer to stop, the second table tells them apart: on the other businesses, how many plans that differ from
the verified reading of their template (most of them misreadings) each threshold lets through.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from datamate.contracts import QueryPlan
from datamate.nlu import baseline, canonical_plan
from datamate.nlu.templates import NameIndex, plan_shape, template_text
from datamate.nlu.twins import TwinIndex

from .build_bank import NAMES, PLANS, TEMPLATES, current_plans, verify_by_answer

THRESHOLDS = (0, 80, 85, 90, 95, 100)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--target", type=float, default=95.0, help="độ chính xác tối thiểu (%)")
    args = ap.parse_args(argv)

    split = Path(args.data_root) / "train"
    questions = [json.loads(line) for line in (split / "questions.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    plans = current_plans(questions, {e["id"]: e["plan"]
                                      for e in map(json.loads, PLANS.read_text(encoding="utf-8").splitlines())})
    outcome = verify_by_answer(questions, plans, split)
    index = TwinIndex.from_file()
    names = {b: NameIndex([tuple(x) for x in ns]) for b, ns in json.loads(NAMES.read_text(encoding="utf-8")).items()}

    rows = []  # (outcome, twin score, baseline agrees)
    for q in questions:
        if q["id"] not in outcome:
            continue
        plan = QueryPlan.model_validate(plans[q["id"]])
        base = baseline.parse(q["question"])
        agree = base is not None and canonical_plan(base) == canonical_plan(plan)
        twin = index.twin(template_text(q["question"], names.get(q["business_id"])), plan,
                          exclude_business=q["business_id"])
        rows.append((outcome[q["id"]], twin, agree))

    n = len(rows)
    print(f"{n} câu có plan LLM ở các cửa hàng có mapping; kho {len(index)} câu đã kiểm chứng")
    print(f"\n  {'ngưỡng':>7}{'đúng':>7}{'sai':>6}{'trả lời':>9}{'chính xác':>11}{'PA':>8}")
    best = None
    for t in THRESHOLDS:
        passed = [o for o, twin, a in rows if a or twin.passes(t)]
        right, wrong = passed.count("correct"), passed.count("wrong")
        answered = right + wrong
        precision = right / answered * 100 if answered else 0.0
        print(f"  {t:>7}{right:>7}{wrong:>6}{answered:>9}{precision:>10.1f}%{(right - wrong) / n:>+8.3f}")
        if precision >= args.target and (best is None or answered > best[1]):
            best = (t, answered)
    print(f"\nNgưỡng chọn (chính xác ≥ {args.target:g}%, trả lời nhiều nhất): {best[0] if best else 'không có'}")

    # Businesses without a mapping have no answer to score, but a plan whose shape differs from the verified reading
    # of its template is most likely a misreading: how many such plans each threshold lets through.
    cluster = {i: k["id"] for k in json.loads(TEMPLATES.read_text(encoding="utf-8"))["clusters"] for i in k["ids"]}
    verified: dict[str, set[str]] = defaultdict(set)
    for qid, o in outcome.items():
        if o == "correct":
            verified[cluster.get(qid, qid)].add(plan_shape(QueryPlan.model_validate(plans[qid])))
    proxy = []  # (shape agrees with the verified reading of the template, twin, baseline agrees)
    for q in questions:
        c = cluster.get(q["id"], q["id"])
        if q["id"] in outcome or not plans.get(q["id"]) or c not in verified:
            continue
        plan = QueryPlan.model_validate(plans[q["id"]])
        base = baseline.parse(q["question"])
        agree = base is not None and canonical_plan(base) == canonical_plan(plan)
        twin = index.twin(template_text(q["question"], names.get(q["business_id"])), plan,
                          exclude_business=q["business_id"])
        proxy.append((plan_shape(plan) in verified[c], twin, agree))
    same, other = sum(s for s, _, _ in proxy), sum(not s for s, _, _ in proxy)
    print(f"\nCửa hàng không mapping, câu thuộc cụm đã có dạng kiểm chứng: {same} cùng dạng, {other} khác dạng "
          f"(khác dạng ≈ LLM đọc sai)")
    print(f"  {'ngưỡng':>7}{'cùng dạng qua':>15}{'khác dạng qua':>15}{'tỉ lệ cùng dạng':>17}")
    for t in THRESHOLDS:
        a = sum(1 for s, twin, b in proxy if s and (b or twin.passes(t)))
        o = sum(1 for s, twin, b in proxy if not s and (b or twin.passes(t)))
        print(f"  {t:>7}{a:>15}{o:>15}{a / max(a + o, 1) * 100:>16.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
