"""Mapping by transfer (T5, work package G2 part 3). The train shops come in a few export formats that repeat from shop
to shop (the same software, the same hand-kept ledger), so a new shop's tables usually carry the very column names a
hand-mapped train shop has. Its mapping is that shop's mapping with the raw tables renamed:

1. each table of the example mapping takes the new shop's raw tables holding every column it reads; when tables of
   two different layouts fit, the one closest to the example's own table wins, and a tie is no guess;
2. status words the example never met are read with the vocabulary of every hand mapping (folded spellings, a word two
   mappings read differently left out); a word still unknown stays as written, and the status check stops the shop;
3. what was a constant of the example shop is worked out again: the day of a stock snapshot (the last day of data,
   as the train READMEs state it), whether order times carry an hour.

The pipeline then runs the ten checks of build.py on the result; a shop no example passes for abstains. Nothing here
looks at a business id: examples are chosen by their columns only.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd

from datamate.contracts import TABLES, CheckResult, ColumnMap, Mapping, RawBusiness, TableMap
from datamate.llm import LLMClient
from datamate.loader.parse import parse_datetime

from .build import PSEUDO, build_canonical, run_checks, source_ids

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "assets" / "mappings" / "train"
SIGNATURES = ROOT / "assets" / "mappings" / "signatures.json"  # tools/mapping_signatures.py
REQUIRED = ("orders", "lines")
SAME_TABLE = 0.8  # raw tables of two layouts are stacked as one table when their columns are this alike (Jaccard)


@dataclass(frozen=True)
class Example:
    name: str  # file stem, for the notes
    mapping: Mapping
    tables: dict[str, tuple[str, ...]]  # raw table id -> columns, of the shop the mapping was written for
    samples: dict[str, dict[str, list[str]]] = field(default_factory=dict)  # raw table id -> column -> a few values
    notes: dict[str, dict[str, str]] = field(default_factory=dict)  # raw table id -> column -> README meaning


@lru_cache(maxsize=1)
def _all_examples() -> tuple[Example, ...]:
    if not SIGNATURES.exists():
        return ()
    signatures = json.loads(SIGNATURES.read_text(encoding="utf-8"))
    out = []
    for path in sorted(LIBRARY.glob("*.json")):
        if path.stem in signatures:
            mapping = Mapping.model_validate(json.loads(path.read_text(encoding="utf-8")))
            tables = signatures[path.stem]
            out.append(Example(path.stem, mapping, {k: tuple(v["columns"]) for k, v in tables.items()},
                               {k: v.get("samples", {}) for k, v in tables.items()},
                               {k: v.get("notes", {}) for k, v in tables.items()}))
    return tuple(out)


def examples(leave_out: str | None = None) -> list[Example]:
    """The hand mappings of train; `leave_out` drops one (the leave-one-out measure of eval/mapping.py)."""
    return [e for e in _all_examples() if e.name != leave_out]


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).strip().lower()).replace("đ", "d")
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _reads(c: ColumnMap) -> set[str]:
    return {s for s in [c.source, *c.sources] if s and s not in PSEUDO}


def used_columns(tm: TableMap) -> set[str]:
    """Raw columns the required canonical columns of a table mapping read from its own sources: an optional column
    (channel, debt…) the new shop does not have is left out, not a reason to drop the table."""
    spec = TABLES[tm.target]
    return set().union(*(_reads(c) for c in tm.columns if spec.column(c.target).required))


def _layout(example: Example, ids: list[str]) -> set[str]:
    return set().union(*(set(example.tables[i]) for i in ids)) if ids else set()


def match_tables(used: set[str], layout: set[str], raw: RawBusiness) -> list[str] | None:
    """The new shop's raw tables that play the part of a table with this layout: every one holding the columns read,
    stacked when their layouts are alike (sheets of months, files _1 / _2); None when none fits or two unlike layouts
    fit equally well."""
    fits = [t for t in raw.tables if used <= {str(c) for c in t.frame.columns}]
    if not fits:
        return None
    groups: dict[frozenset, list[str]] = {}
    for t in fits:
        groups.setdefault(frozenset(str(c) for c in t.frame.columns), []).append(t.table_id)
    ranked = sorted(groups.items(), key=lambda g: -_jaccard(set(g[0]), layout))
    best, score = ranked[0][0], _jaccard(set(ranked[0][0]), layout)
    if len(ranked) > 1 and _jaccard(set(ranked[1][0]), layout) == score and _jaccard(set(best), set(ranked[1][0])) < SAME_TABLE:
        return None
    return [i for cols, ids in groups.items() if _jaccard(set(cols), set(best)) >= SAME_TABLE for i in ids]


@lru_cache(maxsize=1)
def vocabulary() -> dict[tuple[str, str], dict[str, str]]:
    """(table, column) -> folded raw word -> canonical value, from every hand mapping's value_maps; a word two
    mappings read differently is left out."""
    seen: dict[tuple[str, str], dict[str, set[str]]] = {}
    for e in _all_examples():
        for tm in e.mapping.tables:
            for col, vm in tm.value_maps.items():
                for raw_word, value in vm.items():
                    seen.setdefault((tm.target, col), {}).setdefault(_fold(raw_word), set()).add(value)
    return {k: {w: vs.pop() for w, vs in words.items() if len(vs) == 1} for k, words in seen.items()}


# Order status words no hand mapping met, read by their key words (folded). A word with key words of two statuses is
# not read. "hoàn" alone is both "hoàn thành" (completed) and "hoàn hàng / hoàn trả" (returned): only the pairs count.
STATUS_WORDS = {
    "cancelled": r"\b(?:huy|khong giao duoc|bom hang|cancel|cancelled|canceled)\b",
    "returned": r"\b(?:tra hang|tra lai|tra ve|hoan hang|hoan tra|doi tra|return|returned|refund|refunded)\b",
    "delivering": r"\b(?:dang giao|dang van chuyen|dang gui|dang xu ly|shipping|delivering|in transit)\b",
    "completed": r"\b(?:hoan thanh|xong|thanh cong|da giao|da lay|completed|complete|done|delivered|ok)\b",
}


def read_word(table: str, column: str, word: str) -> str | None:
    """A raw value of a value-mapped column: the hand mappings' vocabulary, else (order status) its key words."""
    known = vocabulary().get((table, column), {}).get(_fold(word))
    if known is not None or (table, column) != ("orders", "status"):
        return known
    hits = [code for code, rx in STATUS_WORDS.items() if re.search(rx, _fold(word))]
    return hits[0] if len(hits) == 1 else None


def _raw_values(raw: RawBusiness, ids: list[str], column: str) -> set[str]:
    out = set()
    for t in raw.tables:
        if t.table_id in ids and column in t.frame.columns:
            out |= {str(v).strip() for v in t.frame[column].dropna().unique() if str(v).strip()}
    return out


def _transfer_table(tm: TableMap, example: Example, raw: RawBusiness) -> TableMap | None:
    ids = match_tables(used_columns(tm), _layout(example, source_ids(tm, list(example.tables))), raw)
    if ids is None:
        return None
    present = set.intersection(*({str(x) for x in t.frame.columns} for t in raw.tables if t.table_id in ids))
    columns = []
    for c in tm.columns:
        if not _reads(c) <= present:
            continue  # an optional column this shop does not record (required ones were matched above)
        if c.transform == "lookup":  # the looked-up table is matched by its own layout
            looked = match_tables({c.args["key"], c.args["value"]}, set(example.tables.get(c.args["table"], ())), raw)
            if looked is None or len(looked) != 1:
                if c.target in _REQUIRED_COLUMNS.get(tm.target, ()):
                    return None
                continue  # an optional attribute the new shop does not record that way
            c = c.model_copy(update={"args": {**c.args, "table": looked[0]}})
        columns.append(c)
    value_maps = {}
    for col, vm in tm.value_maps.items():
        source = next((c.source for c in columns if c.target == col), None)
        read = {w: read_word(tm.target, col, w) for w in _raw_values(raw, ids, source)} if source else {}
        value_maps[col] = {**vm, **{w: v for w, v in read.items() if v is not None}}
    return tm.model_copy(update={"sources": ids, "columns": columns, "value_maps": value_maps})


_REQUIRED_COLUMNS = {"orders": ("order_id", "order_time", "status"),
                     "lines": ("order_id", "product_key", "product_name", "qty", "line_amount")}


def transfer(example: Example, raw: RawBusiness) -> Mapping | None:
    """The example's mapping moved onto the new shop's tables; None when its orders or lines find no table."""
    tables = []
    for tm in example.mapping.tables:
        moved = _transfer_table(tm, example, raw)
        if moved is None and tm.target in REQUIRED:
            return None
        if moved is not None:
            tables.append(moved)
    return Mapping(record_grain=example.mapping.record_grain, tables=tables,
                   notes=[f"chuyển từ mapping mẫu {example.name} (khớp theo tên cột)"])


_SNAPSHOT_AT_END = re.compile(r"ton cuoi ngay cuoi co du lieu")  # folded; every train README with a stock file


def _settle_constants(mapping: Mapping, raw: RawBusiness) -> Mapping:
    """The constants the example wrote for its own shop, worked out for this one: the stock snapshot is dated the last
    day of the data, and order times have an hour only if some order is not at midnight. The snapshot date holds
    only where the shop's README says so (train: "**Tồn cuối** là tồn cuối ngày cuối có dữ liệu"); a README that does
    not (a stock at the start, at another day) leaves the stock unmapped and its questions blank (review 04/11)."""
    db = build_canonical(raw, mapping.model_copy(update={"tables": [t for t in mapping.tables if t.target == "orders"]}))
    orders = db.table("orders")
    if orders is None or orders["order_time"].isna().all():
        return mapping
    times = orders["order_time"].dropna()
    last_day, has_hour = times.max().date().isoformat(), bool((times.dt.normalize() != times).any())
    at_end = bool(_SNAPSHOT_AT_END.search(_fold(raw.readme)))
    tables = []
    for tm in mapping.tables:
        if tm.target == "inventory" and not at_end and any(c.target == "as_of" and c.const is not None
                                                            for c in tm.columns):
            continue
        cols = []
        for c in tm.columns:
            if tm.target == "inventory" and c.target == "as_of" and c.const is not None:
                c = c.model_copy(update={"const": last_day})
            elif tm.target == "orders" and c.target == "has_time" and c.const is not None:
                c = c.model_copy(update={"const": has_hour})
            cols.append(c)
        tables.append(tm.model_copy(update={"columns": cols}))
    return mapping.model_copy(update={"tables": tables})


def candidates(raw: RawBusiness, pool: list[Example] | None = None) -> list[Mapping]:
    """Every example that moves onto the shop, the closest first: most tables matched, then most alike columns."""
    found = []
    for e in examples() if pool is None else pool:
        m = transfer(e, raw)
        if m is not None:
            likeness = sum(_jaccard(_layout(e, source_ids(tm, list(e.tables))),
                                    {str(c) for t in raw.tables if t.table_id in tm.sources for c in t.frame.columns})
                           for tm in m.tables if tm.target in REQUIRED)
            found.append((len(m.tables), likeness, e.name, m))
    return [m for *_, m in sorted(found, key=lambda f: (-f[0], -f[1], f[2]))]


def failed(tried: list[str]) -> Mapping:
    """The mapping of a shop no example moved onto: no tables, and a failed check saying what was tried."""
    detail = "; ".join(tried) if tried else "không mapping mẫu nào có đủ cột của bảng đơn và dòng hàng"
    return Mapping(checks=[CheckResult(name="mapping", passed=False, detail=detail)])


def _passes(m: Mapping, raw: RawBusiness, tried: list[str]) -> Mapping | None:
    m = _settle_constants(m, raw)
    checks = run_checks(build_canonical(raw, m), raw.readme)
    bad = [c.name for c in checks if not c.passed]
    tried.append(f"{m.notes[0]}: {'qua' if not bad else 'hỏng ' + ', '.join(bad)}")
    return None if bad else m


def map_by_transfer(raw: RawBusiness, pool: list[Example] | None = None, llm: LLMClient | None = None,
                    by_meaning: int = 2) -> tuple[Mapping | None, list[str]]:
    """The first candidate whose canonical tables pass every check, and what each candidate tried did: examples
    matched by column names first; then, with an LLM, the `by_meaning` examples whose files the shop shares most,
    their columns matched by meaning."""
    tried = []
    for m in candidates(raw, pool):
        if (ok := _passes(m, raw, tried)) is not None:
            return ok, tried
    for e in sibling_files(raw, pool)[:by_meaning] if llm is not None else []:
        m = transfer_by_meaning(e, raw, llm)
        if m is None:
            tried.append(f"ghép theo nghĩa với mapping mẫu {e.name}: thiếu bảng đơn hoặc dòng hàng")
        elif (ok := _passes(m, raw, tried)) is not None:
            return ok, tried
    from .from_readme import map_from_readme  # N23: no example fits, the README's column meanings do
    m, why = map_from_readme(raw)
    if m is None:
        tried.append(f"dựng từ README: {why}")
    elif (ok := _passes(m, raw, tried)) is not None:
        return ok, tried
    return None, tried


# ---------------------------------------------------------------- by meaning: same files, columns renamed
# Shops of one hand-kept ledger format share their files (SoBanHang, SoNhapHang, TonKho…) and the meaning of their
# columns, but each names its columns its own way ("Mã phiếu" / "Ma don", "Tiền" / "Amount"). The tables are paired by
# file name; for each pair the LLM picks, for every column the example reads, the new shop's column of the same meaning
# (or none), seeing the new columns with a few values and the example's with theirs. The checks of meaning (amounts =
# quantity × price…) stop a wrong pick.

def stem(table_id: str) -> str:
    """What names a table across shops: its file name without digits or punctuation ("SoBanHang_1.xlsx" →
    "sobanhang"), with the table name for a database file (one file holds every table)."""
    file, _, sheet = table_id.partition("::")
    name = re.sub(r"[^a-z]+", "", _fold(Path(file).stem))
    return name + "/" + re.sub(r"[^a-z]+", "", _fold(sheet)) if Path(file).suffix.lower() in (".sqlite", ".db") else name


def _new_groups(raw: RawBusiness) -> dict[str, list[str]]:
    """The new shop's tables by stem; a stem whose tables have unlike layouts is left out (no guess)."""
    by_stem: dict[str, list] = {}
    for t in raw.tables:
        by_stem.setdefault(stem(t.table_id), []).append(t)
    out = {}
    for s, ts in by_stem.items():
        cols = [{str(c) for c in t.frame.columns} for t in ts]
        if all(_jaccard(cols[0], c) >= SAME_TABLE for c in cols):
            out[s] = [t.table_id for t in ts]
    return out


def _used_tables(e: Example) -> set[str]:
    """The example's raw tables its mapping reads: sources and looked-up tables."""
    out = {t for tm in e.mapping.tables for t in source_ids(tm, list(e.tables))}
    return out | {c.args["table"] for tm in e.mapping.tables for c in tm.columns if c.transform == "lookup"}


def _phrases(notes: dict[str, str]) -> set[str]:
    """The meanings a README gives its columns, first clause folded ("thành tiền sau giảm", "mã đơn")."""
    return {_fold(re.split(r"[:;(]", v)[0]) for v in notes.values() if v.strip()}


PAIR_MIN, PAIR_MARGIN = 0.5, 0.1  # share of the example table's README meanings found in the new table's


def pair_tables(e: Example, raw: RawBusiness) -> dict[str, list[str]]:
    """Example table id -> the new shop's tables playing its part: the same file name, else the table whose README
    meanings ("mã đơn", "trạng thái đơn", "thành tiền sau giảm"…) cover most of the example table's, by a margin. Files
    are named differently from shop to shop (ChiTietHoaDon, DonHang_ChiTiet…), what their columns mean is not."""
    groups = _new_groups(raw)
    readme = readme_columns(raw.readme)
    theirs = {s: _phrases(column_notes(readme, ids[0])) for s, ids in groups.items()}
    out = {}
    for t in _used_tables(e):
        if stem(t) in groups:
            out[t] = groups[stem(t)]
            continue
        mine = _phrases(e.notes.get(t, {}))
        scored = sorted(((len(mine & p) / len(mine), s) for s, p in theirs.items() if mine and p), reverse=True)
        if scored and scored[0][0] >= PAIR_MIN and (len(scored) == 1 or scored[0][0] - scored[1][0] >= PAIR_MARGIN):
            out[t] = groups[scored[0][1]]
    return out


def sibling_files(raw: RawBusiness, pool: list[Example] | None = None) -> list[Example]:
    """Examples whose orders and lines tables the shop has too (by file name or README meanings): those sharing most
    files by name first (04/11: an example paired by README meanings alone tried before the one with the same seven
    files, and the shop lost its mapping), then those pairing most of their tables."""
    ranked, mine = [], set(_new_groups(raw))
    for e in examples() if pool is None else pool:
        pairs = pair_tables(e, raw)
        core = {i for tm in e.mapping.tables if tm.target in REQUIRED for i in source_ids(tm, list(e.tables))}
        if core and core <= set(pairs):
            by_name = sum(stem(t) in mine for t in _used_tables(e))  # the same files first: the same format
            ranked.append((by_name, len(pairs) / len(_used_tables(e)), e.name, e))
    return [e for *_, e in sorted(ranked, key=lambda r: (-r[0], -r[1], r[2]))]


ASSIGN_GUIDE = """Bạn ghép cột của hai sổ bán hàng cùng loại. Cửa hàng mẫu và cửa hàng mới ghi cùng một bảng nhưng mỗi \
cửa hàng đặt tên cột theo cách riêng. Với mỗi cột của cửa hàng mẫu (kèm ý nghĩa và vài giá trị), chọn đúng một cột của \
cửa hàng mới có cùng ý nghĩa, dựa vào cả tên lẫn giá trị. Cửa hàng mới không có cột nào cùng ý nghĩa thì chọn "". Không \
chọn một cột chỉ vì tên giống khi giá trị không hợp (ví dụ cột ngày không phải cột tiền)."""


_SECTION = re.compile(r"^#+ .*?`([^`]+)`")
_NOTE = re.compile(r"^\s*[-*] \*\*(.+?)\*\*\s*:\s*(.+?)\s*$")


def readme_columns(readme: str) -> dict[str, dict[str, str]]:
    """What a README says of each column: file or table name (as written in "## Cột trong `don_hang.csv`") -> column
    -> meaning ("Khách trả" -> "đã thanh toán"). The strongest clue for matching columns: two columns with alike
    values ("Thành tiền", "Khách trả": equal for every order paid at once) differ there (04/11)."""
    out: dict[str, dict[str, str]] = {}
    current = None
    for line in readme.splitlines():
        if line.startswith("#"):
            m = _SECTION.match(line)
            current = m.group(1) if m else None
        elif current and (m := _NOTE.match(line)):
            out.setdefault(current, {})[m.group(1).strip()] = m.group(2)
    return out


def readme_section(readme_cols: dict[str, dict[str, str]], table_id: str) -> str | None:
    """The README section ("## Cột trong `<name>`") of a raw table: its sheet or table name, its file name, else its
    stem (files split _1, _2…); None when the README names no such table (review 04/11: the stem test was always
    true, every table the README did not name exactly took the notes of the README's first section)."""
    file, _, sheet = table_id.partition("::")
    for name in (sheet, file):
        if name and name in readme_cols:
            return name
    s = stem(table_id).split("/")[-1]
    return next((k for k in readme_cols if re.sub(r"[^a-z]+", "", _fold(Path(k).stem)) == s), None)


def column_notes(readme_cols: dict[str, dict[str, str]], table_id: str) -> dict[str, str]:
    """The README notes of a raw table (readme_section); none when the README does not describe it."""
    section = readme_section(readme_cols, table_id)
    return readme_cols[section] if section is not None else {}


def _meaning(e: Example, table_id: str, column: str) -> str:
    uses = []
    for tm in e.mapping.tables:
        if not any(t == table_id for t in source_ids(tm, list(e.tables))):
            continue
        for c in tm.columns:
            if column in _reads(c):
                spec = TABLES[tm.target].column(c.target)
                uses.append(f"{tm.target}.{c.target}" + (f" ({spec.doc})" if spec.doc else ""))
    for tm in e.mapping.tables:  # a column another table looks up
        for c in tm.columns:
            if c.transform == "lookup" and c.args.get("table") == table_id and column in (c.args["key"], c.args["value"]):
                uses.append(f"tra cứu cho {tm.target}.{c.target}")
    return "; ".join(dict.fromkeys(uses))


def _ask(e: Example, example_id: str, columns: list[str], raw: RawBusiness, ids: list[str], llm: LLMClient
         ) -> dict[str, str] | None:
    """example column -> new column (None: not recorded), for one pair of tables."""
    frames = [t.frame for t in raw.tables if t.table_id in ids]
    new_cols = list(dict.fromkeys(str(c) for f in frames for c in f.columns))
    notes = column_notes(readme_columns(raw.readme), ids[0])
    ex_notes = e.notes.get(example_id, {})
    lines = [f'- "{c}"' + (f" (README: {notes[c]})" if c in notes else "") + ": "
             + ", ".join(f'"{v}"' for v in _samples(frames, c)) for c in new_cols]
    asked = [f'c{i}: cột mẫu "{c}"' + (f" (README: {ex_notes[c]})" if c in ex_notes else "")
             + f" = {_meaning(e, example_id, c)}; giá trị: "
             + ", ".join(f'"{v}"' for v in e.samples.get(example_id, {}).get(c, [])) for i, c in enumerate(columns, 1)]
    user = "Cột của cửa hàng mới:\n" + "\n".join(lines) + "\n\nCột của cửa hàng mẫu cần ghép:\n" + "\n".join(asked)
    schema = {"type": "object", "additionalProperties": False, "required": [f"c{i}" for i in range(1, len(columns) + 1)],
              "properties": {f"c{i}": {"enum": new_cols + [""]} for i in range(1, len(columns) + 1)}}
    try:
        answer = llm.generate_json([{"role": "system", "content": ASSIGN_GUIDE}, {"role": "user", "content": user}],
                                   schema)
    except Exception:
        return None
    picked = {c: (answer.get(f"c{i}") or None) if answer.get(f"c{i}") in new_cols else None
              for i, c in enumerate(columns, 1)}
    return _one_meaning_each(e, example_id, picked)


def _one_meaning_each(e: Example, example_id: str, picked: dict[str, str | None]) -> dict[str, str | None]:
    """Two example columns of different meaning matched to one new column: the optional ones lose it (04/11: an
    example with a base-quantity column matched it to the shop's only quantity column, "1 thùng" counted as one
    can). Columns of one meaning (product key and name from one column) keep it."""
    by_new: dict[str, list[str]] = {}
    for c, new in picked.items():
        if new is not None:
            by_new.setdefault(new, []).append(c)
    out = dict(picked)
    for new, cols in by_new.items():
        if len(cols) < 2:
            continue
        required = [c for c in cols if _is_required(e, example_id, c)]
        for c in cols:
            if c not in required:
                out[c] = None
    return out


def _is_required(e: Example, table_id: str, column: str) -> bool:
    """The example column feeds a required canonical column (orders.order_id, lines.qty…)."""
    return any(column in _reads(c) and TABLES[tm.target].column(c.target).required
               for tm in e.mapping.tables if table_id in source_ids(tm, list(e.tables)) for c in tm.columns)


def _fill_date(e: Example, table_id: str, rename: dict[str, str | None], raw: RawBusiness, ids: list[str]
               ) -> dict[str, str | None]:
    """A required date column the LLM left unmatched ("Ngày tháng" / "Ngày", 04/11) takes the one column of the new
    table not matched yet whose values read as dates; two such columns: no guess."""
    missing = sorted({c.source for tm in e.mapping.tables if table_id in source_ids(tm, list(e.tables))
                      for c in tm.columns if c.parse in ("date", "datetime") and c.source and c.source not in PSEUDO
                      and TABLES[tm.target].column(c.target).required and rename.get(c.source) is None})
    if len(missing) != 1:
        return rename
    frames = [t.frame for t in raw.tables if t.table_id in ids]
    taken = {v for v in rename.values() if v}
    free = [c for c in dict.fromkeys(str(c) for f in frames for c in f.columns) if c not in taken
            and _dates(frames, c)]
    return {**rename, missing[0]: free[0]} if len(free) == 1 else rename


def _dates(frames: list[pd.DataFrame], column: str, share: float = 0.9) -> bool:
    """The column's values read as days of this century ("1/3" with a sheet year too; a quantity "5" read as an Excel
    serial would be 1900)."""
    values = [v for f in frames if column in f.columns for v in f[column].dropna().astype(str).head(50) if v.strip()]
    days = [parse_datetime(v, 2000) for v in values]
    return bool(values) and sum(d is not None and d.year >= 2000 for d in days) >= share * len(values)


def _samples(frames: list[pd.DataFrame], column: str, n: int = 3) -> list[str]:
    values: list[str] = []
    for f in frames:
        if column in f.columns:
            values += [str(v).strip() for v in f[column].dropna().unique()[:50] if str(v).strip()]
    return list(dict.fromkeys(values))[:n]


def _has_order_ids(raw: RawBusiness, ids: list[str]) -> bool:
    """Whether a sales table groups its rows into orders: some column ties neighbouring rows together (an order id,
    the order's time). Measured 04/11: the id column of every ledger with order ids does, no column of the three
    ledgers without does. A ledger where a customer column happens to group rows is taken for one with ids: the
    example without ids is then not used, and the shop abstains rather than being read row by row wrongly."""
    frame = pd.concat([t.frame for t in raw.tables if t.table_id in ids], ignore_index=True)
    return any(_groups_rows(frame[c]) for c in frame.columns)


def _groups_rows(values: pd.Series, continued: float = 0.2, distinct: float = 0.05) -> bool:
    """The column ties neighbouring rows into orders: many rows continue the row above (same value, or blank under a
    value: the order id written on its first line only), and there are many such groups. Product names repeat too,
    but rarely on the next row."""
    text = values.map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip())
    if len(text) < 2:
        return False
    same = (text == text.shift()) & (text != "")
    follow = (text == "") & (text.replace("", None).ffill().notna())
    return float((same | follow).mean()) >= continued and text[text != ""].nunique() >= distinct * len(text)


def transfer_by_meaning(e: Example, raw: RawBusiness, llm: LLMClient) -> Mapping | None:
    """The example's mapping moved onto a shop sharing its files, columns matched by meaning; None when the orders or
    lines lose a required column, or when the example's ledger has no order ids and the shop's has (04/11: a shop
    with order ids read row by row like the example passed every check with 68 wrong answers of 119)."""
    pairs = pair_tables(e, raw)
    if e.mapping.record_grain == "line_is_record":
        orders = next(tm for tm in e.mapping.tables if tm.target == "orders")
        sales = source_ids(orders, list(e.tables))
        if not sales or sales[0] not in pairs or _has_order_ids(raw, pairs[sales[0]]):
            return None
    renames: dict[str, dict[str, str | None]] = {}  # example table id -> its column -> new column
    new_ids: dict[str, list[str]] = {}
    needed: dict[str, set[str]] = {}
    for tm in e.mapping.tables:
        for t in source_ids(tm, list(e.tables)):
            needed.setdefault(t, set()).update(*(_reads(c) for c in tm.columns))
        for c in tm.columns:
            if c.transform == "lookup":
                needed.setdefault(c.args["table"], set()).update({c.args["key"], c.args["value"]})
    asked: dict[str, dict[str, str | None]] = {}  # one question per new table group
    for t, cols in needed.items():
        if t not in pairs:
            continue
        new_ids[t] = pairs[t]
        key = ",".join(pairs[t]) + "|" + "|".join(sorted(cols))
        if key not in asked:
            asked[key] = _ask(e, t, sorted(cols), raw, pairs[t], llm) or {}
        renames[t] = _fill_date(e, t, asked[key], raw, pairs[t])
    if e.mapping.record_grain == "order" and not _order_ids_group_lines(e, renames, new_ids, raw):
        return None
    tables = []
    for tm in e.mapping.tables:
        moved = _rename(tm, e, renames, new_ids, raw)
        if moved is None and tm.target in REQUIRED:
            return None
        if moved is not None:
            tables.append(moved)
    return Mapping(record_grain=e.mapping.record_grain, tables=tables,
                   notes=[f"ghép theo nghĩa với mapping mẫu {e.name} (LLM chọn cột)"])


def _order_ids_group_lines(e: Example, renames: dict, new_ids: dict, raw: RawBusiness) -> bool:
    """The column matched to the lines' order id ties neighbouring lines into orders, as an order id does (04/11: an
    example with order ids moved onto a ledger without any, a date column taken for the id, 33 wrong of 40)."""
    lines = next((tm for tm in e.mapping.tables if tm.target == "lines"), None)
    oid = next((c.source for c in lines.columns if c.target == "order_id"), None) if lines else None
    t = next((t for t in source_ids(lines, list(e.tables)) if t in renames), None) if lines else None
    new = renames.get(t, {}).get(oid) if t else None
    frames = [tb.frame[new] for tb in raw.tables if t and tb.table_id in new_ids[t] and new in tb.frame.columns]
    return bool(frames) and _groups_rows(pd.concat(frames, ignore_index=True))


def _rename(tm: TableMap, e: Example, renames: dict, new_ids: dict, raw: RawBusiness) -> TableMap | None:
    ex_ids = [t for t in source_ids(tm, list(e.tables)) if t in new_ids]
    if not ex_ids:
        return None
    ids = list(dict.fromkeys(i for t in ex_ids for i in new_ids[t]))
    rename = {k: v for t in ex_ids for k, v in renames.get(t, {}).items()}
    spec, columns = TABLES[tm.target], []
    for c in tm.columns:
        reads = _reads(c)
        if any(rename.get(r) is None for r in reads):
            if spec.column(c.target).required:
                return None
            continue
        update = {}
        if c.source in rename:
            update["source"] = rename[c.source]
        if c.sources:
            update["sources"] = [rename.get(s, s) for s in c.sources]
        if c.transform == "lookup":
            looked, keys = new_ids.get(c.args["table"]), renames.get(c.args["table"], {})
            key, value = keys.get(c.args["key"]), keys.get(c.args["value"])
            if not looked or len(looked) != 1 or key is None or value is None:
                if spec.column(c.target).required:
                    return None
                continue
            update["args"] = {**c.args, "table": looked[0], "key": key, "value": value}
        columns.append(c.model_copy(update=update))
    value_maps = {}
    for col, vm in tm.value_maps.items():
        source = next((c.source for c in columns if c.target == col), None)
        read = {w: read_word(tm.target, col, w) for w in _raw_values(raw, ids, source)} if source else {}
        value_maps[col] = {w: v for w, v in read.items() if v is not None}
    return tm.model_copy(update={"sources": ids, "columns": columns, "value_maps": value_maps})
