"""Public rulebook §6 Mẹ và bé (06/11): "Số sữa, size bỉm: lấy theo cột Số / Size của danh mục: hàng để trống cột
Số / Size thì không xếp vào số, size nào, dù tên hàng có số. Phần trăm của một size hay một hãng chia cho tổng số bịch
mọi hàng bỉm tã cùng kỳ"; "Khách thành viên mới trong tháng: số khách có Ngày đăng ký trong tháng đó"."""
from datetime import date, datetime

import pandas as pd

from datamate import metrics
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.nlu import link_entities

ITEMS = [("Sữa A số 2 900g", "sữa bột", "A", "Số 2", 2), ("Sữa B số 2 800g", "sữa bột", "B", "Số 2", 1),
         ("Sữa A số 3 900g", "sữa bột", "A", "Số 3", 4), ("Tã Bobby size XL", "bỉm tã", "Bobby", "Size XL", 3),
         ("Tã Moony size L", "bỉm tã", "Moony", "Size L", 5), ("Khăn sữa số 2 lớp", "đồ dùng", None, None, 7)]


def shop() -> CanonicalDB:
    lines = pd.DataFrame({"order_id": [str(i) for i in range(len(ITEMS))], "product_key": [x[0] for x in ITEMS],
                          "product_name": [x[0] for x in ITEMS], "product_group": [x[1] for x in ITEMS],
                          "qty": [float(x[4]) for x in ITEMS], "base_qty": [float(x[4]) for x in ITEMS],
                          "line_amount": 100.0, "is_item": True})
    products = pd.DataFrame({"product_key": [x[0] for x in ITEMS], "product_name": [x[0] for x in ITEMS],
                             "product_group": [x[1] for x in ITEMS], "brand": [x[2] for x in ITEMS],
                             "stage": [x[3] for x in ITEMS], "size": [x[3] for x in ITEMS]})
    o = pd.DataFrame({"order_id": [str(i) for i in range(len(ITEMS))], "order_time": datetime(2026, 6, 2),
                      "status": "completed", "has_time": False})
    customers = pd.DataFrame({"customer_key": ["An", "Bình", "Chi"], "customer_name": ["An", "Bình", "Chi"],
                              "registered_date": [date(2026, 6, 3), date(2026, 5, 30), date(2026, 6, 28)]})
    return CanonicalDB(tables={"orders": o, "lines": lines, "products": products, "customers": customers})


def run(raw):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"period": {"kind": "this_month"}, **raw}), as_of=date(2026, 6, 30),
                        period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30)))
    db = shop()
    r = metrics.execute(link_entities(plan, db, ""), db)
    return None if r is None else r.value


def test_milk_stage_by_the_catalogue_column_not_the_name():
    """"sữa bột số 2": 2 + 1 cans; "Khăn sữa số 2 lớp" has "số 2" in its name but no Số / Size: not stage 2."""
    assert run({"intent": "value", "measures": [{"metric": "quantity", "filters": [
        {"field": "product", "value": "sữa bột số 2"}]}]}) == 3
    assert run({"intent": "value", "measures": [{"metric": "quantity", "filters": [
        {"field": "stage", "value": "số 2"}]}]}) == 3


def test_a_size_or_brand_share_is_over_every_diaper_bag():
    """Size XL: 3 of 8 bags (37.5%); Moony: 5 of 8. A product with no brand is no brand, not an unknown one."""
    whole = {"metric": "quantity", "filters": [{"field": "product_group", "value": "bỉm tã"}]}
    assert run({"intent": "share", "measures": [{"metric": "quantity", "filters": [{"field": "size", "value": "XL"}]}],
                "share_of": whole}) == 37.5
    assert run({"intent": "share", "measures": [{"metric": "quantity", "filters": [
        {"field": "brand", "value": "Moony"}]}], "share_of": whole}) == 62.5


def test_new_members_are_counted_by_their_registration_day():
    assert run({"intent": "value", "measures": [{"metric": "new_customer_count"}]}) == 2
