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
DATABASES = (".sqlite", ".db", ".sqlite3")  # one file, many tables (loader.READERS)


class LLMUnavailable(Exception):
    """The model did not answer a mapping question twice (timeout, server busy): not "no column matches" (N164b)."""


def _generate(llm: LLMClient, messages: list[dict], schema: dict, what: str) -> dict:
    """One mapping question, asked again once when the call fails (N164b, 10/11: a busy shared server timing out
    blanked whole shops, reported as "thiếu bảng đơn hoặc dòng hàng"); a second failure raises LLMUnavailable."""
    for attempt in (1, 2):
        try:
            return llm.generate_json(messages, schema)
        except Exception as ex:
            if attempt == 2:
                raise LLMUnavailable(f"{what}: {type(ex).__name__}") from ex
    raise AssertionError("unreachable")


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


@lru_cache(maxsize=500_000)  # N175: see build._fold
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
    # "Khách trả" alone in a status cell (a public shop, 06/11); "khách trả tiền" is no status word
    # "kiểm tra lại" (check again) is no return (a public repair ledger's note, 06/11)
    "returned": r"\b(?:tra hang|(?<!kiem )tra lai|tra ve|mang tra|hoan hang|hoan tra|doi tra|return|returned|refund"
                r"|refunded)\b"
                r"|^khach tra$",
    # "chưa giao": not delivered yet, of the four §8 statuses the one in delivery (public notes, 06/11)
    # "đang ship" (a public ledger, 06/11: 3 orders without status, every delivery count of their days abstained)
    "delivering": r"\b(?:dang giao|dang van chuyen|dang gui|dang xu ly|cho giao|chua giao|shipping|delivering"
                  r"|in transit|dang ship|cho ship)\b",
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


def refresh_status_words(m: Mapping, raw: RawBusiness) -> Mapping:
    """The order statuses a logged mapping's value map lacks, read with today's words (a replay sees what a new run
    would: "đang ship" became a delivering order, 06/11)."""
    out = []
    for tm in m.tables:
        source = next((c.source for c in tm.columns if c.target == "status"), None)
        if tm.target == "orders" and "status" in tm.value_maps and source:
            vm = tm.value_maps["status"]
            ids = source_ids(tm, [t.table_id for t in raw.tables])
            new = {w: v for w in _raw_values(raw, ids, source) if w not in vm
                   and (v := read_word("orders", "status", w)) is not None}
            if new:
                tm = tm.model_copy(update={"value_maps": {**tm.value_maps, "status": {**vm, **new}}})
        out.append(tm)
    return m.model_copy(update={"tables": out})


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
    from .from_readme import enrich  # N29: the attributes the README names that the example's shop did not record
    m = expand_abbreviations(status_in_note(_settle_constants(enrich(m, raw), raw), raw), raw)
    db = build_canonical(raw, m)
    if broken := unfilled_extras(db):  # N27: a side table matched wrongly is left out, not the shop
        m = m.model_copy(update={"tables": [tm for tm in m.tables if tm.target not in broken], "notes": list(
            m.notes) + ["bỏ bảng phụ có cột bắt buộc trống: " + ", ".join(broken)]})
        db = build_canonical(raw, m)
    checks = run_checks(db, raw.readme)
    bad = [c.name for c in checks if not c.passed]
    if bad == [AMOUNT_CHECK] and (fixed := requantify(m, raw)) is not None:
        m, bad = fixed, []
    tried.append(f"{m.notes[0]}: {'qua' if not bad else 'hỏng ' + ', '.join(bad)}")
    return None if bad else m


AMOUNT_CHECK = "thành tiền khớp số lượng × đơn giá"


def requantify(m: Mapping, raw: RawBusiness) -> Mapping | None:
    """N27: the amount check alone failed: the one other number column of the lines that, taken for the quantity,
    makes every check pass (05/11: an unfamiliar pharmacy's "SL cơ bản", the quantity in base units, was matched for
    the line's quantity, its "Slg" left out; 1 thùng at the price of a thùng counted as 24). Two such columns: no
    guess."""
    lines = next((tm for tm in m.tables if tm.target == "lines"), None)
    qty = next((c for c in lines.columns if c.target == "qty"), None) if lines is not None else None
    if qty is None or qty.transform is not None or not qty.source:
        return None
    used = {x for c in lines.columns for x in [c.source, *c.sources] if x}
    ids = set(source_ids(lines, [t.table_id for t in raw.tables]))
    frames = [t.frame for t in raw.tables if t.table_id in ids]
    passing = []
    for col in dict.fromkeys(str(c) for f in frames for c in f.columns):
        if col in used or not _numbers(frames, col):
            continue
        moved = lines.model_copy(update={"columns": [c.model_copy(update={"source": col}) if c is qty else c
                                                     for c in lines.columns]})
        cand = m.model_copy(update={"tables": [moved if tm is lines else tm for tm in m.tables], "notes": list(
            m.notes) + [f"số lượng của dòng đọc lại theo thành tiền = số lượng × đơn giá: {col}"]})
        if all(c.passed for c in run_checks(build_canonical(raw, cand), raw.readme)):
            passing.append(cand)
    return passing[0] if len(passing) == 1 else None


def _numbers(frames: list[pd.DataFrame], column: str, share: float = 0.9) -> bool:
    from datamate.loader.parse import parse_number
    values = [v for f in frames if column in f.columns for v in f[column].dropna().astype(str).head(50) if v.strip()]
    return bool(values) and sum(parse_number(v) is not None for v in values) >= share * len(values)


# N40, public rulebook §8 "sổ không có cột trạng thái: trạng thái đơn ghi ở cột Ghi chú": a shop moved from an example
# whose status column it has not (public phone ledgers, 06/11)
NOTE_NAME = re.compile(r"^ghi chu\b")


def note_column(raw: RawBusiness, ids: list[str]) -> str | None:
    """The one column of these tables named "Ghi chú…" that is a note: mostly blank (a status column has a word on
    every row; a ledger's note names a status on the few orders it concerns), or of other words than statuses. None:
    none, or two."""
    frames = [t.frame for t in raw.tables if t.table_id in ids]
    names = [c for c in dict.fromkeys(str(c) for f in frames for c in f.columns) if NOTE_NAME.match(_fold(c))]
    if len(names) != 1:
        return None
    cells = pd.concat([f[names[0]] for f in frames if names[0] in f.columns], ignore_index=True)
    blank = float(cells.map(lambda v: v is None or (isinstance(v, float) and pd.isna(v)) or not str(v).strip()).mean())
    return names[0] if blank >= 0.5 or not _status_words(frames, names[0]) else None


def _status_words(frames: list[pd.DataFrame], column: str) -> bool:
    values = {str(v).strip() for f in frames if column in f.columns for v in f[column].dropna().unique()[:100]} - {""}
    return bool(values) and len(values) <= 20 and sum(read_word("orders", "status", v) is not None
                                                       for v in values) >= STATUS_SHARE * len(values)


def status_in_note(m: Mapping, raw: RawBusiness) -> Mapping:
    """An orders status read from the shop's note column (not status words) is read by status_from_note, its value
    map dropped."""
    out, changed = [], False
    for tm in m.tables:
        st = next((c for c in tm.columns if c.target == "status"), None) if tm.target == "orders" else None
        if st is not None and st.transform in (None, "order_status_from_lines") and st.source is not None:
            ids = source_ids(tm, [t.table_id for t in raw.tables])
            if note_column(raw, ids) == st.source:
                cols = [c.model_copy(update={"transform": "status_from_note"}) if c is st else c for c in tm.columns]
                tm = tm.model_copy(update={"columns": cols, "value_maps": {k: v for k, v in tm.value_maps.items()
                                                                           if k != "status"}})
                changed = True
        out.append(tm)
    return m.model_copy(update={"tables": out}) if changed else m


ABBREV_COVER = 0.8  # share of the lines' distinct product values written by abbreviation or by name
ABBREV_SOME = 0.2  # share of them abbreviated
ABBREV_NAMED = 0.1  # share of them written by the full name (a public phone ledger: 56 of 115)


def expand_abbreviations(m: Mapping, raw: RawBusiness) -> Mapping:
    """N43, public phone ledgers (06/11): "hàng bán, có thể ghi tắt (tra ở sheet Ghi tắt)". When the lines read their
    product from a plain column and another table of the shop has a column holding most of that column's values (as
    keys, each once) and another column of names (with a space), the product key and name are looked up there
    (unknown abbreviations kept as written). Two such tables or columns: no guess."""
    lines = next((tm for tm in m.tables if tm.target == "lines"), None)
    key = next((c for c in lines.columns if c.target == "product_key"), None) if lines is not None else None
    if key is not None and key.transform == "lookup" and key.args.get("fold") and {"table", "key", "value"} <= set(key.args):
        # already expanded (a logged mapping replayed): the kind of goods of the same sheet, if any
        a = key.args
        return m.model_copy(update={"tables": _kind_of_goods(list(m.tables), raw, a["table"], a["key"], a["value"])})
    if key is None or key.transform is not None or not key.source:
        return m
    ids = set(source_ids(lines, [t.table_id for t in raw.tables]))
    # compared however written (§8): a public ledger writes "IP16 128 hong" and "IP16 128 hồng", "Cáp  C-L"
    values = {_fold(str(v)) for t in raw.tables if t.table_id in ids and key.source in t.frame.columns
              for v in t.frame[key.source].dropna().unique()} - {""}
    if not values:
        return m
    found = []
    for t in raw.tables:
        if t.table_id in ids:
            continue
        f = t.frame
        for k in map(str, f.columns):
            col = f[k].dropna().astype(str).map(_fold)
            if not col.is_unique or len(values & set(col)) < ABBREV_SOME * len(values):
                continue
            # the ledger writes some products by abbreviation, the others by their full name (a public ledger: 59 of
            # 115 values abbreviated): together they cover the lines
            names = [n for n in map(str, f.columns) if n != k and f[n].dropna().astype(str).str.contains(" ").mean() >= 0.5
                     and f[n].dropna().astype(str).nunique() >= 0.9 * len(col)
                     and len(values & (set(col) | set(f[n].dropna().astype(str).map(_fold))))
                     >= ABBREV_COVER * len(values)
                     and f[n].dropna().astype(str).str.len().mean() > col.str.len().mean()  # names are longer
                     # some lines write the full name itself: a ledger keyed by codes never does (06/11: train shops
                     # keyed "SP001" with a catalogue of codes and names lost their keys to the names, 67 answers)
                     and len(values & set(f[n].dropna().astype(str).map(_fold))) >= ABBREV_NAMED * len(values)]
            if len(names) == 1:
                found.append((t.table_id, k, names[0]))
    if len(found) != 1:
        return m
    table, k, name = found[0]
    if k == key.source and table in ids:
        return m
    args = {"table": table, "key": k, "value": name, "keep_missing": True, "fold": True}
    # the key as written, and the name whatever lookup the moved mapping made (a public ledger's name was looked up by
    # the wrong column of the same sheet)
    cols = [c.model_copy(update={"transform": "lookup", "args": args, "source": key.source})
            if (c.target == "product_key" and c.transform is None) or (c.target == "product_name"
                                                                       and c.source == key.source) else c
            for c in lines.columns]
    if not any(c.target == "product_name" for c in cols):
        cols.append(ColumnMap(target="product_name", source=key.source, transform="lookup", args=args))
    out = [lines.model_copy(update={"columns": cols}) if tm is lines else tm for tm in m.tables]
    out = _kind_of_goods(out, raw, table, k, name)
    return m.model_copy(update={"tables": out, "notes": list(m.notes) + [f"tên hàng ghi tắt tra ở {table}"]})


def _kind_of_goods(tables: list[TableMap], raw: RawBusiness, table: str, key: str, name: str) -> list[TableMap]:
    """The kind of each product the abbreviation sheet gives beside its full name (public phone ledgers, 06/11: "sheet
    Ghi tắt cho tên đầy đủ và loại hàng (máy mới, máy cũ, phụ kiện)"): the catalogue keyed by that full name (the
    product key the lines now hold) gets it as its category; a shop without a catalogue gets one from the sheet."""
    frame = next((t.frame for t in raw.tables if t.table_id == table), None)
    if frame is None:
        return tables
    kinds = [c for c in map(str, frame.columns) if c not in (key, name) and _fold(c).startswith("loai")
             and 2 <= frame[c].dropna().astype(str).nunique() <= 10]
    if len(kinds) != 1:
        return tables
    kind = ColumnMap(target="category", source=kinds[0])
    products = [tm for tm in tables if tm.target == "products"]
    if not products:
        return tables + [TableMap(target="products", sources=[table], columns=[
            ColumnMap(target="product_key", source=name), ColumnMap(target="product_name", source=name), kind])]
    p = products[0]
    keyed = next((c.source for c in p.columns if c.target == "product_key"), None)
    if len(products) != 1 or p.sources != [table] or keyed != name or any(c.target == "category" for c in p.columns):
        return tables
    return [tm.model_copy(update={"columns": list(tm.columns) + [kind]}) if tm is p else tm for tm in tables]


def unfilled_extras(db) -> list[str]:
    """Canonical tables besides the orders and lines with a required column left empty in some row (N27, 05/11: an
    unfamiliar shop's lines and orders matched right, its product list taken for a price history with no dates: the
    whole shop failed "cột bắt buộc đủ giá trị"). Such a table is wrong or unreadable; without it, the questions it
    serves abstain."""
    out = []
    for name, df in db.tables.items():
        spec = TABLES.get(name)
        if name in REQUIRED or spec is None or not len(df):
            continue
        if any(c.required and c.name in df.columns and df[c.name].isna().any() for c in spec.columns):
            out.append(name)
    return sorted(out)


THIN_NOTE = "README không có mục Quy ước: chỉ giữ bảng đơn, dòng hàng, danh mục (N176)"
THIN_ORDER_COLUMNS = frozenset({"order_id", "order_time", "has_time", "status", "customer_key", "customer_name",
                                "goods_amount", "employee", "channel", "payment_method"})
THIN_LINE_DROP = frozenset({"unit_cost"})


def is_llm_route(note: str) -> bool:
    """True for a mapping the LLM paired or picked the columns of ('ghép theo nghĩa…', 'ghép bảng theo vai trò…')."""
    return note.startswith(("ghép theo nghĩa", "ghép bảng theo vai trò"))


def thin_core(mapping: Mapping) -> Mapping:
    """N176. A README with no '## Quy ước' section gives nothing to check an LLM's picks against: the sales file mapped
    four times as employees, lots, payments and returns, quantity and base quantity swapped (a one-line README probe,
    5 answers to another value), the debt columns picked by the model alone (20). Only what the data itself confirms is
    kept: orders (their identity, time, status, customer, amount, seller, channel, payment), lines and products; the
    side tables and the order columns only a README or a pick defines go, so those questions abstain."""
    tables = []
    for tm in mapping.tables:
        if tm.target not in ("orders", "lines", "products"):
            continue
        if tm.target == "orders":
            tm = tm.model_copy(update={"columns": [c for c in tm.columns if c.target in THIN_ORDER_COLUMNS]})
        elif tm.target == "lines":
            tm = tm.model_copy(update={"columns": [c for c in tm.columns if c.target not in THIN_LINE_DROP]})
        tables.append(tm)
    return mapping.model_copy(update={"tables": tables, "notes": list(mapping.notes) + [THIN_NOTE]})


def map_by_transfer(raw: RawBusiness, pool: list[Example] | None = None, llm: LLMClient | None = None,
                    by_meaning: int = 2) -> tuple[Mapping | None, list[str]]:
    """`_map_by_transfer`, then (N176) the core only when the README has no '## Quy ước' section and an LLM chose the
    mapping; kept as it was when the reduced mapping fails a check."""
    mapping, tried = _map_by_transfer(raw, pool, llm, by_meaning)
    if mapping is None or not mapping.notes or not is_llm_route(mapping.notes[0]):
        return mapping, tried
    from .build import readme_conventions
    if readme_conventions(raw.readme or "") is not None:
        return mapping, tried
    done = _passes(thin_core(mapping), raw, [])
    return (mapping if done is None else done), tried


def _map_by_transfer(raw: RawBusiness, pool: list[Example] | None = None, llm: LLMClient | None = None,
                     by_meaning: int = 2) -> tuple[Mapping | None, list[str]]:
    """The first candidate whose canonical tables pass every check, and what each candidate tried did: examples
    matched by column names first; then, with an LLM, the `by_meaning` examples whose files the shop shares most,
    their columns matched by meaning."""
    tried = []
    for m in candidates(raw, pool):
        if (ok := _passes(m, raw, tried)) is not None:
            return ok, tried
    for e in sibling_files(raw, pool)[:by_meaning] if llm is not None else []:
        try:
            m = transfer_by_meaning(e, raw, llm)
        except LLMUnavailable as ex:
            tried.append(f"ghép theo nghĩa với mapping mẫu {e.name}: LLM không trả lời ({ex})")
            continue
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
    # N27: no file name, README meaning or column name pairs the tables: the LLM pairs them by role, then the columns
    ranked, failed = by_role(raw, pool, llm) if llm is not None else ([], [])
    if failed:
        tried.append(f"ghép bảng theo vai trò: LLM không trả lời cho {len(failed)} mapping mẫu")
    for e, pairs in ranked[:by_meaning]:
        try:
            m = transfer_by_meaning(e, raw, llm, pairs)
        except LLMUnavailable as ex:
            tried.append(f"ghép bảng theo vai trò với mapping mẫu {e.name}: LLM không trả lời ({ex})")
            continue
        if m is None:
            tried.append(f"ghép bảng theo vai trò với mapping mẫu {e.name}: thiếu bảng đơn hoặc dòng hàng")
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
    "sobanhang"); for a database file, its table name alone (N27, 05/11: one file holds every table and its name says
    nothing of the format, "pos.sqlite" / "du_lieu.db"; with the file name in, a shop of the same POS whose file was
    named otherwise paired with no example, and a database's "don_hang" never met the "don_hang.csv" of three shops)."""
    file, _, sheet = table_id.partition("::")
    if Path(file).suffix.lower() in DATABASES:
        return re.sub(r"[^a-z]+", "", _fold(sheet))
    return re.sub(r"[^a-z]+", "", _fold(Path(file).stem))


def layout_groups(raw: RawBusiness) -> list[list[str]]:
    """The shop's tables as the LLM sees them when pairing by role: by stem, and within a stem by layout (columns
    alike at SAME_TABLE). A workbook of several lists offers each list; the sheets of one list stay together (public
    shop, 06/11: the sales sheets of a workbook of five lists were left out by `_new_groups`, never offered)."""
    out: list[list[str]] = []
    by_stem: dict[str, list] = {}
    for t in raw.tables:
        by_stem.setdefault(stem(t.table_id), []).append(t)
    for ts in by_stem.values():
        clusters: list[tuple[set, list[str]]] = []
        for t in ts:
            cols = {str(c) for c in t.frame.columns}
            home = next((c for c in clusters if _jaccard(c[0], cols) >= SAME_TABLE), None)
            if home is None:
                clusters.append((cols, [t.table_id]))
            else:
                home[1].append(t.table_id)
        out += [ids for _, ids in clusters]
    return out


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
    s = stem(table_id)
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


def _ask(e: Example, example_id: str, columns: list[str], raw: RawBusiness, ids: list[str], llm: LLMClient,
         taken: frozenset[str] = frozenset()) -> dict[str, str | None]:
    """example column -> new column (None: not recorded), for one pair of tables; `taken`: new columns already
    matched, not offered."""
    frames = [t.frame for t in raw.tables if t.table_id in ids]
    new_cols = [c for c in dict.fromkeys(str(c) for f in frames for c in f.columns) if c not in taken]
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
    answer = _generate(llm, [{"role": "system", "content": ASSIGN_GUIDE}, {"role": "user", "content": user}],
                       schema, example_id)
    picked = {c: (answer.get(f"c{i}") or None) if answer.get(f"c{i}") in new_cols else None
              for i, c in enumerate(columns, 1)}
    return _one_meaning_each(e, example_id, picked)


def _ask_required_again(e: Example, example_id: str, columns: list[str], raw: RawBusiness, ids: list[str],
                        llm: LLMClient) -> dict[str, str | None]:
    """_ask, then once more for the required columns it left unmatched, among the new columns not taken (N27, 05/11:
    a shop whose lines had "Số lượng sản phẩm" lost its quantity in a question of 8 columns, and the whole mapping).
    The checks of meaning (amount = quantity × price…) stop a wrong second pick. N164 (10/11): the same shop with
    its columns reversed had its customers' names matched to a 3-value column; a pick that cannot hold its meaning
    (`_implausible`) is refused and asked once more. N164c: a refused constant pick comes back when the second
    answer gives nothing better (a shop whose customers are all "Cá nhân" has one group, not a wrong one)."""
    got = _ask(e, example_id, columns, raw, ids, llm)
    missing = [c for c in columns if got.get(c) is None and _is_required(e, example_id, c)]
    if missing:
        again = _ask(e, example_id, missing, raw, ids, llm, frozenset(v for v in got.values() if v))
        got.update({c: v for c, v in again.items() if v is not None})
    bad = _implausible(e, example_id, got, raw, ids)
    if bad:
        # a column refused as a name stays offered (it may be the group); one holding a single value means nothing
        frames = [t.frame for t in raw.tables if t.table_id in ids]
        constant = {got[c] for c in bad if _distinct(frames, got[c])[0] <= 1}
        first = {c: got[c] for c in bad}
        for c in bad:
            got[c] = None
        taken = frozenset(v for v in got.values() if v) | constant
        again = _ask(e, example_id, bad, raw, ids, llm, taken)
        again = {c: v for c, v in again.items() if v is not None}
        ok = set(again) - set(_implausible(e, example_id, {**got, **again}, raw, ids))
        got.update({c: again[c] for c in ok})
        for c in bad:
            if first[c] in constant and c not in ok:
                got[c] = first[c]
    return got


def _targets(e: Example, table_id: str, column: str) -> set[str]:
    """The canonical columns the example column is read as directly in a table of the example's raw table."""
    return {c.target for tm in e.mapping.tables if table_id in source_ids(tm, list(e.tables)) for c in tm.columns
            if column in _reads(c) and c.transform is None}


def _distinct(frames: list[pd.DataFrame], column: str) -> tuple[int, int]:
    """(distinct non-blank values, non-blank rows) of the column over the frames."""
    values = pd.concat([f[column] for f in frames if column in f.columns], ignore_index=True) if any(
        column in f.columns for f in frames) else pd.Series([], dtype=object)
    text = values.dropna().astype(str).str.strip()
    text = text[text != ""]
    return int(text.nunique()), int(len(text))


def _implausible(e: Example, example_id: str, got: dict[str, str | None], raw: RawBusiness, ids: list[str]
                 ) -> list[str]:
    """Example columns whose new column cannot hold their meaning (N164, 10/11: the same shop with its columns in
    reverse order had its customers' names matched to "LoaiKhachHang" — 3 values for 300 customers, rankings named
    "sỉ", "lẻ" — and its product group to a column holding one value). A name must tell most of its keys apart; a
    group must hold more than one value."""
    frames = [t.frame for t in raw.tables if t.table_id in ids]
    keys = {t: new for c, new in got.items() if new for t in _targets(e, example_id, c) if t.endswith("_key")}
    bad = []
    for c, new in got.items():
        if not new:
            continue
        for t in _targets(e, example_id, c):
            if t.endswith("_name") and keys.get(t[:-5] + "_key") not in (None, new):
                n_key, _ = _distinct(frames, keys[t[:-5] + "_key"])
                n_name, _ = _distinct(frames, new)
                if n_key >= 20 and n_name < 0.5 * n_key:
                    bad.append(c)
                    break
            if t.endswith("_group"):
                n, rows = _distinct(frames, new)
                if n <= 1 and rows >= 20:
                    bad.append(c)
                    break
    return bad


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
        # N27, 05/11: the order id's column means nothing else (an unfamiliar shop's order ids were taken for the
        # product key too, both required: rankings named codes of orders)
        ids = [c for c in cols if _feeds(e, example_id, c, "order_id")]
        if ids:
            for c in cols:
                if c not in ids:
                    out[c] = None
            continue
        required = [c for c in cols if _is_required(e, example_id, c)]
        for c in cols:
            if c not in required:
                out[c] = None
    return out


def _feeds(e: Example, table_id: str, column: str, target: str) -> bool:
    """The example column is read as `target` in a table of the example's raw table."""
    return any(column in _reads(c) and c.target == target and c.transform is None
               for tm in e.mapping.tables if table_id in source_ids(tm, list(e.tables)) for c in tm.columns)


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


def transfer_by_meaning(e: Example, raw: RawBusiness, llm: LLMClient,
                        pairs: dict[str, list[str]] | None = None) -> Mapping | None:
    """The example's mapping moved onto a shop sharing its files, columns matched by meaning; None when the orders or
    lines lose a required column, or when the example's ledger has no order ids and the shop's has (04/11: a shop
    with order ids read row by row like the example passed every check with 68 wrong answers of 119). `pairs`: the
    tables paired otherwise (by_role); by default by file name or README meanings."""
    by_llm = pairs is not None
    pairs = pair_tables(e, raw) if pairs is None else pairs
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
            asked[key] = _ask_required_again(e, t, sorted(cols), raw, pairs[t], llm)
        renames[t] = _fill_date(e, t, asked[key], raw, pairs[t])
    grain = e.mapping.record_grain
    if grain == "order" and not _order_ids_group_lines(e, renames, new_ids, raw):
        # each row an order only on the last path (by role): before the README's own column notes it took two train
        # ledgers without order ids with fewer columns (a train ledger 40 → 29 right, 05/11)
        if not by_llm or not _as_rows(e, renames, new_ids, raw):
            return None
        grain = "line_is_record"
    tables = []
    for tm in e.mapping.tables:
        moved = _rename(tm, e, renames, new_ids, raw)
        if moved is None and tm.target in REQUIRED:
            return None
        if moved is not None:
            tables.append(moved)
    return Mapping(record_grain=grain, tables=tables,
                   notes=[f"ghép theo nghĩa với mapping mẫu {e.name} (LLM chọn cột)" if not by_llm
                          else f"ghép bảng theo vai trò, cột theo nghĩa với mapping mẫu {e.name} (LLM chọn bảng và cột)"])


def _as_rows(e: Example, renames: dict, new_ids: dict, raw: RawBusiness) -> bool:
    """N27, 05/11: a flat ledger example (orders and lines read from one table, with order ids) moved onto a ledger
    without any column grouping its rows: each row is an order (§8 "sổ không có mã đơn thì mỗi dòng sổ là một lần
    ghi"), as the hand mapping of such a ledger reads it (order id "_row"). The order id column of the example is
    renamed to "_row" in `renames`. False (no move) when the example is not flat or the shop's rows do group."""
    tables = {tm.target: source_ids(tm, list(e.tables)) for tm in e.mapping.tables if tm.target in REQUIRED}
    if len(tables) != 2 or set(tables["orders"]) != set(tables["lines"]):
        return False
    t = next((x for x in tables["lines"] if x in new_ids), None)
    if t is None or _has_order_ids(raw, new_ids[t]):
        return False
    ids = {c.source for tm in e.mapping.tables if tm.target in REQUIRED for c in tm.columns
           if c.target == "order_id" and c.source}
    for x in tables["lines"]:
        if x in renames:
            renames[x] = {**renames[x], **{c: "_row" for c in ids}}
    return True


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
            if tm.target == "orders" and c.target == "status" and (note := note_column(raw, ids)) is not None:
                columns.append(ColumnMap(target="status", source=note, transform="status_from_note"))  # N40
                continue
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


# ---------------------------------------------------------------- by role: tables paired by the LLM (N27)
# A shop of a format no example shares: its files are named otherwise (no stem in common) and its README does not
# describe each column, so neither file names nor README meanings pair its tables with an example's. Each table of the
# example plays a known part (one order per row, one order line per row, the product list, a lookup for a product's
# name…); the LLM picks the new shop's table playing that part, seeing names, columns, a few values and row counts.
# The columns are then matched as for a shop sharing the files, and the checks of meaning stop a wrong pairing.

TABLE_GUIDE = """Bạn ghép bảng của hai bộ dữ liệu bán hàng. Bảng của cửa hàng mẫu đã biết vai trò; cửa hàng mới đặt \
tên file, tên bảng và tên cột theo cách riêng. Với mỗi bảng của cửa hàng mẫu, chọn bảng của cửa hàng mới giữ cùng \
vai trò, tức mỗi dòng là cùng một loại bản ghi (một đơn, một dòng hàng của đơn, một mặt hàng, một khách, một lần thu \
tiền…), dựa vào tên bảng, tên cột, giá trị và số dòng. Cửa hàng mới không có bảng nào cùng vai trò thì chọn ""."""
MAX_COLUMNS, SAMPLE_CHARS = 30, 30  # columns shown per table, characters shown per value


STATUS_SHARE = 0.9  # share of a column's distinct values read as order statuses


def _has_statuses(raw: RawBusiness, ids: list[str]) -> bool:
    """Some column of these tables holds order status words: at least 90% of its distinct values read as a status."""
    frames = [t.frame for t in raw.tables if t.table_id in ids]
    for c in dict.fromkeys(str(c) for f in frames for c in f.columns):
        values = {str(v).strip() for f in frames if c in f.columns for v in f[c].dropna().unique()[:100]} - {""}
        if values and len(values) <= 20 and sum(read_word("orders", "status", v) is not None
                                                for v in values) >= STATUS_SHARE * len(values):
            return True
    return False


AMOUNT_MEDIAN_MIN = 1000  # đồng: line amounts of every train shop are thousands; quantities and counts are not


def _has_amounts(raw: RawBusiness, ids: list[str]) -> bool:
    """Some column of these tables holds money: at least 90% of its first values read as numbers, their median at
    least 1 000 đồng."""
    from datamate.loader.parse import parse_money
    frames = [t.frame for t in raw.tables if t.table_id in ids]
    for c in dict.fromkeys(str(c) for f in frames for c in f.columns):
        values = [v for f in frames if c in f.columns for v in f[c].dropna().astype(str).head(100) if v.strip()]
        nums = [n for n in map(parse_money, values) if n is not None]
        if values and len(nums) >= 0.9 * len(values) and sorted(nums)[len(nums) // 2] >= AMOUNT_MEDIAN_MIN:
            return True
    return False


def _quoted(values) -> str:
    return ", ".join(f'"{str(v)[:SAMPLE_CHARS]}"' for v in values)


def _role(e: Example, table_id: str) -> str:
    """What an example table is for: the canonical tables it feeds and the lookups made in it."""
    uses = [f"{tm.target} ({TABLES[tm.target].doc})" for tm in e.mapping.tables
            if table_id in source_ids(tm, list(e.tables))]
    uses += [f"tra cứu cho {tm.target}.{c.target}" for tm in e.mapping.tables for c in tm.columns
             if c.transform == "lookup" and c.args.get("table") == table_id]
    return "; ".join(dict.fromkeys(uses))


def _read_columns(e: Example, table_id: str) -> list[str]:
    """The columns of an example table its mapping reads (sources, lookup keys and values), in the table's order."""
    read = set()
    for tm in e.mapping.tables:
        if table_id in source_ids(tm, list(e.tables)):
            read.update(*(_reads(c) for c in tm.columns))
        for c in tm.columns:
            if c.transform == "lookup" and c.args.get("table") == table_id:
                read.update({c.args["key"], c.args["value"]})
    return [c for c in e.tables.get(table_id, ()) if c in read]


def pair_tables_by_llm(e: Example, raw: RawBusiness, llm: LLMClient) -> dict[str, list[str]]:
    """Example table id -> the new shop's tables playing its part, picked by the LLM; nothing when the example's
    orders and lines would fall on one table (a different record grain: no guess). Raises LLMUnavailable when the
    model does not answer (twice)."""
    groups = layout_groups(raw)
    used = sorted(_used_tables(e))
    if not groups or not used:
        return {}
    shown = []
    for i, ids in enumerate(groups, 1):
        frames = [t.frame for t in raw.tables if t.table_id in ids]
        cols = list(dict.fromkeys(str(c) for f in frames for c in f.columns))[:MAX_COLUMNS]
        more = f" và {len(ids) - 1} bảng cùng dạng" if len(ids) > 1 else ""
        shown.append(f'b{i}: bảng "{ids[0]}"{more}, {sum(len(f) for f in frames)} dòng; cột: '
                     + ", ".join(f'"{c}" ({_quoted(_samples(frames, c, 2))})' for c in cols))
    asked = []
    for i, t in enumerate(used, 1):
        samples = e.samples.get(t, {})
        asked.append(f't{i}: bảng mẫu "{t}" = {_role(e, t)}; cột: '
                     + ", ".join(f'"{c}" ({_quoted(samples.get(c, [])[:2])})' for c in _read_columns(e, t)[:MAX_COLUMNS]))
    user = "Bảng của cửa hàng mới:\n" + "\n".join(shown) + "\n\nBảng của cửa hàng mẫu cần ghép:\n" + "\n".join(asked)
    labels = [f"b{i}" for i in range(1, len(groups) + 1)]
    keys = [f"t{i}" for i in range(1, len(used) + 1)]
    # an example table read for the order status takes only a table with status words, when the shop has one
    # (05/11: a sales ledger paired with a delivery note of the same columns but no status)
    with_status = [lab for lab, ids in zip(labels, groups) if _has_statuses(raw, ids)]
    reads_status = {t for tm in e.mapping.tables if tm.target == "orders" for t in source_ids(tm, list(e.tables))
                    if any(c.target == "status" and c.source and c.transform != "lookup" for c in tm.columns)}
    # likewise the lines take a table with an amount column (05/11: a sale's lots per line, as many rows as the
    # lines and the same order ids, but no money, taken for the lines)
    with_amount = [lab for lab, ids in zip(labels, groups) if _has_amounts(raw, ids)]
    reads_amount = {t for tm in e.mapping.tables if tm.target == "lines" for t in source_ids(tm, list(e.tables))
                    if any(c.target == "line_amount" and c.source and c.transform is None for c in tm.columns)}

    def offered(t: str) -> list[str]:
        out = [lab for lab in labels if (t not in reads_status or not with_status or lab in with_status)
               and (t not in reads_amount or not with_amount or lab in with_amount)]
        return out or labels
    schema = {"type": "object", "additionalProperties": False, "required": keys,
              "properties": {k: {"enum": offered(t) + [""]} for k, t in zip(keys, used)}}
    answer = _generate(llm, [{"role": "system", "content": TABLE_GUIDE}, {"role": "user", "content": user}],
                       schema, e.name)
    pairs = {t: groups[labels.index(answer[k])] for k, t in zip(keys, used) if answer.get(k) in labels}
    core = {r: {i for tm in e.mapping.tables if tm.target == r for i in source_ids(tm, list(e.tables))}
            for r in REQUIRED}
    orders = {tuple(pairs[t]) for t in core["orders"] if t in pairs}
    lines = {tuple(pairs[t]) for t in core["lines"] if t in pairs}
    # an example's orders and lines on one sheet of the shop: only a flat sheet whose rows group into orders (public
    # shop, 06/11: "hoá đơn và chi tiết gộp chung sheet BanHang, thông tin hoá đơn lặp lại"); otherwise no guess
    if core["orders"] != core["lines"] and any(not _has_order_ids(raw, list(ids)) for ids in orders & lines):
        return {}
    return pairs


def by_role(raw: RawBusiness, pool: list[Example] | None, llm: LLMClient
            ) -> tuple[list[tuple[Example, dict[str, list[str]]]], list[str]]:
    """Examples whose orders and lines found a table, with their tables paired by the LLM: those reading the most of
    the shop's tables first, then those pairing the largest share of their own (05/11: ranked by share alone, a
    one-sheet ledger, all of its one table paired, came before the exports of many tables for a shop of 13 tables).
    Also the examples the LLM did not answer for (N164b), so a dead call is not read as "no table fits"."""
    ranked, failed = [], []
    for e in examples() if pool is None else pool:
        try:
            pairs = pair_tables_by_llm(e, raw, llm)
        except LLMUnavailable:
            failed.append(e.name)
            continue
        core = {i for tm in e.mapping.tables if tm.target in REQUIRED for i in source_ids(tm, list(e.tables))}
        if core and core <= set(pairs):
            read = len({tuple(ids) for ids in pairs.values()})
            ranked.append((read, len(pairs) / len(_used_tables(e)), e.name, e, pairs))
    return [(e, pairs) for *_, e, pairs in sorted(ranked, key=lambda r: (-r[0], -r[1], r[2]))], failed
