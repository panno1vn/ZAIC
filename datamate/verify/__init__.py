"""[V] Check a result and collect the signals the decision [E] uses. Leader.

Every signal starts pessimistic (contracts.results.Signals) and is raised only on evidence.
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import date

from datamate.contracts import CanonicalDB, ExecResult, Filter, Mapping, ResolvedPeriod, ResolvedPlan, Signals

# filter fields whose value must be found in the data by [C3]; others (shift, weekday, size, numbers) need no linking
LINKED_FIELDS = frozenset({
    "product", "product_group", "category", "product_line", "brand", "active_ingredient", "customer",
    "customer_group", "channel", "payment_method", "employee", "supplier", "service", "vehicle_model", "plate",
})


def filter_keys(f: Filter) -> list[str]:
    """Keys under which [C3] records the linked value of a filter: each value as written."""
    values = f.value if isinstance(f.value, list) else [f.value]
    return [str(v) for v in values]


def coverage(period: ResolvedPeriod | None, span: tuple[date, date] | None) -> str | None:
    """How much of the period lies inside the data's date span: full / partial / none (§7)."""
    if period is None:
        return "full"
    if span is None:
        return None
    lo, hi = span
    if period.mode == "stock":
        return "none" if period.end < lo else "full"
    if period.end < lo or period.start > hi:
        return "none"
    return "full" if period.start >= lo and period.end <= hi else "partial"


# §7 rows the "period wholly outside the shop's data: unanswerable" decision relies on (N28)
R_OUTSIDE = ("§7.p_cau_khong_tra_loi_duoc_khi", "§7.p_khong_co_du_lieu_khac_voi")
# N83: the reason nlu writes on an out-of-scope plan it made itself for a quality the data does not record
SUBJECTIVE_REASON = "câu hỏi phẩm chất người / nhà cung cấp: dữ liệu không ghi (§7)"
NOT_RECORDED_REASON = "cửa hàng không ghi giới tính / địa chỉ khách (§7)"  # N89, set by the pipeline from the README
OWN_REASONS = frozenset({SUBJECTIVE_REASON, NOT_RECORDED_REASON})


# tables without their own dates take the span of the table that dates them
DATE_OWNER = {"lines": "orders", "lot_sales": "orders", "payments": "orders", "returns": "orders",
              "deliveries": "orders", "installments": "orders"}


def data_span(db: CanonicalDB, requires: list[str]) -> tuple[date, date] | None:
    """Date span of the data a result relies on: first required table with a span, else its dating table."""
    for table in [r.split(".")[0] for r in requires] + ["orders"]:
        for t in (table, DATE_OWNER.get(table)):
            if t and t in db.date_ranges:
                return db.date_ranges[t]
    return None


def _sane(result: ExecResult) -> bool:
    v = result.value
    if v is None:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return math.isfinite(v)
    if isinstance(v, list):
        return len(v) > 0
    if isinstance(v, dict):
        return bool(v.get("rows"))
    return True


# N37: a time in the question ("tháng 12/2025", "hôm qua", "Tết"): an out-of-scope reading of it is an LLM misreading
# of a figure, not a question the data cannot hold (train 05/11: 7 of 8 out-of-scope readings have no time, all
# unanswerable; the eighth, "nhân viên bán giỏi nhất tháng 12/2025", is a ranking)
# N159: "quý" only as a quarter ("quý 2", "quý này"): "khách quý mến nhất" folds to "quy men", no time (train: "Ai
# trong cửa hàng đc khách quý mến nhất?" unanswerable, refused as a reading with a time)
_TIME = re.compile(r"\b(?:thang|tuan|quy (?:\d|i|ii|iii|iv|nay|truoc|toi|sau|vua|roi)|ngay|hom nay|hom qua|bua qua"
                   r"|bua nay|hqua|tet|nam nay|nam ngoai|nam truoc|nam \d{4}|\d{1,2}/\d{2,4}|\d{4})\b")


# N38, train 05/11: the 104 purchase questions of shops whose README conventions name "Nhập hàng" are answerable, the
# 5 of the shops whose conventions do not are all unanswerable
PURCHASE_METRICS = frozenset({"purchase_amount", "purchase_avg_cost", "receipt_count", "purchase_minus_sales"})


def _asks_purchases(p) -> bool:
    measures = list(p.measures) + ([p.share_of] if p.share_of else [])
    return any(m.metric in PURCHASE_METRICS for m in measures) or (p.rank is not None and p.rank.entity == "supplier")


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# N112. §7 "Thông tin file không ghi thì không suy ra từ cột khác … shop không ghi loại thông tin câu hỏi cần thì không
# trả lời được": a question by product group, by a sale's profit or by the reason an order was returned or cancelled,
# in a shop whose README names no such column and whose mapping found none. Train: "lãi gộp <tháng>" in a pharmacy
# whose README names no cost, "đơn bị huỷ vì giao trễ", "trả hàng vì lỗi và vì mua nhầm" in shops naming no reason:
# all three unanswerable. Public (s65): 7 questions by "nhóm trà / nhóm sơn / nhóm điện" in two shops with no group
# column, 3 by a return or cancel reason, 1 "mặt hàng nào lời nhiều nhất" without cost.
_REASON_ASKED = re.compile(r"\b(?:huy|tra)\b(?:\s+\S+){0,4}?\s+vi\s+(?!dien\b)\S")  # "bị huỷ vì giao trễ", "trả lại vì"
_NOT_REASON = re.compile(r"\bbang vi\b|\bvi (?:dien tu|momo|zalo|shopee|tien)\b")  # "trả bằng ví điện tử"
# a column the README names for the group: "- **Nhóm**: nhóm hàng", "loại hàng", "danh mục" (folded lines)
_GROUP_NOTE = re.compile(r"^\s*-\s*\*\*[^*]+\*\*\s*:\s*(?:nhom\b(?! khach)|loai hang|danh muc|phan loai)")
PROFIT_METRICS = frozenset({"gross_profit"})


def _filter_fields(node) -> set[str]:
    if isinstance(node, dict):
        out = {node["field"]} if isinstance(node.get("field"), str) else set()
        return out.union(*(_filter_fields(v) for v in node.values()))
    if isinstance(node, list):
        return set().union(*(_filter_fields(v) for v in node))
    return set()


def _has(db: CanonicalDB, tables: tuple[str, ...], column: str) -> bool:
    return any((df := db.table(t)) is not None and column in df.columns and df[column].notna().any() for t in tables)


def not_recorded(plan, question: str, db: CanonicalDB) -> str | None:
    """N112: what the question needs that the shop does not record (§7), or None. Only from the README and the
    mapped data together: a column the README names, or the mapping found, is recorded."""
    readme = [_fold(line) for line in db.readme.splitlines()]
    if not readme:
        return None
    text = " ".join(readme)
    q = " ".join(_fold(question).split())
    if _REASON_ASKED.search(q) and not _NOT_REASON.search(q) and not re.search(r"\bly do\b|\bnguyen nhan\b", text) \
            and not _has(db, ("returns",), "reason"):
        return "lý do trả / huỷ đơn"
    if plan is None:
        return None
    fields = _filter_fields(plan.model_dump(mode="json", exclude_none=True))
    if plan.rank is not None:
        fields.add(plan.rank.entity)
    if "product_group" in fields and not _has(db, ("products", "lines"), "product_group") \
            and not any(_GROUP_NOTE.search(line) for line in readme):
        return "nhóm hàng"
    asked = {m.metric for m in list(plan.measures) + ([plan.share_of] if plan.share_of else [])}
    if plan.rank is not None:
        asked.add(plan.rank.by)
    if asked & PROFIT_METRICS and "gia von" not in text and not _has(db, ("lines", "products"), "unit_cost"):
        return "giá vốn"
    # N115. Stock in a shop that keeps none: train "hết hôm nay bia tiger còn mấy lon trong kho" in 4 shops whose README
    # never writes "tồn", "kho" or "lô" and whose mapping has no stock or lot table: 9 / 9 unanswerable; every train
    # shop whose stock question is answerable writes "Tồn kho", "Tồn thực" or "số lô" (lots, §6 Nhà thuốc)
    # stock words as phrases: a single "kho" is also "khổ" folded ("lưới B40 mạ kẽm khổ 1.5m", a train shop with no stock)
    if asked & _STOCK_ASKED and not re.search(_STOCK_WORDS, text) \
            and not any(db.has(t) for t in ("inventory", "lots")):
        return "tồn kho"
    # N121. Customers in a shop that records none, debts in a shop that keeps none (train: two shops whose README has
    # no column about customers: every customer question unanswerable, 8 / 8; two whose README never writes "nợ":
    # every debt question unanswerable, 3 / 3). A README column "…khách…" or a mapped customer key is a record.
    customer_asked = (fields & {"customer", "customer_group"}) or asked & _CUSTOMER_METRICS or (
        plan.rank is not None and plan.rank.entity == "customer") or (
        plan.threshold is not None and plan.threshold.entity == "customer")
    if customer_asked and not any(re.search(r"\bkhach\b", line) for line in readme if line.lstrip().startswith("-")) \
            and not _has(db, ("orders",), "customer_key"):
        return "khách hàng"
    # N160: "ghi sổ" (on credit), not "ghi số lượng" (train: a README "hàng trả ghi số lượng âm" with no debt at all
    # read as a debt record, so "3 khách nợ nhiều nhất" stayed blank instead of unanswerable)
    # N172: nor a debt written only as a term of credit ("Hạn nợ (ngày)": số ngày được nợ; "công nợ theo hạn"), which
    # records when an order must be paid, not what was paid (train: such a README, "3 khách còn nợ nhiều nhất"
    # unanswerable; every train shop that answers debts has payment rows or a "còn nợ" column)
    owed = re.sub(r"\b(?:han|duoc|cong) no\b|\bban no co han\b", " ", text)
    if asked & _DEBT_METRICS and not re.search(r"\bno\b|\bghi so\b(?! luong)|\bchiu\b", owed) \
            and not db.has("payments"):
        return "công nợ"
    # N161. A sales channel, a payment method, a customer group the shop does not record (§7: train, plans with such
    # a filter in shops with neither a mapped column nor a README word for it: channel 2 / 2, payment method 2 / 2,
    # customer group 1 / 1 unanswerable). Only a value that is a channel / payment code (synonyms.json): "hqua có
    # tổng cộng nhiêu ddown" read with payment_method = "đơn" is a misreading, not a payment question.
    from datamate.nlu import linking  # late import: nlu imports this module
    coded = {f.field for m in list(plan.measures) + ([plan.share_of] if plan.share_of else []) for f in m.filters
             if f.field in ("channel", "payment_method")
             and all(linking.concept(f.field, str(v)) for v in (f.value if isinstance(f.value, list) else [f.value]))}
    if "channel" in coded and not _has(db, ("orders",), "channel") \
            and not re.search(r"\bkenh\b|\bban qua\b|\bnguon don\b|\bnoi ban\b", text):
        return "kênh bán"
    if "payment_method" in coded and not _has(db, ("orders", "payments"), "payment_method") \
            and not re.search(r"\bthanh toan bang\b|\bhinh thuc (?:thanh toan|tt|tra)\b|\bphuong thuc\b|\btra bang\b"
                              r"|\bcach tra\b|\b(?:thanh toan|tt)\s*:", text):
        return "hình thức thanh toán"
    if "customer_group" in fields and not _has(db, ("orders", "customers"), "customer_group") \
            and not re.search(r"\bnhom khach\b|\bloai khach\b|\bhang (?:thanh vien|khach)\b|\bthanh vien\b", text):
        return "nhóm khách"
    # N162. Expiry dates in a shop that keeps none (§6 Nhà thuốc keeps lots): train "những sp nào đang còn hàng có hạn
    # dùng từ … đến hết …" in 3 shops with no lot table and no README word for expiry, 3 / 3 unanswerable
    expiry = (plan.list_spec is not None and plan.list_spec.condition in _EXPIRY_CONDITIONS) or asked & {"nearest_expiry"}
    if expiry and not db.has("lots") and not re.search(r"\bhan (?:dung|su dung)\b|\bhsd\b|\bhet han\b|\bso lo\b", text):
        return "hạn dùng"
    return None


_EXPIRY_CONDITIONS = frozenset({"expiring_within"})


_STOCK_ASKED = frozenset({"stock_qty", "stock_value"})
_STOCK_WORDS = r"\bton (?:kho|thuc|cuoi|dau)\b|\bso lo\b|\bma lo\b|\bkho hang\b|\bhang ton\b|\bthe kho\b"
_CUSTOMER_METRICS = frozenset({"customer_count", "new_customer_count", "debtor_count"})
_DEBT_METRICS = frozenset({"debt_total", "debt_amount", "debt_paid", "debt_added", "debtor_count", "overdue_amount"})


def collect_signals(plan: ResolvedPlan | None, result: ExecResult | None, db: CanonicalDB, mapping: Mapping,
                    rules: dict[str, bool], question: str = "") -> Signals:
    s = Signals(mapping_ok=mapping.ok)
    if mapping.ok and question and all(rules.get(r, False) for r in R_OUTSIDE) \
            and (missing := not_recorded(plan.plan if plan is not None else None, question, db)) is not None:
        s.intent_known = s.out_of_scope = s.subjective = True  # decide: unanswerable (§7)
        s.notes.append(f"cửa hàng không ghi {missing} (§7)")
        return s
    if plan is None:
        return s
    p = plan.plan
    s.intent_known = True
    s.out_of_scope = p.intent == "out_of_scope"
    if s.out_of_scope and question and all(rules.get(r, False) for r in R_OUTSIDE):
        # N83: nlu's own reading of a quality question is unanswerable with or without a time ("khách thân thiện
        # nhất <tháng>"); the LLM's out-of-scope reading only without one (N37)
        s.subjective = p.out_of_scope_reason in OWN_REASONS or not _TIME.search(_fold(question))
    measures = list(p.measures) + ([p.share_of] if p.share_of else [])
    filters = [f for m in measures for f in m.filters] + list((p.compare.filters or []) if p.compare else [])
    linkable = [k for f in filters if f.field in LINKED_FIELDS for k in filter_keys(f)]
    s.entities_ok = all(k in plan.linked for k in linkable)  # no linkable filter: nothing to link, so ok
    if plan.omitted:  # N36: a name the question writes is missing from the plan
        s.entities_ok = False
    if all(rules.get(r, False) for r in R_OUTSIDE) and _asks_purchases(p) and db.conventions is not None \
            and "nhap hang" not in db.conventions and not db.has("purchases"):
        s.not_recorded = True  # N38: the README's conventions name no purchases, and none were mapped (§7)
    shop = db.date_ranges.get("orders")  # §7 "khoảng ngày có dữ liệu của shop", not the span of one table
    if plan.period is not None and shop is not None and all(rules.get(r, False) for r in R_OUTSIDE):
        compared = plan.compare_period if p.compare is not None and p.compare.kind != "filter" else None
        s.outside_data = any(coverage(x, shop) == "none" for x in (plan.period, compared) if x is not None)
    if result is None:
        return s
    s.required_fields_present = all(
        db.has(*r.split(".", 1)) if "." in r else db.has(r) for r in result.requires)
    span = data_span(db, result.requires)
    s.period_coverage = coverage(plan.period, span)
    if p.compare is not None and p.compare.kind != "filter":
        s.compare_coverage = coverage(plan.compare_period, span)
    s.sane = _sane(result)
    if "tie" in result.notes:  # metrics.sales.TIE: the generator leaves ties out, so ours mean a misread (N25)
        s.ranking_clear = False
    s.rules_unchanged = bool(result.rule_ids) and all(rules.get(r, False) for r in result.rule_ids)
    return s
