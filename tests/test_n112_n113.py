"""N112: §7 "shop không ghi loại thông tin câu hỏi cần" — product group, profit without cost, return / cancel reason,
a product's quality — unanswerable. N113: credit orders counted by the README's due day ("Ngày phải trả")."""
from datetime import date
from pathlib import Path

import pandas as pd

from datamate import metrics, temporal
from datamate.contracts import CanonicalDB, ColumnMap, Mapping, QueryPlan, RawBusiness, TableMap
from datamate.mapping.from_readme import enrich
from datamate.nlu.grounding import due_date_count_plan, subjective_quality
from datamate.verify import not_recorded

from test_mapping_readme import section, table

CALENDAR = Path("data/train/calendar.csv")
README = "# Dữ liệu\n\n## Cột trong `ban.csv`\n- **Mã đơn**: mã đơn\n- **Hàng**: tên hàng\n"


def db(readme: str = README, **tables) -> CanonicalDB:
    return CanonicalDB(tables=tables, readme=readme)


def plan(**kw) -> QueryPlan:
    return QueryPlan.model_validate({"period": {"kind": "month", "year": 2025, "month": 11}, **kw})


GROUP = {"intent": "value", "measures": [{"metric": "quantity", "filters": [
    {"field": "product_group", "value": "trà sữa"}]}]}


def test_a_group_the_shop_does_not_record_is_unanswerable():
    lines = pd.DataFrame({"product_key": ["Trà sữa"], "qty": [1.0]})
    assert not_recorded(plan(**GROUP), "Tháng 9/2025 nhóm trà sữa bán được bao nhiêu ly?", db(lines=lines)) == "nhóm hàng"
    named = README + "- **Nhóm**: nhóm hàng\n"
    assert not_recorded(plan(**GROUP), "nhóm trà sữa bán bao nhiêu ly", db(named, lines=lines)) is None
    grouped = lines.assign(product_group=["trà"])
    assert not_recorded(plan(**GROUP), "nhóm trà sữa bán bao nhiêu ly", db(lines=grouped)) is None


def test_profit_without_cost_is_unanswerable():
    p = plan(intent="rank", rank={"entity": "product", "by": "gross_profit", "k": 1, "order": "desc"})
    lines = pd.DataFrame({"product_key": ["A"], "line_amount": [1.0]})
    assert not_recorded(p, "02/2026 mặt hàng nào lời nhiều nhất z?", db(lines=lines)) == "giá vốn"
    assert not_recorded(p, "mặt hàng nào lời nhiều nhất", db(README + "- **Giá vốn**: giá vốn\n", lines=lines)) is None
    assert not_recorded(p, "mặt hàng nào lời nhiều nhất", db(lines=lines.assign(unit_cost=[0.5]))) is None


def test_a_return_or_cancel_reason_the_shop_does_not_record_is_unanswerable():
    for q in ("Th3/2025 có mấy đơn bị huỷ vì giao trễ z?", "thang 3/2026, tra hang vi loi va tra vi mua nham",
              "T9/2025 có mấy đơn khách trả lại vì gọi nhầm món?", "Th5/2026 khách huỷ đơn chủ yếu vì sao z?"):
        assert not_recorded(None, q, db()) == "lý do trả / huỷ đơn", q
    assert not_recorded(None, "Th3/2025 có mấy đơn bị huỷ vì giao trễ?", db(README + "- **Lý do**: lý do huỷ\n")) is None
    returns = pd.DataFrame({"order_id": ["D1"], "reason": ["lỗi"]})
    assert not_recorded(None, "mấy đơn trả lại vì lỗi", db(returns=returns)) is None
    for q in ("doanh thu các đơn trả bằng ví điện tử tháng 2/2025", "thang 3 dthu cac don tra bang vi dien tu"):
        assert not_recorded(None, q, db()) is None, q


def test_a_product_quality_is_subjective():
    assert subjective_quality("Mặt hàng có chất lượng tốt nhất tháng 10/2025 là gì?")
    assert subjective_quality("Trong tháng 11/2025, sản phẩm nào ngon nhất?")
    assert subjective_quality("Trong tháng 3/2026, ai là thợ nhiệt tình nhất?")
    assert not subjective_quality("Tháng 10/2025 mặt hàng nào bán số lượng nhiều nhất?")
    assert not subjective_quality("Thợ chăm chỉ nhất tháng 3/2026 là ai?")  # §3 defines it


DUE = [("Tới hnay, mấy đơn bán chịu ghi ngày phải trả còn sau hôm nay vậy?", "gt", "today"),
       ("Tới hôm nay, có mấy đơn bán chịu ghi ngày phải trả muộn hơn hôm nay (hạn đúng hôm nay không tính)?", "gt",
        "today"),
       ("Tính đến hôm nay, trong mọi đơn bán chịu, có mấy đơn ghi ngày phải trả trong tháng 4/2026?", "eq", "2026-04"),
       ("Tính tới hnay, có mấy đơn bán chịu ghi ngày phải trả trong th2/2026?", "eq", "2026-02")]


def test_the_due_day_questions_are_read():
    for q, op, value in DUE:
        p = due_date_count_plan(q, date(2026, 1, 5))
        f = p.measures[0].filters[0]
        assert (p.measures[0].metric, f.field, f.op, f.value) == ("due_order_count", "other", op, value), q
        assert p.period.kind == "until"
    assert due_date_count_plan("Tháng 2/2026 có mấy đơn bán chịu?", date(2026, 1, 5)) is None
    assert due_date_count_plan("Có mấy đơn ngày phải trả trong tháng 2/2026 và sau hôm nay?", date(2026, 1, 5)) is None


def test_credit_orders_are_counted_by_their_due_day():
    orders = pd.DataFrame({
        "order_id": ["D1", "D2", "D3", "D4", "D5"],
        "order_time": pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-10", "2026-01-03"]),
        "status": ["completed", "completed", "cancelled", "completed", "completed"],
        "due_date": [date(2026, 2, 1), date(2026, 2, 20), date(2026, 2, 5), date(2026, 2, 9), None]})
    shop = CanonicalDB(tables={"orders": orders}, date_ranges={"orders": (date(2025, 1, 1), date(2026, 3, 1))})
    for (q, _, _), want in zip(DUE, (2, 2, 0, 2)):  # D4 is placed after today, D3 cancelled, D5 not on credit
        r = temporal.resolve(due_date_count_plan(q, date(2026, 1, 5)), date(2026, 1, 5), CALENDAR, shop)
        assert metrics.execute(r, shop).value == want, q


def test_the_due_day_is_looked_up_from_the_readme_book():
    readme = section("ban.csv", {"Mã đơn": "mã đơn", "Ngày": "ngày bán", "TT": "trạng thái đơn"}) + \
        section("hanno.csv", {"Mã đơn hàng": "mã đơn", "Kỳ hạn": "số ngày được nợ", "Ngày phải trả": "hạn thanh toán"})
    raw = RawBusiness(root=Path("."), readme=readme, tables=[
        table("ban.csv", [("D1", "01/06/2026", "Xong")], ["Mã đơn", "Ngày", "TT"]),
        table("hanno.csv", [("D1", 30, "2026-07-01")], ["Mã đơn hàng", "Kỳ hạn", "Ngày phải trả"])])
    m = Mapping(tables=[TableMap(target="orders", sources=["ban.csv"], columns=[
        ColumnMap(target="order_id", source="Mã đơn"), ColumnMap(target="order_time", source="Ngày"),
        ColumnMap(target="status", source="TT")])])
    due = {c.target: c for c in enrich(m, raw).tables[0].columns}["due_date"]
    assert due.transform == "lookup" and due.parse == "date"
    assert due.args == {"table": "hanno.csv", "key": "Mã đơn hàng", "value": "Ngày phải trả", "keep_missing": False}
