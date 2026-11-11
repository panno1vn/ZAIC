"""Sales metrics, exact to rulebook §1–§3 (with §5 "hàng ế", price effect, §6 size and pharmacy rows). Work package
G5 / T3, ordered by the number of train questions each template carries (docs/research/templates.md).

A measure function gives one figure for a period under some filters, or None when it cannot be exact. The intent
functions build on them: value (one figure or several), compare (two periods, or two filters), share, rank, count
over a threshold, trend, series and unsold products. Every one returns None rather than a guess.
"""
from __future__ import annotations

import operator
from collections.abc import Callable
from datetime import timedelta

import pandas as pd

from datamate.contracts import CanonicalDB, ExecResult, Filter, Measure, ResolvedPeriod, ResolvedPlan
from datamate.contracts.plan import CODED_VALUES, expected_answer_type
from datamate.formatter import money
from datamate.nlu import linking

from . import frames as F
from .registry import metric

# ---------------------------------------------------------------- rule ids (assets/rules/reference_rules.json)
R_TODAY = ("§0.p_hom_nay_cua_moi_cau_la",)
R_VALID = ("§1.don_tinh_vao_doanh_thu", "§1.don_thuoc_ky_nao") + R_TODAY
R_REVENUE = R_VALID + ("§1.doanh_thu_mot_don", "§1.ban_duoc_bao_nhieu_tien_thu_ve_bao_nhieu_tien", "§3.mat_hang")
# N166: a rule row is cited when the plan depends on it (a filter, a ranked entity, a comparison, a period kind),
# not by every answer: a rulebook that drops or rewords an industry's section blanked 85 % of the split (F004)
FILTER_RULES = {
    "payment_method": ("§1.doanh_thu_theo_hinh_thuc_thanh_toan",),
    "customer_group": ("§1.doanh_thu_theo_nhom_khach", "§3.xac_dinh_khach"),
    "customer": ("§3.xac_dinh_khach",),
    "shift": ("§2.ca_sang_ca_chieu",),
    "product_group": ("§3.nhom_hang",), "category": ("§3.nhom_hang",),
    "size": ("§6.ca_phe.size_m_size_l",),
    "active_ingredient": ("§6.nha_thuoc.doanh_thu_theo_hoat_chat",),
    "prescription": ("§6.nha_thuoc.thuoc_ke_don",),
    # rows a filter of a repair ledger reads by (train's rulebook has neither)
    "service": ("§6.sua_xe.viec_ghi_trong_o_lam_gi",), "vehicle_model": ("§6.sua_xe.dong_xe_bien_so",),
    "stage": ("§6.me_va_be.so_sua_size_bim",),
}
R_NAMES = ("§8.ten_goi_nhan",)  # cited when a filter value is a name linked to the data
ENTITY_RULES = {"customer": ("§3.xac_dinh_khach",), "product_group": ("§3.nhom_hang",)}
R_METRIC = {
    "revenue": R_REVENUE,
    "order_count": R_VALID + ("§1.so_don",),
    "cancel_count": ("§1.don_bi_huy", "§1.don_thuoc_ky_nao") + R_TODAY,
    "cancel_rate": ("§1.ti_le_don_huy_trong_ky", "§1.don_bi_huy", "§1.don_thuoc_ky_nao") + R_TODAY,
    "avg_order_value": R_REVENUE + ("§1.so_don", "§3.gia_tri_trung_binh_mot_don"),
    "quantity": R_VALID + ("§3.mat_hang", "§3.ban_duoc_bao_nhieu_don_vi", "§10.don_vi_co_ban_don_vi_lon"),
    "customer_count": R_VALID + ("§1.so_don", "§3.xac_dinh_khach"),
    "gross_profit": R_REVENUE + ("§5.lai_gop", "§5.gia_von", "§3.hang_loi_nhat"),
    "net_profit": R_REVENUE + ("§5.lai_gop", "§5.gia_von", "§5.lai_rong_mot_thang"),
}
R_COMPARE = ("§1.phan_tram_thay_doi_tang_truong", "§1.chenh_lech_hon_kem_tang_giam_bao_nhieu_so_khong_",
             "§2.thang_nay", "§2.tet_nam_y_dip_tet_mua_tet", "§5.hieu_ung_tang_gia")  # every id a comparison may cite


def compare_rules(p) -> tuple[str, ...]:
    """The rows this comparison reads: its output, and its kind (the same days of last month, before Tết, the days
    since a price rise)."""
    c = p.compare
    out = ("§1.phan_tram_thay_doi_tang_truong",) if c.output == "pct_change" else \
        ("§1.chenh_lech_hon_kem_tang_giam_bao_nhieu_so_khong_",)
    if c.kind == "previous_same_days":
        out += ("§2.thang_nay",)
    if c.kind == "before_tet":
        out += ("§2.tet_nam_y_dip_tet_mua_tet",)
    if c.kind == "before_days_from":
        out += ("§5.hieu_ung_tang_gia",)
    return out


R_TIES = ("§9.p_bang_nhau_hai_doi_tuong_bang",)
R_RANK = R_TIES + ("§3.ban_chay", "§3.xac_dinh_khach", "§3.nhan_vien_ban_gioi_nhat")
R_COUNT = ("§2.qua_n_hon_n_tren_n_duoi_n", "§1.so_don", "§3.xac_dinh_khach")
R_UNSOLD = R_VALID + ("§5.mat_hang_khong_ban_duoc_trong_ky_e", "§3.mat_hang")

REQ_ORDERS = ("orders.order_time", "orders.status")
REQ_METRIC = {
    "revenue": REQ_ORDERS + ("lines.line_amount",),
    "order_count": REQ_ORDERS,
    "cancel_count": REQ_ORDERS,
    "cancel_rate": REQ_ORDERS,
    "avg_order_value": REQ_ORDERS + ("lines.line_amount",),
    "quantity": REQ_ORDERS + ("lines.base_qty",),
    "customer_count": REQ_ORDERS + ("orders.customer_key",),
    "gross_profit": REQ_ORDERS + ("lines.line_amount", "lines.unit_cost"),
    "net_profit": REQ_ORDERS + ("lines.line_amount", "lines.unit_cost", "expenses.amount"),
}


# ---------------------------------------------------------------- one figure for a period
def _line_filtered(filters: list[Filter]) -> bool:
    return any(f.field in F.LINE_FILTERS for f in filters)


def _orders(db: CanonicalDB, period: ResolvedPeriod, filters: list[Filter], linked: dict[str, str],
            statuses: tuple[str, ...] | None = F.VALID_STATUSES) -> pd.DataFrame | None:
    """Orders of the period (by order date, §1) passing the order-level filters; `statuses` None = every status."""
    o = F.orders(db)
    if o is None:
        return None
    mask = F.order_mask(o, filters, linked)
    if mask is None:
        return None
    mask &= F.in_period(o, period)
    if F.unknown_status(o[mask]):
        return None
    if statuses is not None:
        mask &= o["status"].isin(statuses)
    return o[mask]


def _lines(db: CanonicalDB, period: ResolvedPeriod, filters: list[Filter], linked: dict[str, str],
           items_only: bool = False) -> pd.DataFrame | None:
    """Lines of the period's valid orders passing every filter; `items_only` drops fee lines (§3 "Phí phục vụ")."""
    o, ln = _orders(db, period, filters, linked), F.lines(db)
    if o is None or ln is None:
        return None
    mask = F.line_mask(ln, filters, linked)
    if mask is None:
        return None
    mask &= ln["order_id"].isin(set(o["order_id"]))
    if items_only and "is_item" in ln.columns:
        mask &= ln["is_item"].ne(False)
    return ln[mask]


def revenue(db, period, filters, linked, m=None, strict_unit=True):
    if _line_filtered(filters):  # revenue of the matching lines only (a product, a group)
        ln = _lines(db, period, filters, linked)
        if ln is None or ln["line_amount"].isna().any():
            return None
        return money(float(ln["line_amount"].sum()))
    o = _orders(db, period, filters, linked)
    if o is None or not o["revenue_ok"].all():
        return None
    return money(float(o["revenue"].sum()))


def order_count(db, period, filters, linked, m=None, strict_unit=True):
    if _line_filtered(filters):  # §1 "số đơn có một mặt hàng": valid orders with at least one matching line
        ln = _lines(db, period, filters, linked)
        return None if ln is None else int(ln["order_id"].nunique())
    o = _orders(db, period, filters, linked)
    return None if o is None else int(o["order_id"].nunique())


def cancel_count(db, period, filters, linked, m=None, strict_unit=True):
    if _line_filtered(filters):
        return None
    o = _orders(db, period, filters, linked, statuses=("cancelled",))
    return None if o is None else int(o["order_id"].nunique())


def cancel_rate(db, period, filters, linked, m=None, strict_unit=True):
    """§1: cancelled orders over every order placed in the period, whatever its status."""
    if _line_filtered(filters):
        return None
    every = _orders(db, period, filters, linked, statuses=None)
    if every is None or every.empty:
        return None
    return float((every["status"] == "cancelled").sum() / every["order_id"].nunique() * 100)


def avg_order_value(db, period, filters, linked, m=None, strict_unit=True):
    """§3: revenue / number of valid orders, in whole đồng (half up). §6 Sửa xe (public rulebook): over the tickets
    with money, warranty tickets left out (N42)."""
    if _line_filtered(filters):
        return None
    o = _orders(db, period, filters, linked)
    if o is not None and "is_warranty" in o.columns:
        o = o[o["is_warranty"].ne(True)]
    if o is None or o.empty or not o["revenue_ok"].all():
        return None
    return money(float(o["revenue"].sum()) / o["order_id"].nunique())


def quantity(db, period, filters, linked, m: Measure | None = None, strict_unit=True):
    """§3: quantity in base units. "Bao nhiêu <đơn vị>" counts the products whose base unit is that unit; a product
    asked in a unit that is not its base unit has no rule here, so None. With `strict_unit` False (a percent change,
    where the unit cancels out) the base units are compared as they are."""
    ln = _lines(db, period, filters, linked, items_only=True)
    if ln is None:
        return None
    if m is not None and m.unit and strict_unit and linking.units(db):  # a shop with no unit: "chiếc" only counts
        unit = linking.norm(m.unit)
        if unit not in linking.units(db):  # N34: no unit of this shop ("ly ta", a particle read as a unit), not 0
            return None
        if "base_unit" not in ln.columns or ln["base_unit"].isna().any():
            return None
        if any(f.field == "product" for f in filters):
            if (ln["base_unit"] != unit).any():
                return None
        else:
            ln = ln[ln["base_unit"] == unit]
    if "base_qty" not in ln.columns or ln["base_qty"].isna().any():  # a mapping without base quantities (05/11)
        return None
    q = float(ln["base_qty"].sum())
    return int(q) if q.is_integer() else q


def customer_count(db, period, filters, linked, m=None, strict_unit=True):
    """§1 "khách đã mua": customers with at least one valid order in the period; walk-ins are not customers (§3)."""
    if _line_filtered(filters):
        ln = _lines(db, period, filters, linked)
        return None if ln is None or "customer_key" not in ln.columns else int(ln["customer_key"].dropna().nunique())
    o = _orders(db, period, filters, linked)
    return None if o is None or "customer_key" not in o.columns else int(o["customer_key"].dropna().nunique())


def _line_profit(ln: pd.DataFrame) -> pd.Series | None:
    """§5 "lãi gộp" of each line: its amount − quantity × the cost written on the sale line (per unit sold), never a
    cost worked out from receipts or lots. Lines that are not items (a service fee) cost nothing; an item line with no
    cost has no profit to tell: None."""
    if "unit_cost" not in ln.columns or ln["line_amount"].isna().any():
        return None
    item = ln["is_item"].ne(False) if "is_item" in ln.columns else pd.Series(True, index=ln.index)
    if ln.loc[item, "unit_cost"].isna().any() or ln.loc[item, "qty"].isna().any():
        return None
    return ln["line_amount"] - (ln["qty"] * ln["unit_cost"]).where(item, 0.0)


def gross_profit(db, period, filters, linked, m=None, strict_unit=True):
    """§5: revenue (§1, fee lines included) − cost of the goods sold, over the period's valid orders."""
    ln = _lines(db, period, filters, linked)
    profit = None if ln is None else _line_profit(ln)
    return None if profit is None else money(float(profit.sum()))


def net_profit(db, period, filters, linked, m=None, strict_unit=True):
    """§5 "lãi ròng một tháng": gross profit of the period − every expense dated in it (repairs, equipment too)."""
    expenses = db.table("expenses")
    if filters or expenses is None or expenses["amount"].isna().any() or expenses["expense_date"].isna().any():
        return None
    day = pd.to_datetime(expenses["expense_date"]).dt.date
    gp = gross_profit(db, period, filters, linked)
    spent = expenses.loc[(day >= period.start) & (day <= period.end), "amount"].sum()
    return None if gp is None else money(gp - float(spent))


# ---------------------------------------------------------------- industry figures of §6 (N44, public rulebook)
def _tickets(db, period, filters, linked) -> pd.DataFrame | None:
    """A repair shop's tickets of the period (each row of its ledger one ticket, warranty tickets included, §6 Sửa
    xe "lượt xe, phiếu"); None for a shop that is no repair ledger (no vehicle plates)."""
    o = F.orders(db)
    if o is None or "vehicle_plate" not in o.columns or _line_filtered(filters):
        return None
    return _orders(db, period, filters, linked)


def _paid(t: pd.DataFrame) -> pd.DataFrame:
    """The tickets with money: warranty tickets left out (§6 Sửa xe)."""
    return t[t["is_warranty"].ne(True)] if "is_warranty" in t.columns else t


def ticket_count(db, period, filters, linked, m=None, strict_unit=True):
    t = _tickets(db, period, filters, linked)
    return None if t is None else int(len(t))


def avg_ticket_value(db, period, filters, linked, m=None, strict_unit=True):
    """§6 Sửa xe: "tiền trung bình một phiếu chia cho số phiếu có thu tiền (không tính phiếu bảo hành)"."""
    t = _tickets(db, period, filters, linked)
    if t is None or not t["revenue_ok"].all():
        return None
    paid = _paid(t)
    return None if paid.empty else money(float(paid["revenue"].sum()) / len(paid))


def vehicle_count(db, period, filters, linked, m=None, strict_unit=True):
    """§6 Sửa xe: "số chiếc xe mang tới = số biển số khác nhau, tính cả xe chỉ tới bảo hành"."""
    t = _tickets(db, period, filters, linked)
    if t is None or t["vehicle_plate"].isna().any():
        return None
    return int(t["vehicle_plate"].map(lambda v: linking.norm(v)).nunique())


def _phone_visits(db, period, filters, linked) -> pd.DataFrame | None:
    """A phone shop's warranty visits received in the period (§6 Cửa hàng điện thoại "Bảo hành": "lượt bảo hành có
    ngày nhận trong quý … lượt bảo hành của máy bán từ quý trước vẫn tính"); a line filter keeps the visits of that line
    (the book writes the line, "Máy ghi dòng máy")."""
    v = db.table("warranty_visits")
    if v is None or v["visit_time"].isna().any():
        return None
    day = v["visit_time"].dt.date
    v = v[(day >= period.start) & (day <= period.end)]
    for f in filters:
        if f.field != "product_line" or f.op not in ("eq", "in"):
            return None
        keys = {linking.norm(str(linked.get(str(x), x))) for x in F._values(f)}
        v = v[v["product_line"].map(lambda x: linking.norm(str(x))).isin(keys)]
    return v


def phones_sold(db, period) -> int | None:
    """Phones sold in the period, cancelled and returned orders left out (§6 "số máy bán trong quý"): the quantity of
    the lines that are no accessory (the shop's kind of goods); None when a line's kind is unknown."""
    ln = _lines(db, period, [], {}, items_only=True)
    if ln is None or "category" not in ln.columns or ln["category"].isna().any() or ln["base_qty"].isna().any():
        return None
    phones = ln[~ln["category"].map(lambda c: linking.norm(str(c))).eq("phu kien")]
    return int(phones["base_qty"].sum())


def warranty_count(db, period, filters, linked, m=None, strict_unit=True):
    if db.table("warranty_visits") is not None and not any(f.field != "product_line" for f in filters):
        v = _phone_visits(db, period, filters, linked)
        return None if v is None else int(len(v))
    t = _tickets(db, period, filters, linked)
    return None if t is None or "is_warranty" not in t.columns else int(t["is_warranty"].eq(True).sum())


def warranty_rate(db, period, filters, linked, m=None, strict_unit=True):
    """§6 Sửa xe: "tỉ lệ bảo hành = số phiếu bảo hành có ngày trong kỳ / số phiếu có thu tiền trong cùng kỳ"; §6 Cửa
    hàng điện thoại: "số lượt bảo hành có ngày nhận trong quý, chia cho số máy bán trong quý (bỏ đơn huỷ, đơn trả)"."""
    if db.table("warranty_visits") is not None:
        v = None if filters else _phone_visits(db, period, filters, linked)
        sold = phones_sold(db, period) if v is not None else None
        return None if not sold else round(100.0 * len(v) / sold, 2)
    t = _tickets(db, period, filters, linked)
    if t is None or "is_warranty" not in t.columns:
        return None
    paid = len(_paid(t))
    return None if not paid else round(100.0 * int(t["is_warranty"].eq(True).sum()) / paid, 2)


ORDER_AMOUNTS = {"voucher_discount": "voucher_discount", "points_discount": "points_discount",
                 "shipping_fee_total": "shipping_fee", "trade_in_amount": "trade_in_amount",
                 "amount_due_total": "total_due"}  # §6 điện thoại "khách phải trả": after discount and trade-in


def order_amount(db, period, filters, linked, m=None, strict_unit=True):
    """§6 Mẹ và bé (voucher, points, shipping) and Điện thoại (trade-in): positive amounts summed by the order's day,
    over the orders neither cancelled nor returned. None when the shop records no such column."""
    if m is None or _line_filtered(filters):
        return None
    col = ORDER_AMOUNTS[m.metric]
    raw = db.table("orders")
    if raw is None or col not in raw.columns or raw[col].notna().sum() == 0:
        return None
    o = _orders(db, period, filters, linked)
    if o is None:
        return None
    amounts = o["order_id"].map(raw.set_index("order_id")[col])
    return money(float(amounts.fillna(0).abs().sum()))


def avg_amount_due(db, period, filters, linked, m=None, strict_unit=True):
    """§6 Điện thoại "Thu máy cũ": what the customers have to pay (after the discount and the trade-in) over the
    period's orders neither cancelled nor returned, per order; a money average is money, in whole đồng (§3, §9).
    None when an order of the period has no amount (the average would not be the shop's)."""
    raw = db.table("orders")
    if _line_filtered(filters) or raw is None or "total_due" not in raw.columns:
        return None
    o = _orders(db, period, filters, linked)
    if o is None or o.empty:
        return None
    due = o["order_id"].map(raw.drop_duplicates("order_id").set_index("order_id")["total_due"])
    if due.isna().any():
        return None
    return money(float(due.abs().sum()) / o["order_id"].nunique())


def trade_in_order_count(db, period, filters, linked, m=None, strict_unit=True):
    """§6 Điện thoại "Thu máy cũ": the period's orders neither cancelled nor returned (§1) with an old phone taken
    in (a trade-in amount above 0). None when the shop records no trade-in."""
    raw = db.table("orders")
    if _line_filtered(filters) or raw is None or "trade_in_amount" not in raw.columns \
            or raw["trade_in_amount"].notna().sum() == 0:
        return None
    o = _orders(db, period, filters, linked)
    if o is None:
        return None
    amounts = o["order_id"].map(raw.drop_duplicates("order_id").set_index("order_id")["trade_in_amount"])
    return int(o.loc[amounts.fillna(0).abs().gt(0).to_numpy(), "order_id"].nunique())


def new_customer_count(db, period, filters, linked, m=None, strict_unit=True):
    """§6 Mẹ và bé: "khách thành viên mới trong tháng: số khách có Ngày đăng ký trong tháng đó, kể cả khách chưa mua
    lần nào" — the member list, not the orders."""
    c = db.table("customers")
    if filters or c is None or "registered_date" not in c.columns or c["registered_date"].isna().all():
        return None
    day = pd.to_datetime(c["registered_date"], errors="coerce").dt.date
    return int(c.loc[(day >= period.start) & (day <= period.end), "customer_key"].nunique())


def commissions(db, period, filters, linked) -> pd.Series | None:
    """Each person's commission (a public repair shop's README: "Hoa hồng (%): phần trăm hoa hồng của thợ, tính trên
    tổng Tiền các phiếu thợ làm trong tháng"): the staff list's percent × the money of the orders, tickets, the person
    did in the period, in whole đồng. Within one month only: the base is a month's money, and a longer period rounded
    once may differ from its months rounded one by one. None when someone of the period has no percent."""
    staff = db.table("employees")
    if (staff is None or "commission_pct" not in staff.columns or staff["commission_pct"].isna().any()
            or (period.start.year, period.start.month) != (period.end.year, period.end.month) or _line_filtered(filters)):
        return None
    o = _orders(db, period, filters, linked)
    if o is None or "employee" not in o.columns or o["employee"].isna().any() or not o["revenue_ok"].all():
        return None
    pct: dict[str, float] = {}
    for col in ("employee_key", "employee_name"):
        if col in staff.columns:
            pct.update({str(k): float(v) for k, v in zip(staff[col], staff["commission_pct"]) if pd.notna(k)})
    base = o.groupby(o["employee"].astype(str))["revenue"].sum()
    if not set(base.index) <= set(pct):
        return None
    return pd.Series({e: money(float(v) * pct[e] / 100) for e, v in base.items()}, dtype="int64")


def commission(db, period, filters, linked, m=None, strict_unit=True):
    """The commission of the people the filters keep (one person: an employee filter), summed."""
    per = commissions(db, period, filters, linked)
    return None if per is None else int(per.sum())


R_TICKETS = R_TODAY + ("§6.sua_xe.luot_xe_phieu", "§6.p_luat_rieng_cua_tung_nganh_dung", "§1.don_thuoc_ky_nao")
R_ORDER_AMOUNT = R_VALID + ("§6.me_va_be.tien_giam_voucher_tien_giam_nho_dung_diem_phi_sh",
                            "§6.p_luat_rieng_cua_tung_nganh_dung")
R_METRIC.update({
    "work_days": R_VALID + ("§3.nhan_vien_tho_cham_chi_nhat",),
    "days_with_purchase": R_VALID + ("§3.khach_trung_thanh_nhat", "§3.xac_dinh_khach"),
    "ticket_count": R_TICKETS, "avg_ticket_value": R_TICKETS + ("§6.sua_xe.bao_hanh",),
    "vehicle_count": R_TICKETS + ("§6.sua_xe.dong_xe_bien_so",),
    "warranty_count": R_TICKETS + ("§6.sua_xe.bao_hanh", "§6.cua_hang_dien_thoai.bao_hanh"),
    "warranty_rate": R_TICKETS + ("§6.sua_xe.bao_hanh", "§6.cua_hang_dien_thoai.bao_hanh"),
    "voucher_discount": R_ORDER_AMOUNT,
    "points_discount": R_ORDER_AMOUNT, "shipping_fee_total": R_ORDER_AMOUNT,
    "trade_in_amount": R_VALID + ("§6.cua_hang_dien_thoai.thu_may_cu", "§6.p_luat_rieng_cua_tung_nganh_dung"),
    "amount_due_total": R_VALID + ("§6.cua_hang_dien_thoai.thu_may_cu", "§6.p_luat_rieng_cua_tung_nganh_dung"),
    "trade_in_order_count": R_VALID + ("§1.so_don", "§6.cua_hang_dien_thoai.thu_may_cu",
                                       "§6.p_luat_rieng_cua_tung_nganh_dung"),
    "avg_amount_due": R_VALID + ("§1.so_don", "§3.gia_tri_trung_binh_mot_don", "§6.cua_hang_dien_thoai.thu_may_cu",
                                 "§6.p_luat_rieng_cua_tung_nganh_dung"),
    "new_customer_count": R_TODAY + ("§6.me_va_be.khach_thanh_vien_moi_trong_thang", "§6.p_luat_rieng_cua_tung_nganh_dung"),
    "commission": R_REVENUE,  # the percent and its base are the README's, not a rulebook row
})
REQ_TICKETS = REQ_ORDERS + ("orders.vehicle_plate",)
REQ_METRIC.update({
    "commission": REQ_ORDERS + ("orders.employee", "employees.commission_pct"),
    "ticket_count": REQ_TICKETS, "avg_ticket_value": REQ_TICKETS + ("orders.goods_amount",),
    "vehicle_count": REQ_TICKETS, "warranty_count": REQ_TICKETS + ("orders.is_warranty",),
    "warranty_rate": REQ_TICKETS + ("orders.is_warranty",), "voucher_discount": REQ_ORDERS + ("orders.voucher_discount",),
    "points_discount": REQ_ORDERS + ("orders.points_discount",),
    "shipping_fee_total": REQ_ORDERS + ("orders.shipping_fee",), "trade_in_amount": REQ_ORDERS + ("orders.trade_in_amount",),
    "amount_due_total": REQ_ORDERS + ("orders.total_due",),
    "avg_amount_due": REQ_ORDERS + ("orders.total_due",),
    "trade_in_order_count": REQ_ORDERS + ("orders.trade_in_amount",),
    "new_customer_count": ("customers.registered_date",),
})

MEASURES: dict[str, Callable] = {
    "revenue": revenue, "order_count": order_count, "cancel_count": cancel_count, "cancel_rate": cancel_rate,
    "avg_order_value": avg_order_value, "quantity": quantity, "customer_count": customer_count,
    "gross_profit": gross_profit, "net_profit": net_profit,
    "ticket_count": ticket_count, "avg_ticket_value": avg_ticket_value, "vehicle_count": vehicle_count,
    "warranty_count": warranty_count, "warranty_rate": warranty_rate, "commission": commission,
    "new_customer_count": new_customer_count, "avg_amount_due": avg_amount_due,
    "trade_in_order_count": trade_in_order_count,
    **{name: order_amount for name in ORDER_AMOUNTS},
}


# §2 "trung bình mỗi ngày thứ X của kỳ: chia cho số ngày thứ X trong kỳ, kể cả ngày không có đơn, phiếu": the
# figures that add up day by day; a money average is money, in whole đồng (§9 "Làm tròn")
PER_DAY = frozenset({"revenue", "order_count", "cancel_count", "quantity", "gross_profit", "ticket_count",
                     "warranty_count", "voucher_discount", "points_discount", "shipping_fee_total", "trade_in_amount"})
MONEY = frozenset({"revenue", "gross_profit", "voucher_discount", "points_discount", "shipping_fee_total",
                   "trade_in_amount"})
R_PER_DAY = ("§2.trung_binh_moi_ngay_thu_x_cua_ky",)


def calendar_days(period: ResolvedPeriod, filters: list[Filter]) -> int | None:
    """Days of the period an average per day is over: every day, or the days of the weekdays a weekday filter names,
    days without orders included (§2)."""
    wd = [f for f in filters if f.field == "weekday"]
    if len(wd) > 1 or (wd and wd[0].op not in ("eq", "in")):
        return None
    names = {str(v) for v in F._values(wd[0])} if wd else None
    n = (period.end - period.start).days + 1
    return sum(1 for i in range(n)
               if names is None or F.WEEKDAYS[(period.start + timedelta(days=i)).weekday()] in names)


def figure(db: CanonicalDB, m: Measure, period: ResolvedPeriod | None, plan: ResolvedPlan,
           filters: list[Filter] | None = None, strict_unit: bool = True):
    """One measure over one period (the measure's own filters unless `filters` is given); None when not exact.
    An average per day (§2) is the period's total over its calendar days: avg_per_weekday needs the weekday."""
    fn = MEASURES.get(m.metric)
    if fn is None or period is None or m.unit_split:
        return None
    filters = m.filters if filters is None else filters
    if m.aggregate == "total":
        return fn(db, period, filters, plan.linked, m, strict_unit)
    if m.metric not in PER_DAY or (m.aggregate == "avg_per_weekday" and not any(f.field == "weekday" for f in filters)):
        return None
    days, total = calendar_days(period, filters), fn(db, period, filters, plan.linked, m, strict_unit)
    if not days or total is None:
        return None
    return money(total / days) if m.metric in MONEY else total / days


def measure_requires(db: CanonicalDB, metric: str) -> tuple[str, ...]:
    """The columns a figure read in this shop: a phone shop's warranty figures read its warranty book (and, for the
    rate, the kind of each line), not a repair ledger's tickets."""
    if metric in ("warranty_count", "warranty_rate") and db.table("warranty_visits") is not None:
        book = ("warranty_visits.visit_time",)
        return book + (("lines.base_qty", "products.category") if metric == "warranty_rate" else ())
    return REQ_METRIC[metric]


def measure_rules(m: Measure) -> tuple[str, ...]:
    return R_METRIC[m.metric] + (R_PER_DAY if m.aggregate != "total" else ())


def _result(plan: ResolvedPlan, value, rules: tuple[str, ...], requires: tuple[str, ...], fn: str,
            answer_type: str | None = None) -> ExecResult | None:
    answer_type = answer_type or expected_answer_type(plan.plan)
    if value is None or answer_type is None:
        return None
    p = plan.plan
    measures = list(p.measures) + ([p.share_of] if p.share_of else [])
    filters = [f for m in measures for f in m.filters] + list((p.compare.filters or []) if p.compare else [])
    rules = tuple(rules) + tuple(r for f in filters for r in FILTER_RULES.get(f.field, ()))
    if any(isinstance(f.value, (str, list)) and f.field not in CODED_VALUES for f in filters):
        rules += R_NAMES
    for entity in (p.rank.entity if p.rank else None, p.threshold.entity if p.threshold else None):
        rules += ENTITY_RULES.get(entity, ())
    return ExecResult(value=value, answer_type=answer_type, source="D1", function=f"sales.{fn}",
                      rule_ids=sorted(set(rules)), requires=sorted(set(requires) | set(F.filter_columns(filters))))



# ---------------------------------------------------------------- value, compare, share, trend, series
def value_of(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """One figure, or several in the order the question asks ("lần lượt", "mỗi bên"): a list."""
    ms = plan.plan.measures
    values = [figure(db, m, plan.period, plan) for m in ms]
    if not ms or any(v is None for v in values):
        return None
    rules = sum((measure_rules(m) for m in ms), ())
    requires = sum((measure_requires(db, m.metric) for m in ms), ())
    return _result(plan, values[0] if len(values) == 1 else values, rules, requires, "value_of")


def compare(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """The asked figure against the compared one (§1): the previous / same / given period, or the same period under
    the compared filters (ca chiều vs ca sáng: the base is ca sáng). pct_change = (a − b) / b × 100; diff = a − b."""
    p, c = plan.plan, plan.plan.compare
    if len(p.measures) != 1 or c.output == "which_more":
        return None
    m = p.measures[0]
    strict = c.output != "pct_change"
    a = figure(db, m, plan.period, plan, strict_unit=strict)
    if c.kind == "filter":
        replaced = {f.field for f in c.filters}
        b = figure(db, m, plan.period, plan, [f for f in m.filters if f.field not in replaced] + list(c.filters), strict)
    else:
        b = figure(db, m, plan.compare_period, plan, strict_unit=strict)
    if a is None or b is None:
        return None
    if c.output == "pct_change":
        value = None if b == 0 else (a - b) / b * 100
    else:
        value = a - b
    rules = measure_rules(m) + compare_rules(p)
    return _result(plan, value, rules, measure_requires(db, m.metric), "compare")


def share(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """Part over whole, in percent: the whole is `share_of`, else the same metric for the whole shop (§1: walk-in
    orders and fee lines included)."""
    p = plan.plan
    if len(p.measures) != 1:
        return None
    m = p.measures[0]
    whole = p.share_of or Measure(metric=m.metric)
    part, total = figure(db, m, plan.period, plan), figure(db, whole, plan.period, plan)
    if part is None or not total:
        return None
    rules = measure_rules(m) + measure_rules(whole)
    return _result(plan, part / total * 100, rules, measure_requires(db, m.metric), "share")


def _series_values(plan: ResolvedPlan, db: CanonicalDB) -> list | None:
    p = plan.plan
    if len(p.measures) != 1 or not plan.series:
        return None
    values = [figure(db, p.measures[0], s, plan) for s in plan.series]
    return None if any(v is None for v in values) else values


def trend(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """True when each month is above the one before. Every train trend question asks about a rise ("tăng liên tục",
    "tháng sau luôn cao hơn tháng trước"); the contract has no way to ask about a fall (docs/HAN_CHE N11)."""
    values = _series_values(plan, db)
    if values is None or len(values) < 2:
        return None
    rising = all(b > a for a, b in zip(values, values[1:]))
    m = plan.plan.measures[0]
    return _result(plan, rising, measure_rules(m), measure_requires(db, m.metric), "trend")


def series(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    values = _series_values(plan, db)
    m = plan.plan.measures[0] if plan.plan.measures else None
    if values is None or m is None:
        return None
    return _result(plan, values, measure_rules(m), measure_requires(db, m.metric), "series")


# ---------------------------------------------------------------- rank
def _first_name(keys: pd.Series, names: pd.Series) -> dict[str, str]:
    """A name for each key: the most frequent one in the data (§9 accepts every spelling the file has, or the code)."""
    frame = pd.DataFrame({"k": keys.astype(str), "n": names}).dropna()
    if frame.empty:
        return {}
    return frame.groupby("k")["n"].agg(lambda s: s.value_counts().index[0]).to_dict()


def _ordered(totals: pd.Series, k: int | None) -> list:
    """Keys by value descending, ties by key ascending (§9 "Bằng nhau"), the first k."""
    frame = totals.rename("v").reset_index()
    frame.columns = ["key", "v"]
    frame = frame.sort_values(["v", "key"], ascending=[False, True], kind="mergesort")
    return frame["key"].head(k if k is not None else len(frame)).tolist()


TIE = "tie"  # ExecResult.notes: the ranking the answer reads has equal values (verify → Signals.ranking_clear)


def _tied(totals: pd.Series, k: int | None, order_matters: bool = True) -> bool:
    """Equal values where the answer depends on the tie rule: at the top-k boundary (which ones are in), or inside
    the top k when the answer is an ordered list. No train rank question has one (281 answered right, 05/11), while a
    month's customers by order count tie at the top 39% of the time: the question generator leaves ties out, so a tie
    in our figures means they differ from the generator's somewhere (N25)."""
    v = sorted((round(float(x), 6) for x in totals.values), reverse=True)
    k = len(v) if k is None else min(k, len(v))
    if k < len(v) and k > 0 and v[k - 1] == v[k]:
        return True
    return order_matters and len(set(v[:k])) < k


def rank(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """Products, customers, employees, days or months ranked by a sales metric; ties by code ascending (§9)."""
    p, r = plan.plan, plan.plan.rank
    if r.order != "desc" or (r.with_values and r.entity != "employee") or plan.period is None:
        return None
    if r.min_orders and (r.by, r.entity) != ("avg_order_value", "customer"):
        return None
    if (r.by, r.entity) == ("warranty_count", "product_line"):  # §6 điện thoại: the book writes each visit's line
        v = _phone_visits(db, plan.period, [], plan.linked)
        if v is None or v.empty or r.with_values or (p.measures and p.measures[0].filters):
            return None
        totals = v.groupby("product_line").size()
        keys = _ordered(totals, r.k)
        out = _result(plan, keys[0] if r.k == 1 else keys, R_TIES + R_METRIC["warranty_count"],
                      ("warranty_visits.visit_time", "warranty_visits.product_line"), "rank")
        if out is not None and _tied(totals, r.k):
            out.notes.append(TIE)
        return out
    filters = p.measures[0].filters if p.measures else []
    if r.entity in ("product", "product_line", "brand"):
        ln = _lines(db, plan.period, filters, plan.linked, items_only=True)
        if ln is None or ln.empty:
            return None
        group = {"product": "product_key", "product_line": "product_line", "brand": "brand"}[r.entity]
        if group not in ln.columns or ln[group].isna().any():
            return None  # §6 điện thoại "dòng máy, hãng": every line's, or no ranking
        if r.by == "gross_profit":  # §3 "hàng lời nhất": by total gross profit (§5)
            profit = _line_profit(ln)
            ln, col = (None if profit is None else ln.assign(_profit=profit)), "_profit"
        else:
            col = {"quantity": "base_qty", "revenue": "line_amount", "order_presence": "order_id"}.get(r.by)
        if ln is None or col is None or col not in ln.columns or ln[col].isna().any():
            return None
        if r.by == "order_presence":  # §3 "mặt hàng được ưa chuộng nhất: có mặt trong nhiều đơn nhất"
            totals = ln.groupby(group)["order_id"].nunique()
        else:
            totals = ln.groupby(group)[col].sum()
        keys = _ordered(totals, r.k)
        if r.entity == "product":
            names = _first_name(F.lines(db)["product_key"], F.lines(db)["product_name"])
            labels = [names.get(k, k) for k in keys]
        else:
            labels = keys
    else:
        if _line_filtered(filters):
            return None
        o = _orders(db, plan.period, filters, plan.linked)
        if o is None or o.empty or not o["revenue_ok"].all():
            return None
        if r.entity in ("day", "month"):
            key = o["day"].map(lambda d: d.isoformat() if r.entity == "day" else d.strftime("%Y-%m"))
        elif r.entity == "customer" and "customer_key" in o.columns:
            key = o["customer_key"]  # §3: walk-in orders have no key and are not ranked
        elif r.entity == "employee" and "employee" in o.columns:
            key = o["employee"]
        elif r.entity == "vehicle_model" and "vehicle_model" in o.columns:  # §6 Sửa xe: a line, all its spellings
            key = linking.ledger_lines(F.orders(db)["vehicle_model"]).loc[o.index]
            if (key.isna() & o["vehicle_model"].notna()).any():
                return None
        elif r.entity == "hour" and "has_time" in o.columns and o["has_time"].eq(True).all():
            key = o["order_time"].dt.hour.map(lambda h: f"{h:02d}")  # §3 "giờ cao điểm": the hour that starts it
        else:
            return None
        if (r.by, r.entity) == ("cancel_count", "customer"):  # §3 "khách hay đổi ý nhất: nhiều đơn huỷ nhất"
            o = _orders(db, plan.period, filters, plan.linked, statuses=("cancelled",))
            if o is None or o.empty or "customer_key" not in o.columns:
                return None
            key = o["customer_key"]
        o = o.assign(_key=key.astype("string")).dropna(subset=["_key"])
        if o.empty:
            return None
        tickets = "vehicle_plate" in o.columns  # a repair shop: each order is a ticket (§6 Sửa xe)
        if r.by == "revenue":
            totals = o.groupby("_key")["revenue"].sum()
        elif r.by in ("order_count", "cancel_count") or (r.by == "ticket_count" and tickets):
            totals = o.groupby("_key")["order_id"].nunique()  # §6 "thợ làm nhiều nhất": warranty tickets included
        elif (r.by, r.entity) == ("avg_order_value", "customer"):  # §3 "khách sộp nhất", only from min_orders orders
            g = o.groupby("_key")
            n = g["order_id"].nunique()
            totals = (g["revenue"].sum() / n)[n >= (r.min_orders or 1)]
            if totals.empty:
                return None
        elif (r.by, r.entity) in (("work_days", "employee"), ("days_with_purchase", "customer")):
            totals = o.groupby("_key")["day"].nunique()  # §3 "chăm chỉ", "trung thành": days with an order
        elif (r.by, r.entity) == ("commission", "employee"):
            totals = commissions(db, plan.period, filters, plan.linked)
            if totals is None or totals.empty:
                return None
        else:
            return None
        keys = _ordered(totals, r.k)
        if r.entity == "customer":
            every = F.orders(db)
            names = _first_name(every["customer_key"], every.get("customer_name", every["customer_key"]))
            customers = db.table("customers")
            if customers is not None and "customer_name" in customers.columns:
                names = {**names, **_first_name(customers["customer_key"], customers["customer_name"])}
            labels = [names.get(k, k) for k in keys]
        elif r.entity == "hour":
            labels = [int(k) for k in keys]  # §3 "giờ cao điểm … type number"
        else:
            labels = keys
    if r.with_values:  # §9 table: the name first, then the measure; rows in any order
        figures = [money(float(totals[k])) if r.by in MONEY | {"commission"} else int(totals[k]) for k in keys]
        value = {"columns": ["nhan_vien", TABLE_COLUMN.get(r.by, r.by)],
                 "rows": [[label, v] for label, v in zip(labels, figures)]}
    else:
        value = labels[0] if r.k == 1 else labels
    rules = R_TIES + R_METRIC.get(r.by, ())
    if r.by == "quantity":
        rules += ("§3.ban_chay",)
    if r.entity == "employee" and r.by == "revenue":
        rules += ("§3.nhan_vien_ban_gioi_nhat",)
    if r.entity == "employee" and r.by in ("order_count", "ticket_count") and "vehicle_plate" in o.columns:
        rules += R_TICKETS + ("§6.sua_xe.tho_lam_nhieu_nhat",)
    if r.entity == "vehicle_model":
        rules += R_TICKETS + ("§6.sua_xe.dong_xe_bien_so",)
    rules += RANK_TERMS.get((r.by, r.entity), ())
    out = _result(plan, value, rules, REQ_METRIC.get(r.by, REQ_ORDERS), "rank")
    if out is not None and _tied(totals, r.k, order_matters=not r.with_values):
        out.notes.append(TIE)
    return out


TABLE_COLUMN = {"revenue": "doanh_thu", "order_count": "so_don", "ticket_count": "so_luot_xe", "work_days": "so_ngay_lam",
                "commission": "hoa_hong"}
# §3 terms of the public rulebook a ranking implements (cited, so the term gate knows the function reads the term)
RANK_TERMS = {("avg_order_value", "customer"): ("§3.khach_sop_nhat",),
              ("cancel_count", "customer"): ("§3.khach_hay_doi_y_nhat",),
              ("order_presence", "product"): ("§3.mat_hang_duoc_ua_chuong_nhat",),
              ("order_count", "hour"): ("§3.gio_cao_diem",),
              ("order_count", "day"): ("§3.ngay_dat_khach_nhat",)}  # N109: "ngày có nhiều đơn nhất trong kỳ"


# ---------------------------------------------------------------- count over a threshold, unsold products
OPS = {"gte": operator.ge, "gt": operator.gt, "lte": operator.le, "lt": operator.lt, "eq": operator.eq}


def count_where(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """How many orders / days / customers / products pass a bound (§2: "từ N trở lên" includes N, "quá N" does
    not); as a share of the customers who bought (§1) when asked in percent."""
    p, t = plan.plan, plan.plan.threshold
    filters = p.measures[0].filters if p.measures else []
    if plan.period is None or _line_filtered(filters):
        return None
    o = _orders(db, plan.period, filters, plan.linked)
    if o is None:
        return None
    cmp = OPS[t.op]
    if t.entity in ("product", "customer", "vehicle", "employee") and cmp(0, t.value) and not cmp(1, t.value):
        return None  # K1: "không bán được lần nào" as order_presence = 0 asks for what the period's rows never show
    if t.entity == "order" and t.metric == "revenue":
        if not o["revenue_ok"].all():
            return None
        per = o.groupby("order_id")["revenue"].sum()
    elif t.entity == "day" and t.metric == "revenue":
        if t.op not in ("gte", "gt") or t.value <= 0 or not o["revenue_ok"].all():
            return None  # a day without orders has revenue 0: only bounds above 0 can skip such days
        per = o.groupby("day")["revenue"].sum()
    elif t.entity == "customer" and t.metric == "order_count":
        if "customer_key" not in o.columns:
            return None  # a shop that does not record its customers
        per = o.dropna(subset=["customer_key"]).groupby("customer_key")["order_id"].nunique()
    elif t.entity == "product" and t.metric in ("order_presence", "order_count"):
        ln = _lines(db, plan.period, filters, plan.linked, items_only=True)
        if ln is None:
            return None
        per = ln.groupby("product_key")["order_id"].nunique()
    elif t.entity == "vehicle" and t.metric in ("ticket_count", "order_count") and "vehicle_plate" in o.columns:
        paid = _paid(o)  # §6 Sửa xe "xe tới nhiều lần": a vehicle by its plate, only tickets with money are a visit
        if paid["vehicle_plate"].isna().any():
            return None
        per = paid.groupby(paid["vehicle_plate"].map(linking.norm))["order_id"].nunique()
    else:
        return None
    hits = int(cmp(per, t.value).sum())
    if t.as_share:
        if t.entity != "customer" or per.empty:
            return None
        value = hits / len(per) * 100
    else:
        value = hits
    rules = ("§2.qua_n_hon_n_tren_n_duoi_n",) + R_VALID + R_METRIC.get(t.metric, ())
    if t.metric == "order_count" or t.entity == "order":
        rules += ("§1.so_don",)
    if t.entity == "vehicle":
        rules += R_TICKETS + ("§6.sua_xe.khach_quen_xe_toi_nhieu_lan", "§6.sua_xe.dong_xe_bien_so")
    return _result(plan, value, rules, REQ_METRIC.get(t.metric, REQ_ORDERS), "count_where")


def unsold(plan: ResolvedPlan, db: CanonicalDB) -> ExecResult | None:
    """§5 "hàng ế": products sold before the period (valid orders) and in no valid order of the period."""
    p, ls = plan.plan, plan.plan.list_spec
    if plan.period is None or ls.entity != "product" or any(m.filters for m in p.measures):
        return None
    ln = F.lines(db)
    if ln is None or F.unknown_status(ln[ln["day"] <= plan.period.end]):
        return None
    items = ln[F.valid(ln) & (ln["is_item"].ne(False) if "is_item" in ln.columns else True)]
    before = set(items.loc[items["day"] < plan.period.start, "product_key"])
    during = set(items.loc[F.in_period(items, plan.period), "product_key"])
    keys = sorted(before - during)
    if ls.count:
        value = len(keys)
    else:
        names = _first_name(ln["product_key"], ln["product_name"])
        value = [names.get(k, k) for k in keys]
        if not value:
            return None
    return _result(plan, value, R_UNSOLD + R_TIES, REQ_METRIC["order_count"] + ("lines.product_key",), "unsold")


# ---------------------------------------------------------------- registry
def _register(intent: str, names, fn, entity: str = "", rules: tuple[str, ...] = ()) -> None:
    for name in names:
        metric(intent, name, requires=REQ_METRIC.get(name, REQ_ORDERS),
               rules=tuple(sorted(set(R_METRIC.get(name, ()) + rules))), entity=entity,
               filters=tuple(sorted(F.FILTERS)))(fn)


_register("value", MEASURES, value_of)
_register("compare", MEASURES, compare, rules=R_COMPARE)
_register("share", ("revenue", "order_count", "quantity", "customer_count", "trade_in_order_count"), share)
_register("trend", ("revenue", "order_count", "avg_order_value", "quantity", "cancel_count"), trend)
_register("series", ("revenue", "order_count", "avg_order_value", "quantity", "cancel_count"), series)
_register("rank", ("quantity", "revenue", "gross_profit"), rank, entity="product", rules=R_RANK)
for _entity in ("customer", "employee", "day", "month"):
    _register("rank", ("revenue", "order_count"), rank, entity=_entity, rules=R_RANK)
_register("rank", ("ticket_count", "work_days", "commission"), rank, entity="employee", rules=R_RANK)
_register("rank", ("days_with_purchase", "avg_order_value", "cancel_count"), rank, entity="customer", rules=R_RANK)
_register("rank", ("order_presence",), rank, entity="product", rules=R_RANK)
_register("rank", ("order_count",), rank, entity="hour", rules=R_RANK)

# rule ids a function cites only when the plan uses them (a filter, an average per day, a term): train's rulebook has
# none of these rows, so they cannot sit in every result; they must still be checked against the split's rulebook
# (pipeline.rule_ids), or [V] reads them as missing and every such answer abstains (caught 06/11 before any run)
CONDITIONAL_RULES = tuple(sorted(set(
    R_PER_DAY + tuple(r for rs in FILTER_RULES.values() for r in rs) + tuple(r for rs in RANK_TERMS.values() for r in rs)
    + R_NAMES + tuple(r for rs in ENTITY_RULES.values() for r in rs) + R_COMPARE + R_RANK + R_COUNT
    + R_TICKETS + ("§6.sua_xe.tho_lam_nhieu_nhat", "§6.sua_xe.khach_quen_xe_toi_nhieu_lan", "§6.sua_xe.dong_xe_bien_so"))))
_register("rank", ("revenue", "order_count", "ticket_count"), rank, entity="vehicle_model", rules=R_RANK)
_register("rank", ("warranty_count",), rank, entity="product_line", rules=R_RANK)
for _entity in ("product_line", "brand"):  # §6 điện thoại "dòng máy, hãng"
    _register("rank", ("quantity", "revenue"), rank, entity=_entity,
              rules=R_RANK + ("§6.cua_hang_dien_thoai.dong_may_hang",))
_register("count_where", ("revenue",), count_where, entity="order", rules=R_COUNT)
_register("count_where", ("revenue",), count_where, entity="day", rules=R_COUNT)
_register("count_where", ("order_count",), count_where, entity="customer", rules=R_COUNT)
_register("count_where", ("order_presence", "order_count"), count_where, entity="product", rules=R_COUNT)
_register("count_where", ("ticket_count", "order_count"), count_where, entity="vehicle", rules=R_COUNT)
_register("list_items", ("unsold_in_period",), unsold, entity="product", rules=R_UNSOLD + R_TIES)
