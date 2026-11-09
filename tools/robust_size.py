"""Time on a shop as big as the task allows (~300k rows): the shop's sales file(s) repeated with order codes made
unique until the shop has --rows data rows, then loader.load_business, prepare_business (mapping as production, LLM
cache) and every question of the shop answered with the plan of a live run, each timed. Compares with BUDGET_S (a
file read after the budget is skipped: the shop is answered from part of its data) and prints what the loader skipped.

    python tools/robust_size.py --shop dev_007 --rows 300000
    python tools/robust_size.py --shop dev_008 --rows 300000

Answers are not compared (the data changed); only time, skipped files and blanks. Development only.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from robust_layout import _csv_grid, _xlsx_grids, _write_xlsx, plans_of  # noqa: E402

from datamate import loader, rules  # noqa: E402
from datamate.contracts import QueryPlan  # noqa: E402
from datamate.eval.check_plans import check  # noqa: E402
from datamate.mapping import transfer  # noqa: E402
from datamate.pipeline import prepare_business, rule_ids  # noqa: E402
from datamate.predict import connect_llm  # noqa: E402

_CODE = re.compile(r"^[A-Za-z]{1,6}[-_]?\d{3,}$")


def _grow(grid: list[list[str]], times: int) -> list[list[str]]:
    """The grid's data rows repeated `times` times; in every copy after the first, code-like cells (ORD000001) get a
    suffix so each copy's orders are new orders."""
    head, body = grid[:1], grid[1:]
    out = head + body
    for k in range(1, times):
        out += [[f"{v}{k:02d}" if _CODE.match(v or "") and not v.startswith(("SP", "NV", "KH")) else v for v in r]
                for r in body]
    return out


def build(src: Path, dst: Path, rows: int) -> int:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    big = {}
    for f in dst.iterdir():
        if f.suffix.lower() == ".csv":
            g, d = _csv_grid(f)
            big[f] = ("csv", {"_": g}, d)
        elif f.suffix.lower() in (".xlsx",):
            big[f] = ("xlsx", _xlsx_grids(f), None)
    total = sum(len(g) - 1 for _, gs, _ in big.values() for g in gs.values())
    biggest = max(big, key=lambda f: sum(len(g) for g in big[f][1].values()))
    n_big = sum(len(g) - 1 for g in big[biggest][1].values())
    times = max(1, round((rows - (total - n_big)) / n_big))
    kind, grids, delim = big[biggest]
    grids = {s: _grow(g, times) for s, g in grids.items()}
    if kind == "csv":
        buf = io.StringIO()
        csv.writer(buf, delimiter=delim, lineterminator="\n").writerows(grids["_"])
        biggest.write_text(buf.getvalue(), encoding="utf-8")
    else:
        biggest.unlink()
        _write_xlsx(biggest, grids)
    return total - n_big + sum(len(g) - 1 for g in grids.values())


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="public_test")
    ap.add_argument("--shop", required=True)
    ap.add_argument("--rows", type=int, default=300000)
    ap.add_argument("--run", default="outputs/public_live_778f898")
    ap.add_argument("--llm-url", default="http://127.0.0.1:8091")
    ap.add_argument("--llm-cache", default="outputs/llm_cache_mapping_robust.jsonl")
    ap.add_argument("--out", default="outputs/robust_size")
    ap.add_argument("--no-build", action="store_true")
    args = ap.parse_args(argv)
    split_dir = ROOT / "data" / args.split
    dst = ROOT / args.out / args.shop
    t = time.perf_counter()
    if not args.no_build:
        n = build(split_dir / "data" / args.shop, dst, args.rows)
        print(f"build: {n} dòng dữ liệu, {time.perf_counter() - t:.0f}s", flush=True)
    llm = connect_llm(args.llm_url, cache=args.llm_cache)
    t = time.perf_counter()
    raw = loader.load_business(dst)
    t_load = time.perf_counter() - t
    print(f"load_business: {t_load:.1f}s (BUDGET_S {loader.BUDGET_S:.0f}); bảng {len(raw.tables)}; "
          f"cảnh báo bỏ qua: {[w for w in raw.warnings if 'bỏ qua' in w]}", flush=True)
    rulebook = (split_dir / "rulebook.md").read_text(encoding="utf-8-sig")
    rule_status = rules.check_rules(rulebook, rule_ids())

    def map_fn(raw, profile, rulebook_text, _llm=None):
        m, tried = transfer.map_by_transfer(raw, llm=llm)
        return m if m is not None else transfer.failed(tried)
    t = time.perf_counter()
    ctx = prepare_business(dst, rulebook, None, map_fn)
    t_prep = time.perf_counter() - t
    print(f"prepare_business: {t_prep:.1f}s, mapping ok {ctx.mapping.ok}; "
          f"{ctx.error.splitlines()[-1] if ctx.error else ''}", flush=True)
    qs = [json.loads(x) for x in (split_dir / "questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    qs = [q for q in qs if q["business_id"] == args.shop]
    plans = plans_of(args.split, qs, ROOT / args.run)
    t, blank, slow = time.perf_counter(), 0, []
    for q in qs:
        t1 = time.perf_counter()
        try:
            line = check(q, QueryPlan.model_validate(plans[q["id"]]), ctx, split_dir / "calendar.csv", rule_status)["line"] \
                if plans.get(q["id"]) and ctx.mapping.ok else {"type": "abstain"}
        except Exception as e:
            line = {"type": "abstain", "error": type(e).__name__}
        blank += line.get("type") == "abstain"
        slow.append(time.perf_counter() - t1)
    t_ans = time.perf_counter() - t
    slow.sort()
    print(f"answer {len(qs)} câu: {t_ans:.1f}s, trống {blank}; chậm nhất {slow[-3:] if slow else []}", flush=True)
    print(json.dumps({"shop": args.shop, "load_s": round(t_load, 1), "prep_s": round(t_prep, 1),
                      "answer_s": round(t_ans, 1), "n_q": len(qs), "blank": blank}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
