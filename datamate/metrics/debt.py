"""Debts, exact to rulebook §4: debt added and paid in a period, and what is still owed at the end of a day (total,
number of debtors, one customer's, ranking of debtors). Work package G5, v2 metrics in the order of their number of
train questions (docs/research/templates.md).

Probe 04/11 against the train answers of the two mapped shops that record debts: every question of these shapes
(total paid in a month; one customer's added and paid debt; total owed; number of debtors) matched the formulas.
"""
from __future__ import annotations

import pandas as pd

from datamate.contracts import CanonicalDB, ExecResult, Measure, ResolvedPlan
from datamate.contracts.plan import expected_answer_type
from datamate.formatter import money
from datamate.nlu import linking

from . import frames as F
from .registry import metric
from .sales import TIE, _first_name, _ordered, _tied  # one naming and tie rule for every ranking (§3, §9)

R_DEBT = ("§4.no_them_tra_no_thu_no_trong_ky", "§4.don_cod_don_ban_qua_san_tmdt", "§4.don_duoc_tinh_vao_no",
          "§4.no_theo_khach", "§3.xac_dinh_khach", "§8.ten_goi_nhan", "§0.p_hom_nay_cua_moi_cau_la")
R_OWED = ("§4.no_mot_don_tai_ngay_x", "§4.don_duoc_tinh_vao_no", "§4.don_cod_don_ban_qua_san_tmdt",
          "§4.no_theo_khach", "§2.den_het_ngay_x_tinh_den_hom_nay", "§3.xac_dinh_khach", "§8.ten_goi_nhan",
          "§0.p_hom_nay_cua_moi_cau_la")
R_TIES = ("§9.p_bang_nhau_hai_doi_tuong_bang",)
FLOW = frozenset({"debt_added", "debt_paid"})
DEBT_CODES = frozenset({"debt", "installment"})  # §6 điện thoại: "đơn trả góp là đơn ghi nợ (§4)"
REQUIRES = ("payments.paid_time", "payments.amount", "orders.payment_method", "orders.total_due")


def debt_orders(db: CanonicalDB, m: Measure, linked: dict[str, str]) -> pd.DataFrame | None:
    """§4: orders written as debt ("ghi nợ"), not cancelled (returned ones stay); COD is its own method, never debt.
    A customer filter keeps that customer's orders (§3: by customer key)."""
    o = F.orders(db)
    if o is None or "payment_method" not in o.columns:
        return None
    codes = {v: linking.concept("payment_method", v) for v in o["payment_method"].dropna().astype(str).unique()}
    debt = o[o["payment_method"].astype(str).map(codes).isin(DEBT_CODES)]
    if F.unknown_status(debt):
        return None  # a debt order that may be cancelled
    debt = debt[debt["status"].ne("cancelled")]
    for f in m.filters:
        keys = [linked.get(str(v)) for v in (f.value if isinstance(f.value, list) else [f.value])]
        if f.field != "customer" or f.op not in ("eq", "in") or None in keys or "customer_key" not in debt.columns:
            return None
        debt = debt[debt["customer_key"].isin(keys)]
    return debt


def _payments(db: CanonicalDB, debt: pd.DataFrame) -> pd.DataFrame | None:
    """Payments of the debt orders with their day and their order's day; refunds (negative amounts) left out (§4:
    "hoàn tiền trả hàng không trừ")."""
    p = db.table("payments")
    if p is None or p["amount"].isna().any() or p["paid_time"].isna().any():
        return None
    pay = p[p["amount"] > 0].merge(debt[["order_id", "day"]], on="order_id")
    return pay.assign(paid_day=pay["paid_time"].dt.date)


def debt_paid(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    """§4 "trả nợ / thu nợ": payments made after the day of purchase and dated in the period, of every debt order
    (orders of earlier periods and returned orders too). Paying on the day of purchase is paying at purchase."""
    debt = debt_orders(db, m, plan.linked)
    pay = None if debt is None else _payments(db, debt)
    if pay is None or plan.period is None:
        return None
    p = plan.period
    later = pay[(pay["paid_day"] > pay["day"]) & (pay["paid_day"] >= p.start) & (pay["paid_day"] <= p.end)]
    return money(float(later["amount"].sum()))


def debt_added(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    """§4 "nợ thêm": of the debt orders placed in the period, the part of the order total (§4: after the order
    discount, with the shipping fee) not paid on the day of purchase."""
    debt = debt_orders(db, m, plan.linked)
    pay = None if debt is None else _payments(db, debt)
    if pay is None or plan.period is None or "total_due" not in debt.columns:
        return None
    placed = debt[F.in_period(debt, plan.period)]
    if placed["total_due"].isna().any():
        return None
    same_day = pay[pay["paid_day"] == pay["day"]].groupby("order_id")["amount"].sum()
    owed = (placed["total_due"] - placed["order_id"].map(same_day).fillna(0.0)).clip(lower=0)
    return money(float(owed.sum()))


def open_orders(db: CanonicalDB, day) -> pd.DataFrame | None:
    """§4 "nợ một đơn tại ngày X": orders placed by the end of the day, not cancelled (returned ones stay), with their
    balance = order total (§4: after the order discount, with the shipping fee) − payments made by then; the ones
    still owing (> 0). COD orders are never debts (§4). The rule counts every other order; the train shops' debts are
    all on orders written as debt, so an unpaid order of another method means the data or the mapping does not read
    as the rule expects: None rather than a guess (probe 04/11: 13/13 questions, both readings equal)."""
    o, p = F.orders(db), db.table("payments")
    if o is None or p is None or not {"total_due", "payment_method"} <= set(o.columns):
        return None
    if p["amount"].isna().any() or p["paid_time"].isna().any():
        return None
    o = o[o["day"] <= day]
    if F.unknown_status(o):
        return None
    o = o[o["status"].ne("cancelled")]
    codes = {v: linking.concept("payment_method", v) for v in o["payment_method"].dropna().astype(str).unique()}
    method = o["payment_method"].astype(str).map(codes)
    if o.loc[method.isin(DEBT_CODES), "total_due"].isna().any():
        return None
    paid = p[(p["amount"] > 0) & (p["paid_time"].dt.date <= day)].groupby("order_id")["amount"].sum()
    balance = o["total_due"] - o["order_id"].map(paid).fillna(0.0)
    owing = o.assign(balance=balance, method=method)[(balance > 1e-6) & method.ne("cod")]
    return owing if owing["method"].isin(DEBT_CODES).all() else None


AGE_OPS = {"gte": lambda a, v: a >= v, "gt": lambda a, v: a > v, "lte": lambda a, v: a <= v, "lt": lambda a, v: a < v,
           "eq": lambda a, v: a == v}


def _owing(db: CanonicalDB, plan: ResolvedPlan, m: Measure | None) -> pd.DataFrame | None:
    day = plan.period.end if plan.period is not None else plan.as_of
    owing = open_orders(db, day)
    for f in (m.filters if m is not None else []):
        if f.field == "payment_method" and owing is not None and f.op in ("eq", "in"):
            # "tiền góp chưa trả": the installment orders only (§6 điện thoại "Trả góp")
            codes = {linking.concept("payment_method", str(v)) for v in (f.value if isinstance(f.value, list) else [f.value])}
            if None in codes:
                return None
            owing = owing[owing["method"].isin(codes)]
            continue
        if f.field == "debt_age_days":  # §4 "tuổi nợ: số ngày tính từ ngày đặt; đơn đặt hôm nay có tuổi nợ 0 ngày"
            if owing is None or f.op not in AGE_OPS or not isinstance(f.value, (int, float)) or isinstance(f.value, bool):
                return None
            age = owing["day"].map(lambda d: (day - d).days)
            owing = owing[AGE_OPS[f.op](age, float(f.value))]
            continue
        keys = [plan.linked.get(str(v)) for v in (f.value if isinstance(f.value, list) else [f.value])]
        if (owing is None or f.field != "customer" or f.op not in ("eq", "in") or None in keys
                or "customer_key" not in owing.columns):
            return None
        owing = owing[owing["customer_key"].isin(keys)]
    return owing


def debt_total(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    """§4 "còn nợ": the balances of every order still owing at the end of the day, walk-in orders included."""
    owing = _owing(db, plan, m)
    return None if owing is None else money(float(owing["balance"].sum()))


def debtor_count(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    """Customers (§3: by customer key; walk-ins are not customers, §4) with an order still owing."""
    owing = _owing(db, plan, m)
    return None if owing is None or "customer_key" not in owing.columns else int(owing["customer_key"].nunique())


def debt_amount(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    """What one customer (the filter) still owes: a debt amount needs its customer."""
    return debt_total(db, plan, m) if any(f.field == "customer" for f in m.filters) else None


def rank_debtors(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """Customers by what they still owe at the end of the day (§4 "nợ theo khách"), ties by code (§9); with values
    the table [customer, amount owed] the train answers use."""
    r = plan.plan.rank
    if r.order != "desc" or r.min_orders or any(m.filters for m in plan.plan.measures):
        return None
    owing = _owing(db, plan, None)
    if owing is None or "customer_key" not in owing.columns:
        return None
    totals = owing.dropna(subset=["customer_key"]).groupby("customer_key")["balance"].sum()
    if totals.empty:
        return None
    keys = _ordered(totals, r.k)
    every = F.orders(db)
    names = _first_name(every["customer_key"], every.get("customer_name", every["customer_key"]))
    customers = db.table("customers")
    if customers is not None and "customer_name" in customers.columns:
        names = {**names, **_first_name(customers["customer_key"], customers["customer_name"])}
    labels = [names.get(str(k), str(k)) for k in keys]
    if r.with_values:
        value = {"columns": ["khach_hang", "so_tien_no"],
                 "rows": [[label, money(float(totals[k]))] for label, k in zip(labels, keys)]}
    else:
        value = labels[0] if r.k == 1 else labels
    tied = _tied(totals, r.k, order_matters=not r.with_values and r.k != 1)  # a table's row order is not scored
    return ExecResult(value=value, answer_type=expected_answer_type(plan.plan), source="D1",
                      function="debt.rank_debtors", rule_ids=sorted(set(R_OWED + R_TIES)), requires=list(REQUIRES),
                      notes=[TIE] if tied else [])


def _overdue(db: CanonicalDB, plan: ResolvedPlan, m: Measure | None) -> pd.Series | None:
    """What each installment order has overdue at the end of the day (§6 điện thoại "Trả góp": "kỳ góp có hạn trước
    ngày hỏi mà chưa góp đủ là quá hạn; kỳ có hạn đúng ngày hỏi thì chưa quá hạn"): the amounts of its periods due
    before the day, less what it paid in installments by then, never below 0; indexed by order."""
    sched, pay = db.table("installments"), db.table("payments")
    if sched is None or pay is None or "kind" not in pay.columns or plan.period is None:
        return None
    day = plan.period.end
    owing = _owing(db, plan, m)
    if owing is None:
        return None
    due = sched[pd.to_datetime(sched["due_date"]).dt.date < day].groupby("order_id")["amount_due"].sum()
    paid = pay[(pay["kind"] == "installment") & (pay["paid_time"].dt.date <= day)].groupby("order_id")["amount"].sum()
    late = (due - paid.reindex(due.index).fillna(0.0)).clip(lower=0)
    return late[late.index.isin(set(owing["order_id"])) & (late > 1e-6)]


def overdue_amount(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    late = _overdue(db, plan, m)
    return None if late is None else money(float(late.sum()))


def overdue_installment_count(db: CanonicalDB, plan: ResolvedPlan, m: Measure):
    """Customers with an overdue installment ("mấy khách quá hạn góp", "mấy người trả góp còn kỳ quá hạn chưa đóng":
    every such question of the public shop counts customers), each by its customer key (§3)."""
    late = _overdue(db, plan, m)
    o = F.orders(db)
    if late is None or o is None or "customer_key" not in o.columns:
        return None
    who = o.set_index("order_id")["customer_key"].reindex(late.index)
    return None if who.isna().any() else int(who.nunique())


MEASURES = {"debt_added": debt_added, "debt_paid": debt_paid, "debt_total": debt_total,
            "debtor_count": debtor_count, "debt_amount": debt_amount, "overdue_amount": overdue_amount,
            "overdue_installment_count": overdue_installment_count}


def value_of(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """One figure, or several in the order asked ("nợ thêm bao nhiêu và trả được bao nhiêu"): a list."""
    ms = plan.plan.measures
    if not ms or any(m.metric not in MEASURES for m in ms):
        return None
    if len({m.metric in FLOW for m in ms}) > 1:
        return None  # a flow over the period and a state at its end: no question of train asks both at once
    values = [MEASURES[m.metric](db, plan, m) for m in ms]
    answer_type = expected_answer_type(plan.plan)
    if any(v is None for v in values) or answer_type is None:
        return None
    rules = R_DEBT if ms[0].metric in FLOW else R_OWED
    if any(f.field == "debt_age_days" for m in ms for f in m.filters):
        rules += R_AGE
    if db.table("installments") is not None:  # the shop's debts include its installments (§6 điện thoại)
        rules += R_INSTALLMENT
    return ExecResult(value=values[0] if len(values) == 1 else values, answer_type=answer_type, source="D1",
                      function="debt.value_of", rule_ids=sorted(set(rules)), requires=list(REQUIRES))


R_AGE = ("§4.tuoi_no",)
R_INSTALLMENT = ("§6.cua_hang_dien_thoai.tra_gop", "§6.p_luat_rieng_cua_tung_nganh_dung")
OVERDUE = frozenset({"overdue_amount", "overdue_installment_count"})
for _name in MEASURES:
    _rules = R_DEBT if _name in FLOW else R_OWED + R_AGE + (R_INSTALLMENT if _name in OVERDUE else ())
    metric("value", _name, requires=REQUIRES, rules=tuple(sorted(set(_rules))),
           filters=("customer",) if _name in FLOW else ("customer", "debt_age_days", "payment_method"))(value_of)
metric("rank", "debt_amount", entity="customer", requires=REQUIRES,
       rules=tuple(sorted(set(R_OWED + R_TIES))))(rank_debtors)
