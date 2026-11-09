"""Robustness to file layout: the private test brings shops never seen, laid out their own way. The same shops of
train and public, their files rewritten without changing any figure (columns in another order, an extra column,
headers without accents, dates written dd/mm/yyyy, csv <-> xlsx), must answer exactly as before. Every question whose
answer moves is a fragility a private shop may hit.

    python tools/robust_layout.py --split train --llm-url http://127.0.0.1:8091
    python tools/robust_layout.py --split public_test --variants identity,unaccent --shops dev_003 dev_006

Each shop is mapped as production maps it (transfer, README enrichment; a train shop with its own hand mapping left
out of the examples), from the rewritten files; each question is answered with the plan already read (train: the
plan bank; public: the plans of a live run's logs), so only the layout differs. `identity` rewrites the files with no
change: it checks the rewriting itself. Answers are compared with the original layout's, never with public gold;
public variants are graded in aggregate only (tools/grade_public.py). Development only.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from python_calamine import CalamineWorkbook  # noqa: E402

from datamate import rules  # noqa: E402
from datamate.contracts import QueryPlan  # noqa: E402
from datamate.eval.build_bank import PLANS, current_plans  # noqa: E402
from datamate.eval.check_plans import check  # noqa: E402
from datamate.eval.scorer import score_line  # noqa: E402
from datamate.loader import _decode  # noqa: E402
from datamate.loader.grid import cell_text, find_header  # noqa: E402
from datamate.mapping import transfer  # noqa: E402
from datamate.nlu.grounding import customer_trait_not_recorded  # noqa: E402
from datamate.pipeline import NOT_RECORDED_REASON, prepare_business, rule_ids  # noqa: E402
from datamate.predict import connect_llm  # noqa: E402

VARIANTS = ("identity", "reorder", "extra_col", "unaccent", "date_dmy", "fmt_swap")
# the README alone thinned (files unchanged): the task warns some private READMEs are almost empty
README_VARIANTS = ("readme_line1", "readme_none")
# file oddities: money with separators, Excel serial dates, title rows, duplicate column, empty sheets, sqlite tables renamed
ODD_VARIANTS = ("money_dot", "money_comma", "date_serial", "title_rows", "dup_col", "empty_sheet", "sqlite_rename",
                "one_sheet_odd")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$")


# ---------------------------------------------------------------- grids: read and write as the loader sees them
def _csv_grid(f: Path) -> tuple[list[list[str]], str]:
    text, _ = _decode(f.read_bytes())
    first = text.split("\n", 1)[0]
    delim = max([",", ";", "\t"], key=first.count)
    return [r for r in csv.reader(io.StringIO(text), delimiter=delim)], delim


def _xlsx_grids(f: Path) -> dict[str, list[list[str]]]:
    wb = CalamineWorkbook.from_path(str(f))
    return {s: [[cell_text(v) for v in row] for row in wb.get_sheet_by_name(s).to_python(skip_empty_area=False)]
            for s in wb.sheet_names}


def _sqlite_grids(f: Path) -> dict[str, list[list[str]]]:
    con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
    try:
        out = {}
        for (t,) in con.execute("select name from sqlite_master where type='table'"):
            df = pd.read_sql_query(f'select * from "{t}"', con)
            df = df.astype(object).where(df.notna(), None).map(cell_text)
            out[t] = [list(map(str, df.columns))] + df.astype(str).values.tolist()
        return out
    finally:
        con.close()


def _write_csv(f: Path, grid: list[list[str]], delim: str = ",") -> None:
    buf = io.StringIO()
    csv.writer(buf, delimiter=delim, lineterminator="\n").writerows(grid)
    f.write_text(buf.getvalue(), encoding="utf-8")


def _write_xlsx(f: Path, grids: dict[str, list[list[str]]]) -> None:
    with pd.ExcelWriter(f, engine="openpyxl") as w:
        for sheet, grid in grids.items():
            pd.DataFrame(grid).to_excel(w, sheet_name=sheet[:31], header=False, index=False)


def _write_sqlite(f: Path, grids: dict[str, list[list[str]]]) -> None:
    con = sqlite3.connect(f)
    try:
        for t, grid in grids.items():
            cols, rows = grid[0], grid[1:]
            df = pd.DataFrame(rows, columns=cols).replace({"": None})
            df.to_sql(t, con, index=False)
    finally:
        con.close()


# ---------------------------------------------------------------- the transforms (figures never change)
def _square(grid: list[list[str]]) -> list[list[str]]:
    width = max((len(r) for r in grid), default=0)
    return [list(r) + [""] * (width - len(r)) for r in grid]


def _unaccent(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def transform(grid: list[list[str]], variant: str, renamed: dict[str, str]) -> list[list[str]]:
    grid = _square(grid)
    if not grid or variant in ("identity", "fmt_swap") + README_VARIANTS:
        return grid
    h, _ = find_header(grid)
    if variant == "reorder":
        return [list(reversed(r)) for r in grid]
    if variant == "extra_col":
        return [(["Ghi chú nội bộ"] if i == h else [""]) + r for i, r in enumerate(grid)]
    if variant == "unaccent":
        out = [list(r) for r in grid]
        for j, name in enumerate(out[h]):
            new = _unaccent(name)
            if new != name:
                renamed[name] = new
                out[h][j] = new
        return out
    if variant == "date_dmy":
        def dmy(v: str) -> str:
            m = _ISO.match(v.strip())
            if not m:
                return v
            day = f"{m[3]}/{m[2]}/{m[1]}"
            if m[4] is None or (m[4] == "00" and m[5] == "00" and (m[6] in (None, "00"))):
                return day
            return f"{day} {m[4]}:{m[5]}" + (f":{m[6]}" if m[6] not in (None, "00") else "")
        return [r if i <= h else [dmy(v) for v in r] for i, r in enumerate(grid)]
    if variant in ("money_dot", "money_comma"):
        # integer columns with big values (money): "1.234.000đ" or "1,234,000"; codes/phones (leading 0) untouched
        out = [list(r) for r in grid]
        for j in range(len(out[h])):
            vals = [r[j] for r in out[h + 1:] if r[j].strip()]
            if not vals or not all(re.fullmatch(r"-?[1-9]\d*(\.0+)?", v.strip()) or v.strip() == "0" for v in vals):
                continue
            if max(abs(int(float(v))) for v in vals) < 10000 or re.search(r"(?i)mã|ma |sđt|phone|đt|số dòng|no\.", out[h][j]):
                continue
            for r in out[h + 1:]:
                v = r[j].strip()
                if v:
                    n = int(float(v))
                    r[j] = f"{n:,}".replace(",", ".") + "đ" if variant == "money_dot" else f"{n:,}"
        return out
    if variant == "date_serial":  # ISO day cells as Excel serial day numbers (time kept as fraction)
        import datetime as _dt
        def ser(v: str) -> str:
            m = _ISO.match(v.strip())
            if not m:
                return v
            d = _dt.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4] or 0), int(m[5] or 0), int(m[6] or 0))
            x = (d - _dt.datetime(1899, 12, 30)).total_seconds() / 86400
            return str(int(x)) if x == int(x) else f"{x:.6f}"
        return [r if i <= h else [ser(v) for v in r] for i, r in enumerate(grid)]
    if variant == "title_rows":  # a report title and a blank row above the header
        w = len(grid[0])
        return [["BÁO CÁO XUẤT TỪ PHẦN MỀM"] + [""] * (w - 1), [""] * w] + grid
    if variant == "dup_col":  # the first column repeated at the end under the same header
        return [r + [r[0]] for r in grid]
    if variant in ("empty_sheet", "sqlite_rename", "one_sheet_odd"):
        return grid
    raise ValueError(variant)


def write_variant(src: Path, dst: Path, variant: str) -> None:
    """The shop `src` rewritten into `dst` under `variant`; its README follows renamed columns and files."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    renamed: dict[str, str] = {}
    files: dict[str, str] = {}
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = f.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        ext = f.suffix.lower()
        if ext == ".csv":
            grid, delim = _csv_grid(f)
            grid = transform(grid, variant, renamed)
            if variant == "fmt_swap":
                out = out.with_suffix(".xlsx")
                files[f.name] = out.name
                _write_xlsx(out, {"Sheet1": grid})
            else:
                _write_csv(out, grid, delim)
        elif ext in (".xlsx", ".xlsm"):
            grids = {s: transform(g, variant, renamed) for s, g in _xlsx_grids(f).items()}
            if variant == "one_sheet_odd" and len(grids) >= 3:
                # a workbook of month sheets where one month was typed by hand: headers without accents, columns
                # in another order (only that sheet)
                s = list(grids)[len(grids) // 2]
                g = _square(_xlsx_grids(f)[s])
                hh, _ = find_header(g)
                g = [list(reversed([_unaccent(v) for v in r] if i == hh else r)) for i, r in enumerate(g)]
                grids[s] = g
            if variant == "empty_sheet":
                grids = {"Trang trống": [[""]], **grids, "Sheet9": [[""]]}
            if variant == "fmt_swap" and len(grids) == 1:
                out = out.with_suffix(".csv")
                files[f.name] = out.name
                _write_csv(out, next(iter(grids.values())))
            else:
                _write_xlsx(out.with_suffix(".xlsx"), grids)
        elif ext == ".sqlite":
            grids = {}
            for k, (t, g) in enumerate(_sqlite_grids(f).items()):
                name = f"tbl_{k + 1}" if variant == "sqlite_rename" else t
                if name != t:
                    renamed[t] = name
                grids[name] = transform(g, variant, renamed)
            _write_sqlite(out, grids)
        elif f.name != "README.md":
            shutil.copy2(f, out)
    readme = (src / "README.md").read_text(encoding="utf-8") if (src / "README.md").exists() else ""
    for old, new in sorted(renamed.items(), key=lambda kv: -len(kv[0])):
        readme = readme.replace(f"**{old}**", f"**{new}**").replace(f"`{old}`", f"`{new}`").replace(f".{old}`", f".{new}`")
    for old, new in files.items():
        readme = readme.replace(old, new)
    if variant == "readme_line1":
        readme = readme.split("\n", 1)[0] + "\n"
    if variant != "readme_none":
        (dst / "README.md").write_text(readme, encoding="utf-8")


# ---------------------------------------------------------------- answering
def plans_of(split: str, questions: list[dict], run: Path) -> dict[str, dict | None]:
    if split == "train":
        return current_plans(questions, {e["id"]: e["plan"] for e in
                                         map(json.loads, PLANS.read_text(encoding="utf-8").splitlines())})
    out = {}
    for q in questions:
        f = run / "logs" / f"{q['id']}.json"
        out[q["id"]] = json.loads(f.read_text(encoding="utf-8")).get("plan") if f.exists() else None
    return out


def answer_shop(root: Path, b: str, qs: list[dict], plans: dict, split_dir: Path, rulebook: str, rule_status: dict,
                llm, leave_out: bool) -> tuple[dict[str, dict], str]:
    pool = transfer.examples(leave_out=b) if leave_out else transfer.examples()

    def map_fn(raw, profile, rulebook_text, _llm=None):
        m, tried = transfer.map_by_transfer(raw, pool, llm=llm)
        return m if m is not None else transfer.failed(tried)
    ctx = prepare_business(root, rulebook, None, map_fn)
    lines = {}
    for q in qs:
        p = plans.get(q["id"])
        if ctx.mapping.ok and ctx.raw is not None and customer_trait_not_recorded(q["question"], ctx.raw.readme or ""):
            p = {"intent": "out_of_scope", "out_of_scope_reason": NOT_RECORDED_REASON}
        if not ctx.mapping.ok or p is None:
            lines[q["id"]] = {"id": q["id"], "type": "abstain"}
            continue
        try:
            lines[q["id"]] = check(q, QueryPlan.model_validate(p), ctx, split_dir / "calendar.csv", rule_status)["line"]
        except Exception as e:  # a crash on a rewritten layout is a finding, not a stop
            lines[q["id"]] = {"id": q["id"], "type": "abstain", "error": type(e).__name__}
    how = ctx.mapping.notes[0] if ctx.mapping.ok and ctx.mapping.notes else ("không có mapping: " + (
        ctx.error.splitlines()[-1] if ctx.error else "; ".join(c.detail for c in ctx.mapping.checks if not c.passed)[:90]))
    return lines, how


def same(a: dict, b: dict) -> bool:
    return a.get("type") == b.get("type") and json.dumps(a.get("answer"), sort_keys=True, ensure_ascii=False) == \
        json.dumps(b.get("answer"), sort_keys=True, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=("train", "public_test"), default="train")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--shops", nargs="*")
    ap.add_argument("--run", default="outputs/public_live_778f898", help="public: the live run whose plans are used")
    ap.add_argument("--llm-url", default="http://127.0.0.1:8091")
    ap.add_argument("--llm-cache", default="outputs/llm_cache_mapping_robust.jsonl")
    ap.add_argument("--out", default="outputs/robust")
    args = ap.parse_args(argv)

    split_dir = ROOT / "data" / args.split
    cache = Path(args.llm_cache)
    if not cache.exists() and (ROOT / "outputs" / "llm_cache_mapping.jsonl").exists():
        shutil.copy2(ROOT / "outputs" / "llm_cache_mapping.jsonl", cache)  # the train mapping calls answered already
    llm = connect_llm(args.llm_url, cache=str(cache))
    if llm is None:
        return 1
    questions = [json.loads(x) for x in (split_dir / "questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    by_shop: dict[str, list[dict]] = {}
    for q in questions:
        by_shop.setdefault(q["business_id"], []).append(q)
    shops = sorted(args.shops or by_shop)
    plans = plans_of(args.split, questions, ROOT / args.run)
    rulebook = (split_dir / "rulebook.md").read_text(encoding="utf-8-sig")
    rule_status = rules.check_rules(rulebook, rule_ids())
    gold = {a["id"]: a for a in map(json.loads, (split_dir / "answers.jsonl").read_text(encoding="utf-8").splitlines())} \
        if args.split == "train" else None
    out = ROOT / args.out
    leave_out = args.split == "train"

    base: dict[str, dict] = {}
    print(f"gốc: {args.split}, {len(shops)} cửa hàng")
    for b in shops:
        lines, _ = answer_shop(split_dir / "data" / b, b, by_shop[b], plans, split_dir, rulebook, rule_status, llm, leave_out)
        base.update(lines)
    summary = {}
    for variant in args.variants.split(","):
        changed, per_shop, diffs, lines_v = Counter(), {}, [], {}
        for b in shops:
            dst = out / variant / args.split / b
            write_variant(split_dir / "data" / b, dst, variant)
            lines, how = answer_shop(dst, b, by_shop[b], plans, split_dir, rulebook, rule_status, llm, leave_out)
            lines_v.update(lines)
            n = 0
            for qid, line in lines.items():
                if not same(line, base[qid]):
                    n += 1
                    o_before = score_line(base[qid], gold[qid]).outcome if gold else None
                    o_after = score_line(line, gold[qid]).outcome if gold else None
                    changed[(o_before, o_after) if gold else (base[qid].get("type") == "abstain", line.get("type") == "abstain")] += 1
                    diffs.append({"id": qid, "business_id": b, "before": base[qid], "after": line,
                                  "outcome": [o_before, o_after]})
            per_shop[b] = (n, len(lines), how)
        (out / f"{args.split}_{variant}.jsonl").write_text(
            "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in diffs), encoding="utf-8")
        moved = sum(n for n, _, _ in per_shop.values())
        print(f"\n== {variant}: {moved} câu đổi đáp án / {sum(t for _, t, _ in per_shop.values())}")
        for b, (n, t, how) in per_shop.items():
            if n:
                print(f"   {b:9} {n:4} / {t:<4} {how[:90]}")
        if gold:
            print("   (trước -> sau):", dict(changed))
        else:
            sub = out / f"{args.split}_{variant}_submission.jsonl"
            sub.write_text("".join(json.dumps(lines_v[q["id"]], ensure_ascii=False) + "\n" for q in questions
                                   if q["id"] in lines_v), encoding="utf-8")
            if not args.shops:
                g = subprocess.run([sys.executable, str(ROOT / "tools" / "grade_public.py"), str(sub)],
                                   capture_output=True, text=True, encoding="utf-8")
                print("   " + "\n   ".join(g.stdout.splitlines()[1:2]))
        summary[variant] = moved
    print("\ntóm tắt:", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
