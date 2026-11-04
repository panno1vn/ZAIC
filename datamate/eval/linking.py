"""T2: how well [C3] links the names of plan filters to the data, on the train businesses with a hand mapping.

    python -m datamate.eval.linking --out outputs/linking/run.jsonl                       # hand + cached plans
    python -m datamate.eval.linking --llm-url http://127.0.0.1:8091 --out outputs/linking/run.jsonl

Questions: those of the mapped businesses whose T1 template (assets/plans/templates_train.json) filters on a linked
field. Plan: the hand plan, else the LLM's (cached in outputs/linking/llm_plans.jsonl). Each filter value is linked
against the canonical data built with the hand mapping. Development only: train data, hand mappings.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from datamate.contracts import DataCard, Mapping, QueryPlan
from datamate.loader import load_business
from datamate.mapping import build_canonical
from datamate.nlu import linking, prompt
from datamate.verify import LINKED_FIELDS, filter_keys

from .oracle import mapping_files

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "assets" / "plans" / "templates_train.json"
CACHE = ROOT / "outputs" / "linking" / "llm_plans.jsonl"


def hand_plans() -> dict[str, dict]:
    out = {}
    for f in prompt.HAND_FILES:  # not the verified bank (T4): hand plans only
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                out[e["id"]] = e["plan"]
    return out


def chosen_questions(questions: list[dict], businesses: set[str]) -> list[dict]:
    """Questions of the businesses whose template's plan shape filters on a linked field."""
    pat = re.compile(r"\[(?:[^\]]*,)?(?:%s)[.,\]]" % "|".join(sorted(LINKED_FIELDS)))
    clusters = json.loads(TEMPLATES.read_text(encoding="utf-8"))["clusters"]
    ids = {i for k in clusters if k["shape"] and pat.search(k["shape"]) for i in k["ids"]}
    return [q for q in questions if q["id"] in ids and q["business_id"] in businesses]


def llm_plans(questions: list[dict], url: str | None) -> dict[str, dict | None]:
    cache: dict[str, dict | None] = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            cache[e["id"]] = e["plan"]
    todo = [q for q in questions if q["id"] not in cache]
    if todo and url:
        from datamate.llm import LlamaServerLLM
        from datamate.nlu import llm_plan
        llm = LlamaServerLLM(url, timeout_s=60.0)
        if not llm.healthy():
            sys.exit(f"không gọi được {url}/health")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE.open("a", encoding="utf-8") as f:
            for n, q in enumerate(todo, 1):
                p = llm_plan(q["question"], date.fromisoformat(q["as_of_date"]), DataCard(), llm)
                cache[q["id"]] = p.model_dump(mode="json", exclude_none=True) if p else None
                f.write(json.dumps({"id": q["id"], "plan": cache[q["id"]]}, ensure_ascii=False) + "\n")
                f.flush()
                if n % 25 == 0:
                    print(f"  LLM {n}/{len(todo)}", flush=True)
    return cache


def link_rows(q: dict, plan: QueryPlan, db) -> list[dict]:
    p = plan
    measures = list(p.measures) + ([p.share_of] if p.share_of else [])
    filters = [f for m in measures for f in m.filters] + list((p.compare.filters or []) if p.compare else [])
    rows = []
    for f in filters:
        if f.field not in LINKED_FIELDS:
            continue
        cands = linking.candidates(f.field, db)
        units = linking.units(db) if f.field == "product" else ()
        for key in filter_keys(f):
            got = linking.link_value(f.field, key, q["question"], cands, units)
            names = sorted(n for n, vs in cands.items() if got.value in vs)[:3] if got.value is not None else []
            rows.append({"id": q["id"], "business_id": q["business_id"], "question": q["question"], "field": f.field,
                         "written": key, "how": got.how, "score": round(got.score, 1), "value": got.value,
                         "names": names, "n_candidates": len(cands)})
    return rows


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--llm-url")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    split = Path(args.data_root) / "train"
    files = mapping_files("train")
    questions = [json.loads(line) for line in (split / "questions.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    chosen = chosen_questions(questions, set(files))
    hand = hand_plans()
    llm = llm_plans([q for q in chosen if q["id"] not in hand], args.llm_url)

    rows, no_plan = [], 0
    by_business = defaultdict(list)
    for q in chosen:
        by_business[q["business_id"]].append(q)
    for b, qs in sorted(by_business.items()):
        m = Mapping.model_validate(json.loads(files[b].read_text(encoding="utf-8")))
        db = build_canonical(load_business(split / "data" / b), m)
        for q in qs:
            raw = hand.get(q["id"]) or llm.get(q["id"])
            if raw is None:
                no_plan += 1
                continue
            rows += link_rows(q, QueryPlan.model_validate(raw), db)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(chosen)} câu có bộ lọc cần nối ở {len(by_business)} cửa hàng; {no_plan} câu không có plan; "
          f"{len(rows)} giá trị bộ lọc")
    by_field: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_field[r["field"]][r["how"]] += 1
    hows = ("exact", "question", "fuzzy", "tie", "none")
    print(f"\n  {'trường':<18}{'n':>5}" + "".join(f"{h:>10}" for h in hows) + f"{'nối được':>10}")
    for field, c in sorted(by_field.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        print(f"  {field:<18}{n:>5}" + "".join(f"{c[h]:>10}" for h in hows)
              + f"{(c['exact'] + c['question'] + c['fuzzy']) / n:>10.0%}")
    print("\nKhông nối hoặc nối mờ (xem đủ trong file --out):")
    for r in rows:
        if r["how"] not in ("exact",):
            print(f"  [{r['how']} {r['score']}] {r['field']} {r['written']!r} -> {r['value']} {r['names']}"
                  f"\n      {r['business_id']} {r['question'][:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
