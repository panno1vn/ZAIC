"""Robustness to wording: the private test asks the same things in words never seen. A sample of train and public
questions, reworded without changing what they ask (accents dropped, the shorthand shops type — "dthu", "bnhiu", "đh",
"đc", "ko" — or the reverse, a polite opening and ending), is read again by the LLM and answered on the same shop;
the answer must not move. A rule written for one wording shows up here as an answer that moves.

    python tools/robust_wording.py --split train --n 150 --llm-url http://127.0.0.1:8091
    python tools/robust_wording.py --split public_test --n 100 --variants noaccent,filler

Reading goes through nlu.parse_question as the pipeline reads (train: the business's own questions left out of the
examples); the original answer is the same chain on the original wording, read the same way now. Public answers are
compared with the original wording's only, never with public gold. Development only.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datamate import nlu, rules  # noqa: E402
from datamate.contracts import DataCard, QueryPlan  # noqa: E402
from datamate.eval.check_plans import check  # noqa: E402
from datamate.eval.scorer import score_line  # noqa: E402
from datamate.mapping import transfer  # noqa: E402
from datamate.nlu import prompt  # noqa: E402
from datamate.nlu.grounding import customer_trait_not_recorded  # noqa: E402
from datamate.pipeline import NOT_RECORDED_REASON, prepare_business, rule_ids  # noqa: E402
from datamate.predict import connect_llm  # noqa: E402

VARIANTS = ("noaccent", "abbrev", "expand", "filler")
# the shorthand shops type, as the questions of train and public write it (whole words, either case)
SHORT = (("doanh thu", "dthu"), ("bao nhiêu", "bnhiu"), ("đơn hàng", "đh"), ("được", "đc"), ("không", "ko"),
         ("khách hàng", "khách"), ("hôm nay", "hnay"), ("hôm qua", "hqua"), ("tháng", "th"))


def _unaccent(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _swap(q: str, pairs, forward: bool) -> str:
    out = unicodedata.normalize("NFC", q)
    for long, short in pairs:
        a, b = (long, short) if forward else (short, long)
        out = re.sub(rf"(?i)(?<!\w){re.escape(a)}(?!\w)", b, out)
    return out


def reword(q: str, variant: str) -> str | None:
    """The question in other words, or None when the variant changes nothing."""
    if variant == "noaccent":
        new = _unaccent(q)
    elif variant == "abbrev":
        new = _swap(q, SHORT, True)
    elif variant == "expand":
        new = _swap(q, [p for p in SHORT if p[1] not in ("th", "khách")], False)  # "th", "khách" mean other things too
    elif variant == "filler":
        new = "cho mình hỏi, " + q.rstrip(" ?.") + " vậy ạ?"
    else:
        raise ValueError(variant)
    return new if new != q else None


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=("train", "public_test"), default="train")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--n", type=int, default=150, help="questions sampled per variant (among those it changes)")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--llm-url", default="http://127.0.0.1:8091")
    ap.add_argument("--llm-cache", default="outputs/llm_cache_wording.jsonl")
    ap.add_argument("--mapping-cache", default="outputs/llm_cache_mapping_robust.jsonl")
    ap.add_argument("--out", default="outputs/robust")
    args = ap.parse_args(argv)

    split_dir = ROOT / "data" / args.split
    llm = connect_llm(args.llm_url, cache=args.llm_cache)
    map_llm = connect_llm(args.llm_url, cache=args.mapping_cache)
    if llm is None or map_llm is None:
        return 1
    questions = [json.loads(x) for x in (split_dir / "questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    gold = {a["id"]: a for a in map(json.loads, (split_dir / "answers.jsonl").read_text(encoding="utf-8").splitlines())} \
        if args.split == "train" else None
    rulebook = (split_dir / "rulebook.md").read_text(encoding="utf-8-sig")
    rule_status = rules.check_rules(rulebook, rule_ids())
    bank = prompt.ExampleBank(prompt.HAND_FILES)
    business = {q["id"]: q["business_id"] for q in questions}
    ctxs = {}

    def ctx_of(b: str):
        if b not in ctxs:
            pool = transfer.examples(leave_out=b) if args.split == "train" else transfer.examples()

            def map_fn(raw, profile, rb, _llm=None):
                m, tried = transfer.map_by_transfer(raw, pool, llm=map_llm)
                return m if m is not None else transfer.failed(tried)
            ctxs[b] = prepare_business(split_dir / "data" / b, rulebook, None, map_fn)
        return ctxs[b]

    def answer(q: dict, text: str) -> dict:
        b = q["business_id"]
        same = frozenset(e["id"] for e in bank.items if business.get(e["id"]) == b) if args.split == "train" else frozenset()
        ctx = ctx_of(b)
        plan = nlu.parse_question(text, date.fromisoformat(q["as_of_date"]), DataCard(), llm, exclude_ids=same)
        if ctx.mapping.ok and ctx.raw is not None and customer_trait_not_recorded(text, ctx.raw.readme or ""):
            plan = QueryPlan(intent="out_of_scope", out_of_scope_reason=NOT_RECORDED_REASON)
        if plan is None or not ctx.mapping.ok:
            return {"id": q["id"], "type": "abstain"}
        return check({**q, "question": text}, plan, ctx, split_dir / "calendar.csv", rule_status)["line"]

    def same_answer(a: dict, b: dict) -> bool:
        return a.get("type") == b.get("type") and json.dumps(a.get("answer"), sort_keys=True, ensure_ascii=False) == \
            json.dumps(b.get("answer"), sort_keys=True, ensure_ascii=False)

    rng = random.Random(args.seed)
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for variant in args.variants.split(","):
        pool_q = [q for q in questions if reword(q["question"], variant)]
        sample = rng.sample(pool_q, min(args.n, len(pool_q)))
        moved, how, rows, by_shop = 0, Counter(), [], defaultdict(int)
        for q in sample:
            new_text = reword(q["question"], variant)
            before, after = answer(q, q["question"]), answer(q, new_text)
            if same_answer(before, after):
                continue
            moved += 1
            by_shop[q["business_id"]] += 1
            if gold:
                key = (score_line(before, gold[q["id"]]).outcome, score_line(after, gold[q["id"]]).outcome)
            else:
                key = ("blank" if before.get("type") == "abstain" else "answer",
                       "blank" if after.get("type") == "abstain" else "answer")
            how[key] += 1
            rows.append({"id": q["id"], "business_id": q["business_id"], "question": q["question"],
                         "reworded": new_text, "before": before, "after": after, "outcome": list(key)})
        (out / f"wording_{args.split}_{variant}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(f"== {variant}: {moved} / {len(sample)} đáp án đổi  (trước -> sau) {dict(how)}", flush=True)
        summary[variant] = (moved, len(sample))
    print("tóm tắt:", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
