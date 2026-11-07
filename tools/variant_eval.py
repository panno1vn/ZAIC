"""N27, train only: a hand-mapped train shop with its columns renamed, as another shop of the same software would name
them, mapped by the automatic chain and scored with the train answers (the data are the same, so the answers are).

Why: the shops of one export format share their files but each names its columns its own way (train: don_hang.csv of
three shops, "Ma don" / "Mã chứng từ" / "Số HĐ"). Matching by column names then fails and only the paths by meaning
can map the shop. On public 6 of 14 shops get no mapping at all (counted from the run logs), on train 2 of 30: the
measure has to come from train shops made unfamiliar.

    python tools/variant_eval.py --llm-url http://127.0.0.1:8091                    # every hand-mapped shop
    python tools/variant_eval.py --llm-url ... --business biz_123 --leave-out       # its own mapping not an example

Renaming: a column the hand mapping reads as X takes the name another hand-mapped shop gives X (sorted, the first
not taken); any other column, or one no other shop names, is respelled (accents dropped, CamelCase <-> words). The
README is rewritten with the new names. A database file is renamed too (its file name says nothing of the format).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datamate import loader, rules  # noqa: E402
from datamate.contracts import Mapping, QueryPlan, RawBusiness, RawTable  # noqa: E402
from datamate.eval.build_bank import PLANS, current_plans  # noqa: E402
from datamate.eval.check_plans import check  # noqa: E402
from datamate.eval.oracle import mapping_files  # noqa: E402
from datamate.eval.scorer import score_line  # noqa: E402
from datamate.mapping import build_canonical, build_card, run_checks, transfer  # noqa: E402
from datamate.mapping.build import PSEUDO, source_ids  # noqa: E402
from datamate.pipeline import BusinessContext, rule_ids  # noqa: E402
from datamate.predict import connect_llm  # noqa: E402


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def respell(name: str) -> str:
    """Another spelling of a column name: words -> CamelCase without accents; CamelCase or snake_case -> words."""
    if " " in name.strip():
        return "".join(w[:1].upper() + w[1:] for w in re.split(r"[\s._()/-]+", _fold(name)) if w)
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", _fold(name).replace("_", " "))
    out = " ".join(p.lower() for p in parts) if parts else name + " 2"
    return out[:1].upper() + out[1:]


def synonyms() -> dict[tuple[str, str], dict[str, str]]:
    """(canonical table, column) -> raw column name -> the shop naming it so, over every hand mapping."""
    out: dict[tuple[str, str], dict[str, str]] = {}
    for name, path in mapping_files("train").items():
        m = Mapping.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for tm in m.tables:
            # a shop keyed by name ("Tên hàng hóa" for key and name) gives no name for a key column holding codes
            names = {c.source for c in tm.columns if c.target.endswith("_name") and c.transform is None}
            for c in tm.columns:
                if c.transform == "lookup":  # the source is the key; what it means is the looked-up column
                    out.setdefault((tm.target, c.target), {}).setdefault(c.args["value"], name)
                    continue
                for s in ([c.source] if c.source else []) + list(c.sources or []):
                    if s and s not in PSEUDO and not (c.target.endswith("_key") and s in names):
                        out.setdefault((tm.target, c.target), {}).setdefault(s, name)
    return out


def meanings(m: Mapping, tables: list[str]) -> dict[str, dict[str, list[tuple[str, str]]]]:
    """raw table id -> column -> the canonical columns it feeds (read from it, or looked up in it)."""
    out: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for tm in m.tables:
        for t in source_ids(tm, tables):
            for c in tm.columns:
                if c.transform == "lookup":
                    continue
                for s in ([c.source] if c.source else []) + list(c.sources or []):
                    if s and s not in PSEUDO:
                        out.setdefault(t, {}).setdefault(s, []).append((tm.target, c.target))
        for c in tm.columns:
            if c.transform == "lookup":
                out.setdefault(c.args["table"], {}).setdefault(c.args["value"], []).append((tm.target, c.target))
    return out


def variant(raw: RawBusiness, m: Mapping, shop: str, rename_files: bool = False, strip_readme: bool = False
            ) -> tuple[RawBusiness, dict[str, dict[str, str]]]:
    """The shop with renamed columns (and database file), its README rewritten; and table id -> old -> new name.
    `rename_files`: files and database tables get neutral names too ("bang_a.xlsx"), files split _1, _2 keep one
    name: no file name pairs the shop with an example, only what the tables hold."""
    syn, feeds = synonyms(), meanings(m, [t.table_id for t in raw.tables])
    letters: dict[str, str] = {}
    for t in raw.tables:
        letters.setdefault(transfer.stem(t.table_id), "bang_" + _letters(len(letters)))
    split = Counter(transfer.stem(t.table_id) for t in raw.tables if "::" not in t.table_id or
                    Path(t.file).suffix.lower() not in transfer.DATABASES)
    seen: Counter = Counter()
    file_names: dict[str, str] = {}  # old file -> new file
    table_names: dict[str, str] = {}  # old database table -> new
    renames: dict[str, dict[str, str]] = {}
    tables = []
    for t in raw.tables:
        taken: set[str] = set()
        rename = {}
        for col in map(str, t.frame.columns):
            new = None
            # a column read as both key and name ("Ten hang": product_key and product_name) takes a name's name: a
            # shop keyed by name calls the column by the name ("Tên hàng"), not "Mã hàng"
            for key in sorted(feeds.get(t.table_id, {}).get(col, []),
                              key=lambda k: k[1].endswith("_key") or k[1] == "order_id"):
                others = sorted((n for n, owner in syn.get(key, {}).items() if owner != shop and n != col
                                 and n not in taken), key=lambda n: hashlib.md5(f"{shop}|{n}".encode()).hexdigest())
                if others:
                    new = others[0]
                    break
            if new is None:
                new = respell(col)
            while new in taken or new == col:
                new += " 1"
            taken.add(new)
            rename[col] = new
        renames[t.table_id] = rename
        file, sheet = t.file, t.sheet
        name = letters[transfer.stem(t.table_id)]
        if Path(file).suffix.lower() in transfer.DATABASES:
            file = "du_lieu" + Path(file).suffix
            if rename_files and sheet:
                table_names[sheet] = sheet = name
        elif rename_files:
            if t.file not in file_names:
                seen[name] += 1
                part = f"_{seen[name]}" if split[transfer.stem(t.table_id)] > 1 else ""
                file_names[t.file] = name + part + Path(t.file).suffix
            file = file_names[t.file]
        table_id = f"{file}::{sheet}" if "::" in t.table_id else file
        tables.append(RawTable(table_id=table_id, file=file, sheet=sheet, frame=t.frame.rename(columns=rename),
                               header_rows=t.header_rows, year_hint=t.year_hint, notes=list(t.notes)))
    readme = raw.readme
    for t in raw.tables:
        if Path(t.file).suffix.lower() in transfer.DATABASES:
            readme = readme.replace(t.file, "du_lieu" + Path(t.file).suffix)
    for old, new in sorted(file_names.items(), key=lambda kv: -len(kv[0])):
        readme = readme.replace(old, new)
    for old, new in sorted(table_names.items(), key=lambda kv: -len(kv[0])):
        readme = readme.replace(f"`{old}`", f"`{new}`").replace(f"`{old}.", f"`{new}.")
    for tid, rename in renames.items():
        for old, new in sorted(rename.items(), key=lambda kv: -len(kv[0])):
            readme = (readme.replace(f"**{old}**", f"**{new}**").replace(f".{old}`", f".{new}`")
                      .replace(f"`{old}`", f"`{new}`"))
    if strip_readme:  # keep the title, file list and conventions; drop every "## Cột trong ..." section
        readme = "".join(part for part in re.split(r"(?m)^(?=## )", readme) if not part.startswith("## Cột"))
    return RawBusiness(root=raw.root.parent / (raw.root.name + "_variant"), readme=readme, tables=tables,
                       warnings=list(raw.warnings)), renames


def _letters(i: int) -> str:
    out = ""
    while True:
        out = "abcdefghijklmnopqrstuvwxyz"[i % 26] + out
        i = i // 26 - 1
        if i < 0:
            return out


def context(raw: RawBusiness, m: Mapping) -> BusinessContext:
    db = build_canonical(raw, m)
    m.checks = list(m.checks) + run_checks(db, raw.readme)
    return BusinessContext(raw, loader.profile_business(raw), m, db, build_card(db))


def score(ctx: BusinessContext, qs: list[dict], plans: dict, refs: dict, calendar: Path, rule_status,
          wrong: list | None = None) -> Counter:
    out = Counter()
    for q in qs:
        p = plans.get(q["id"])
        if not ctx.mapping.ok or p is None:
            out["abstain"] += 1
            continue
        got = check(q, QueryPlan.model_validate(p), ctx, calendar, rule_status)
        outcome = score_line(got["line"], refs[q["id"]]).outcome
        out[outcome] += 1
        if outcome == "wrong" and wrong is not None:
            wrong.append((q["question"], got["function"], got["line"], refs[q["id"]].get("answer")))
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--business", nargs="*")
    ap.add_argument("--llm-url")
    ap.add_argument("--llm-cache", default="outputs/llm_cache_mapping.jsonl")
    ap.add_argument("--leave-out", action="store_true", help="bỏ mapping tay của chính cửa hàng ra khỏi các mẫu")
    ap.add_argument("--show-renames", action="store_true")
    ap.add_argument("--show-mapping", action="store_true", help="in mapping tự động của biến thể")
    ap.add_argument("--rename-files", action="store_true", help="đổi cả tên file, tên bảng sang tên trung tính")
    ap.add_argument("--strip-readme", action="store_true",
                    help="bỏ các mục mô tả cột của README, chỉ giữ tên file và quy ước (README sơ sài)")
    args = ap.parse_args(argv)
    llm = connect_llm(args.llm_url, cache=args.llm_cache) if args.llm_url else None
    if args.llm_url and llm is None:
        return 1
    split = ROOT / args.data_root / "train"
    questions = [json.loads(x) for x in (split / "questions.jsonl").read_text(encoding="utf-8").splitlines()
                 if x.strip()]
    refs = {a["id"]: a for a in map(json.loads, (split / "answers.jsonl").read_text(encoding="utf-8").splitlines())}
    plans = current_plans(questions, {e["id"]: e["plan"]
                                      for e in map(json.loads, PLANS.read_text(encoding="utf-8").splitlines())})
    rule_status = rules.check_rules((split / "rulebook.md").read_text(encoding="utf-8-sig"), rule_ids())
    hand = mapping_files("train")
    total = Counter()
    print(f"  {'cửa hàng':10}{'tay đ/s/t':>14}{'biến thể đ/s/t':>18}  mapping của biến thể")
    for b in args.business or sorted(hand):
        raw = loader.load_business(split / "data" / b)
        m_hand = Mapping.model_validate(json.loads(hand[b].read_text(encoding="utf-8")))
        qs = [q for q in questions if q["business_id"] == b]
        ref = score(context(raw, m_hand.model_copy(deep=True)), qs, plans, refs, split / "calendar.csv", rule_status)
        raw_v, renames = variant(raw, m_hand, b, args.rename_files, args.strip_readme)
        if args.show_renames:
            for t in raw_v.tables:
                print("   ", t.table_id, list(t.frame.columns)[:12])
        pool = transfer.examples(leave_out=b if args.leave_out else None)
        m, tried = transfer.map_by_transfer(raw_v, pool, llm=llm)
        m = m if m is not None else transfer.failed(tried)
        wrong: list = []
        got = score(context(raw_v, m), qs, plans, refs, split / "calendar.csv", rule_status, wrong)
        total += got
        how = m.notes[0] if m.ok and m.notes else ("; ".join(tried))[:160]
        print(f"  {b:10}{ref['correct']:>6}/{ref['wrong']}/{ref['abstain']:<5}"
              f"{got['correct']:>8}/{got['wrong']}/{got['abstain']:<6}  {how}", flush=True)
        for question, fn, line, ref in wrong:
            print(f"      SAI {question[:90]}\n          {fn} | dự đoán {json.dumps(line, ensure_ascii=False)[:110]}"
                  f" | đáp án {json.dumps(ref, ensure_ascii=False)[:80]}")
        if args.show_mapping and m.ok:
            for tm in m.tables:
                print("     ", tm.target, tm.sources[:1], [(c.target, c.source) for c in tm.columns][:16])
    n = sum(total.values())
    print(f"\nbiến thể: {n} câu · đúng {total['correct']} · sai {total['wrong']} · bỏ trống {total['abstain']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
