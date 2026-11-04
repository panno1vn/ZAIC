"""N26: a shop that records orders without their lines (train biz_110: "mỗi dòng một đơn hàng, không có chi tiết mặt
hàng"). Its "tiền hàng của đơn: cộng thành tiền các mặt hàng" is the §1 revenue of the order: revenue, order counts,
customers and days are answered from it, every figure that needs the lines abstains."""
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from datamate import metrics
from datamate.contracts import CanonicalDB, QueryPlan, RawBusiness, ResolvedPeriod, ResolvedPlan
from datamate.mapping import build_canonical, run_checks
from datamate.mapping.from_readme import map_from_readme

from test_mapping_readme import section, table

NOTES = {"Tien hang": "tiền hàng của đơn: cộng thành tiền các mặt hàng, trước giảm giá của đơn, chưa gồm phí giao",
         "TongTien": "số khách phải trả cho cả đơn (đã tính giảm giá của đơn và phí giao)",
         "Mã bill": "mã đơn", "Bên mua": "tên khách (Khách lẻ nếu không lưu)", "Ngày giao dịch": "ngày bán",
         "Status": "trạng thái đơn"}


def invoices(n: int = 30) -> RawBusiness:
    rows = [(f"{10_000 * (1 + i % 3):,}", f"{10_000 * (1 + i % 3):,}", f"ORD{i:04d}", ["An", "kl", "Bình"][i % 3],
             f"{1 + i % 28:02d}/06/2026", "Khách hủy" if i == 5 else "Hoàn thành") for i in range(n)]
    return RawBusiness(root=Path("."), readme=section("hoa_don.csv", NOTES) + "Dữ liệu có đến hết 28/06/2026.\n",
                       tables=[table("hoa_don.csv", rows, list(NOTES))])


def test_the_readme_maps_an_orders_only_shop_and_its_checks_pass():
    m, why = map_from_readme(invoices())
    assert m is not None, why
    assert [t.target for t in m.tables] == ["orders"]
    cols = {c.target: c.source for c in m.tables[0].columns}
    assert cols["goods_amount"] == "Tien hang" and cols["total_due"] == "TongTien" and cols["order_id"] == "Mã bill"
    db = build_canonical(invoices(), m)
    m.checks = run_checks(db, invoices().readme)
    assert m.ok, [(c.name, c.detail) for c in m.checks if not c.passed]


def test_order_ids_that_repeat_are_no_orders_only_table():
    shop = invoices()
    shop.tables[0].frame["Mã bill"] = "ORD0001"
    m, why = map_from_readme(shop)
    assert m is None and "lặp" in why


def _run(db, raw):
    plan = ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=date(2026, 6, 30),
                        period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30)), linked={})
    return metrics.execute(plan, db)


def test_revenue_and_counts_come_from_the_goods_amount_and_product_figures_abstain():
    o = pd.DataFrame({"order_id": ["a", "b", "c"], "order_time": [datetime(2026, 6, d) for d in (1, 1, 2)],
                      "status": ["completed", "cancelled", "delivering"], "goods_amount": [30_000.0, 50_000.0, 20_000.0],
                      "customer_key": ["An", None, "An"]})
    db = CanonicalDB(tables={"orders": o})
    month = {"kind": "this_month"}
    r = _run(db, {"intent": "value", "measures": [{"metric": "revenue"}], "period": month})
    assert r.value == 50_000 and "orders.goods_amount" in r.requires and "lines.line_amount" not in r.requires
    assert _run(db, {"intent": "value", "measures": [{"metric": "order_count"}], "period": month}).value == 2
    assert _run(db, {"intent": "rank", "period": month, "rank": {"entity": "day", "by": "revenue"}}).value == "2026-06-01"
    assert _run(db, {"intent": "rank", "period": month, "rank": {"entity": "product", "by": "quantity"}}) is None
    assert _run(db, {"intent": "value", "measures": [{"metric": "quantity"}], "period": month}) is None
