"""Public rulebook §6 Cửa hàng điện thoại (06/11): "dòng máy = phần tên hàng đứng trước dung lượng …GB; tên không có
phần …GB thì dòng máy là cả tên. Hãng = chữ đầu tên hàng; máy iPhone là hãng Apple"; and the kind of goods (máy mới,
máy cũ, phụ kiện) the abbreviation sheet gives beside each full name."""
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from datamate import metrics
from datamate.contracts import CanonicalDB, ColumnMap, Mapping, QueryPlan, RawBusiness, RawTable, ResolvedPeriod, ResolvedPlan, TableMap
from datamate.mapping.build import phone_lines
from datamate.mapping.transfer import _kind_of_goods
from datamate.nlu import link_entities

NAMES = ["Xiaomi Redmi Note 14 128GB Đen", "Xiaomi Redmi Note 14 256GB Xanh", "iPhone 16 Pro Max 256GB Titan Đen",
         "Nokia 105 4G", "Cáp Type-C 1m"]


def shop() -> CanonicalDB:
    lines = pd.DataFrame({"order_id": ["1", "2", "3", "4", "5"], "product_key": NAMES, "product_name": NAMES,
                          "qty": [1.0, 2.0, 1.0, 1.0, 3.0], "base_qty": [1.0, 2.0, 1.0, 1.0, 3.0],
                          "line_amount": [5e6, 12e6, 30e6, 6e5, 3e5], "is_item": True})
    products = pd.DataFrame({"product_key": NAMES, "product_name": NAMES,
                             "category": ["máy mới", "máy mới", "máy cũ", "máy mới", "phụ kiện"]})
    o = pd.DataFrame({"order_id": ["1", "2", "3", "4", "5"], "order_time": [datetime(2026, 6, d) for d in range(1, 6)],
                      "status": "completed", "has_time": False})
    db = CanonicalDB(tables={"orders": o, "lines": lines, "products": products})
    phone_lines(db)
    return db


def test_the_line_and_brand_of_each_phone():
    p = shop().tables["products"].set_index("product_name")
    assert p.loc["Xiaomi Redmi Note 14 256GB Xanh", "product_line"] == "Xiaomi Redmi Note 14"
    assert p.loc["Nokia 105 4G", "product_line"] == "Nokia 105 4G"  # "4G" is the network, not a capacity
    assert p.loc["iPhone 16 Pro Max 256GB Titan Đen", "brand"] == "Apple"
    assert p.loc["Xiaomi Redmi Note 14 128GB Đen", "brand"] == "Xiaomi"


def run(raw):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"period": {"kind": "this_month"}, **raw}), as_of=date(2026, 6, 30),
                        period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30)))
    db = shop()
    r = metrics.execute(link_entities(plan, db), db)
    return None if r is None else r.value


def test_a_line_or_a_kind_written_as_a_product_filters_by_it():
    """"Xiaomi Redmi Note 14 bán mấy máy": both capacities, 3 phones. "máy cũ bán mấy chiếc": 1. "phụ kiện": 3."""
    q = lambda v: {"intent": "value", "measures": [{"metric": "quantity", "filters": [  # noqa: E731
        {"field": "product", "value": v}]}]}
    assert run(q("Xiaomi Redmi Note 14")) == 3
    assert run(q("máy cũ")) == 1
    assert run(q("phụ kiện")) == 3
    assert run({"intent": "value", "measures": [{"metric": "quantity", "filters": [
        {"field": "brand", "value": "Apple"}]}]}) == 1


def test_the_abbreviation_sheet_gives_the_kind_of_goods():
    frame = pd.DataFrame([("CL 9D", "Kính cường lực 9D", "phụ kiện"), ("A56 128 đen", "Samsung Galaxy A56 5G 128GB Đen",
                           "máy mới"), ("A54 128 cũ", "Samsung Galaxy A54 5G 128GB cũ 99%", "máy cũ")],
                         columns=["Ghi tắt", "Tên hàng", "Loại"])
    raw = RawBusiness(root=Path("."), readme="", tables=[RawTable(table_id="S::Ghi tắt", file="S", sheet="Ghi tắt",
                                                                  frame=frame)])
    lines = TableMap(target="lines", sources=["S::Sổ"], columns=[ColumnMap(target="order_id", source="STT")])
    out = _kind_of_goods([lines], raw, "S::Ghi tắt", "Ghi tắt", "Tên hàng")
    products = next(t for t in out if t.target == "products")
    assert {c.target: c.source for c in products.columns} == {"product_key": "Tên hàng", "product_name": "Tên hàng",
                                                               "category": "Loại"}


def test_a_shop_without_units_counts_what_it_writes():
    """A ledger with "SL" only, no unit and no conversion table: each product sells in one unit, so the quantity
    written is the base quantity; "bán mấy chiếc" asks no unit of the shop's."""
    from datamate.mapping.build import derive_base_qty
    db = shop()
    db.tables["lines"] = db.tables["lines"].drop(columns=["base_qty"])
    derive_base_qty(db)
    assert db.tables["lines"]["base_qty"].tolist() == [1.0, 2.0, 1.0, 1.0, 3.0]
    assert run({"intent": "value", "measures": [{"metric": "quantity", "unit": "chiếc", "filters": [
        {"field": "product", "value": "máy mới"}]}]}) == 4


def raw_books() -> tuple:
    """A sales sheet (STT, IMEI) with a trade-in book and a warranty book, as a public phone shop keeps them."""
    sales = pd.DataFrame([("1", "111", "IP15 128 đen", "20.000.000đ"), ("2", "222 / 333", "A56 128 đen", "10tr"),
                          ("3", "", "Cáp C", "100k")], columns=["STT", "IMEI", "Hàng", "Khách trả"])
    trade = pd.DataFrame([("01/06/2026", "Galaxy S21", "3000k", "2"), ("02/06/2026", "iPhone 11", "1.200.000đ", "2")],
                         columns=["Ngày", "Máy thu", "Giá thu", "Trừ vào (STT sổ bán)"])
    warranty = pd.DataFrame([("05/06/2026", "iPhone 15", "111"), ("06/06/2026", "Samsung Galaxy A56 5G", "333"),
                             ("07/06/2026", "iPhone 15", "111")], columns=["Ngày nhận", "Máy", "IMEI"])
    raw = RawBusiness(root=Path("."), readme="", tables=[
        RawTable(table_id="S::T6", file="S", sheet="T6", frame=sales),
        RawTable(table_id="M::Sheet1", file="M", sheet="Sheet1", frame=trade),
        RawTable(table_id="N::Bảo hành", file="N", sheet="Bảo hành", frame=warranty)])
    mapping = Mapping(tables=[TableMap(target="lines", sources=["S::T6"], columns=[
        ColumnMap(target="order_id", source="STT")])])
    return raw, mapping


def test_the_side_books_give_trade_ins_and_warranty_visits():
    """Trade-ins summed onto the order they name (order 2: 3 000 000 + 1 200 000); each warranty visit one row, its
    order found by the IMEI (a row of two phones written "222 / 333")."""
    from datamate.mapping.side_books import side_books
    raw, mapping = raw_books()
    o = pd.DataFrame({"order_id": ["1", "2", "3"], "order_time": [datetime(2026, 6, 1)] * 3, "status": "completed"})
    db = CanonicalDB(tables={"orders": o})
    side_books(db, raw, mapping)
    assert db.tables["orders"]["trade_in_amount"].fillna(0).tolist() == [0, 4_200_000, 0]
    v = db.tables["warranty_visits"]
    assert v["order_id"].tolist() == ["1", "2", "1"] and v["product_line"].tolist()[1] == "Samsung Galaxy A56 5G"


def test_a_phone_warranty_rate_is_visits_over_phones_sold():
    """§6 Cửa hàng điện thoại: "số lượt bảo hành có ngày nhận trong quý, chia cho số máy bán trong quý (bỏ đơn huỷ,
    đơn trả)". June: phones sold 1 + 2 + 1 + 1 (the 3 cables are accessories); 2 visits: 40%."""
    db = shop()
    db.tables["warranty_visits"] = pd.DataFrame({"visit_time": pd.to_datetime(["2026-06-05", "2026-06-20"]),
                                                 "product_line": ["Xiaomi Redmi Note 14", "Nokia 105 4G"]})
    from datamate.metrics import sales
    june = ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30))
    assert sales.warranty_count(db, june, [], {}) == 2
    assert sales.warranty_rate(db, june, [], {}) == 40.0


def test_the_debt_and_installment_books_read_as_debts():
    """README of a public phone shop: "Sổ nợ … Nợ là số còn nợ sau khi trả lúc mua … Đã trả, Ngày trả"; "Sổ góp … Giá,
    Trả trước, Số kỳ, Góp/tháng, Hạn góp (ngày) … Ngày góp, Đã góp". Order 1 (cash 500k), order 2 (debt: 1tr, 400k
    left, 100k paid back 10/06), order 3 (installment: 3tr, 600k down, 3 × 800k due the 5th: 05/07, 05/08, 05/09; one
    paid 06/07). At the end of 20/08: debt 300k + installments 1 600k; overdue 800k (05/08), one customer."""
    from datamate.mapping.side_books import debts
    from datamate.metrics import debt
    o = pd.DataFrame({"order_id": ["1", "2", "3"], "order_time": pd.to_datetime(["2026-06-01", "2026-06-02",
                                                                                   "2026-06-03"]),
                      "status": "completed", "total_due": [500_000.0, 1_000_000.0, 3_000_000.0],
                      "goods_amount": [500_000.0, 1_000_000.0, 3_000_000.0], "customer_key": [None, "a", "b"]})
    debt_book = pd.DataFrame([("02/06/2026", "An", "400k", "100k", "10/06/2026", "STT 2")],
                             columns=["Ngày", "Khách", "Nợ", "Đã trả", "Ngày trả", "Ghi chú"])
    inst = pd.DataFrame([("03/06/2026", "3", "Bình", "3tr", "600k", "3", "800k", "5", "06/07/2026", "800k")],
                        columns=["Ngày", "STT", "Khách", "Giá", "Trả trước", "Số kỳ", "Góp/tháng", "Hạn góp (ngày)",
                                 "Ngày góp", "Đã góp"])
    raw = RawBusiness(root=Path("."), readme="", tables=[
        RawTable(table_id="N::Sổ nợ", file="N", sheet="Sổ nợ", frame=debt_book),
        RawTable(table_id="N::Trả góp", file="N", sheet="Trả góp", frame=inst)])
    db = CanonicalDB(tables={"orders": o})
    debts(db, raw)
    assert db.tables["installments"]["due_date"].astype(str).tolist() == ["2026-07-05", "2026-08-05", "2026-09-05"]
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "period": {"kind": "until",
                                                                                     "date": "2026-08-20"},
                                                       "measures": [{"metric": "debt_total"}]}),
                        as_of=date(2026, 8, 20), period=ResolvedPeriod(start=date(2000, 1, 1), end=date(2026, 8, 20),
                                                                       mode="stock"))
    m = plan.plan.measures[0]
    assert debt.debt_total(db, plan, m) == 1_900_000
    assert debt.overdue_amount(db, plan, m) == 800_000 and debt.overdue_installment_count(db, plan, m) == 1


def test_a_customer_is_the_phone_number_the_ledger_writes():
    from datamate.mapping.side_books import customers
    sales = pd.DataFrame([("1", "Triệu Linh An 0327988481"), ("2", "Triệu Linh An - 0327 988 481"), ("3", "lẻ"),
                          ("4", "Châu Hằng Hùng (0932225622)")], columns=["STT", "Khách"])
    raw = RawBusiness(root=Path("."), readme="", tables=[RawTable(table_id="S::T6", file="S", sheet="T6", frame=sales)])
    mapping = Mapping(tables=[TableMap(target="lines", sources=["S::T6"], columns=[ColumnMap(target="order_id",
                                                                                              source="STT")])])
    db = CanonicalDB(tables={"orders": pd.DataFrame({"order_id": ["1", "2", "3", "4"]})})
    customers(db, raw, mapping)
    o = db.tables["orders"]
    assert o["customer_key"].tolist()[:2] == ["0327988481"] * 2 and pd.isna(o["customer_key"][2])
    assert o["customer_name"].tolist()[3] == "Châu Hằng Hùng"
