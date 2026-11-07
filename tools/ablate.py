"""A diagnostic submission: a run's file with some of its answers turned into abstain, chosen from the run's own logs
(N22: counts and the system's own logs only, no public file is read). Submitted next to the run itself, the score
difference gives right minus wrong of the answers left out: wrong = (n - (score_run - score_diag) * 1000) / 2.

    python tools/ablate.py outputs/public_run6 --out outputs/public_ablation6/bo_cua_hang_moi.jsonl \
        --new-shops-vs outputs/public_run4
    python tools/ablate.py outputs/public_run6 --out x.jsonl --function debt.value_of debt.rank_debtors
    python tools/ablate.py outputs/public_run6 --out x.jsonl --new-answers-vs outputs/public_run4_twin_off

--new-shops-vs RUN: abstain every answer of a shop that had no mapping in RUN (shops mapped by the new paths).
--new-answers-vs RUN: abstain every answer RUN did not give (what the code since RUN added).
--shops S...: abstain every answer of these shops.
--function F... / --metric M... / --entity E...: abstain the answers computed by these functions, of plans with these
metrics, ranking or counting these entities (all given must hold).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load(path: Path) -> dict[str, dict]:
    return {r["id"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r}


def answered(sub: dict[str, dict]) -> set[str]:
    return {k for k, r in sub.items() if r.get("type") != "abstain"}


def logs(run: Path) -> dict[str, dict]:
    out = {}
    for f in (run / "logs").glob("q_*.json"):
        x = json.loads(f.read_text(encoding="utf-8"))
        plan = (x.get("resolved") or {}).get("plan") or {}
        out[x["id"]] = {"shop": x["business_id"], "function": (x.get("result") or {}).get("function"),
                        "metrics": {m.get("metric") for m in plan.get("measures", [])},
                        "entity": (plan.get("rank") or {}).get("entity") or (plan.get("count_spec") or {}).get("entity")}
    return out


def unmapped_shops(run: Path) -> set[str]:
    out = set()
    for f in (run / "logs").glob("_business_*.json"):
        b = json.loads(f.read_text(encoding="utf-8"))
        checks = (b.get("mapping") or {}).get("checks") or []
        if any(c.get("name") == "mapping" and not c.get("passed") for c in checks) or not checks:
            out.add(b["business_id"])
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--new-shops-vs", type=Path)
    ap.add_argument("--new-answers-vs", type=Path)
    ap.add_argument("--function", nargs="*", default=[])
    ap.add_argument("--metric", nargs="*", default=[], help="chỉ số của plan; đi cùng --function thì phải khớp cả hai")
    ap.add_argument("--entity", nargs="*", default=[], help="đối tượng xếp hạng / đếm (customer, product, day…)")
    ap.add_argument("--shops", nargs="*", default=[], help="bỏ trống mọi câu trả lời của các cửa hàng này")
    args = ap.parse_args(argv)
    sub, info = load(args.run / "submission.jsonl"), logs(args.run)
    drop: set[str] = set()
    if args.new_shops_vs is not None:
        before = unmapped_shops(args.new_shops_vs)
        drop |= {k for k in answered(sub) if info.get(k, {}).get("shop") in before}
    if args.new_answers_vs is not None:
        drop |= answered(sub) - answered(load(args.new_answers_vs / "submission.jsonl"))
    if args.function or args.metric or args.entity:
        def picked(i: dict) -> bool:
            fn_ok = not args.function or i.get("function") in args.function
            metric_ok = not args.metric or bool(i.get("metrics", set()) & set(args.metric))
            return fn_ok and metric_ok and (not args.entity or i.get("entity") in args.entity)
        drop |= {k for k in answered(sub) if picked(info.get(k, {}))}
    if args.shops:
        drop |= {k for k in answered(sub) if info.get(k, {}).get("shop") in set(args.shops)}
    out = [{"id": k, "type": "abstain"} if k in drop else r for k, r in sub.items()]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    by = Counter((info.get(k, {}).get("shop"), info.get(k, {}).get("function")) for k in drop)
    print(f"{args.run}: {len(answered(sub))} câu trả lời; bỏ trống thêm {len(drop)} → còn {len(answered(sub)) - len(drop)}")
    for (shop, fn), n in sorted(by.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {n:4}  {shop}  {fn}")
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
