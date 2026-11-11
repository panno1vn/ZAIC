"""Session 12 (09/11): N125 customer named without the phone the file writes, N126 channel / payment the shop does not
record (§7), N127 measure words of an average order value and of buying stock in, N128 "th này" is this month, N129
"… cao hơn …, rồi … cao hơn …, đúng không?" is a trend, N130 quantity delivered of one product, N131 a quantity bound
written in money and the month word alone as a filter."""
from datetime import date

import pandas as pd

from datamate import nlu
from datamate.contracts import CanonicalDB, QueryPlan
from datamate.nlu import baseline, linking
from datamate.verify import not_recorded

AS_OF = date(2026, 6, 30)


def _accept(question: str, raw: dict):
    return nlu.accept_plan(question, QueryPlan.model_validate(raw), AS_OF)


def test_a_customer_the_file_writes_with_a_phone_is_named_without_it():
    cands = {"ong hieu anh 0935 174 948": frozenset({"Ông Hiếu Anh 0935174948"}),
             "ong hieu anh 0935174948": frozenset({"Ông Hiếu Anh 0935174948"}),
             "ngo nam ngan 0979206677": frozenset({"Ngô Nam Ngân 0979206677"}),
             "ngo nam ngan 0911111111": frozenset({"Ngô Nam Ngân 0911111111"})}
    assert linking.link_value("customer", "Ông Hiếu Anh", "", cands).value == "Ông Hiếu Anh 0935174948"
    # two customers of that name: the question does not say which
    assert linking.link_value("customer", "Ngô Nam Ngân", "", cands).value is None


def _plan(filters):
    return QueryPlan.model_validate({"intent": "value", "period": {"kind": "this_month"},
                                     "measures": [{"metric": "revenue", "filters": filters}]})


def test_a_channel_the_shop_does_not_record_is_unanswerable_and_a_misread_value_is_not():
    db = CanonicalDB(tables={"orders": pd.DataFrame({"order_id": ["1"], "customer_key": ["A"]})},
                     readme="# Dữ liệu\n- **Mã đơn**: mã đơn\n- **Khách**: tên khách\n", conventions=())
    assert not_recorded(_plan([{"field": "channel", "value": "tại quầy"}]), "doanh thu bán tại quầy", db) == "kênh bán"
    # "ddown" (telex for "đơn") read as a payment method: a misread, not a question about payments (train)
    assert not_recorded(_plan([{"field": "payment_method", "value": "dDown"}]), "hqua cos nhiêu ddown", db) is None
    # the README writes a channel: recorded
    db.readme += "- **Kênh bán**: kênh bán\n"
    assert not_recorded(_plan([{"field": "channel", "value": "tại quầy"}]), "doanh thu bán tại quầy", db) is None


def test_an_average_order_value_needs_a_money_or_order_word_and_buying_stock_in_is_no_sale():
    avg = {"intent": "value", "period": {"kind": "month", "year": 2026, "month": 3},
           "measures": [{"metric": "avg_order_value", "filters": []}]}
    assert _accept("Th3/2026 trung bình mỗi thứ Tư tiệm xửa mấy nượt xe?", avg) is None
    assert _accept("Th3/2026 trung bình mỗi đơn khách trả bao nhiêu tiền?", avg) is not None
    revenue = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 6},
               "measures": [{"metric": "revenue", "filters": []}]}
    # N152: no sale, the money spent buying in (§5)
    p = _accept("Tháng 6/2025 tiệm cất hàng hết tổng cộng bao nhiêu tiền?", revenue)
    assert p is not None and p.measures[0].metric == "purchase_amount"


def test_th_nay_is_this_month():
    for kind in ("this_week", "today"):
        raw = {"intent": "value", "period": {"kind": kind}, "measures": [{"metric": "revenue", "filters": []}]}
        plan = _accept("Th này sốp bán được bao nhiêu tiền z?", raw)
        assert plan is not None and plan.period.kind == "this_month"
        assert _accept("Tuần này th nay bán được bao nhiêu tiền?", raw).period.kind == kind  # a week word: kept


def test_a_chain_of_rises_over_three_months_is_a_trend():
    p = baseline.parse("Dthu T7/2025 cao hơn T6/2025, rồi T8/2025 lại cao hơn T7/2025, đúng vậy không?")
    assert p.intent == "trend" and p.period.months == ["2025-06", "2025-07", "2025-08"] and p.answer_type == "boolean"
    assert baseline.parse("Dthu T7/2025 cao hơn T5/2025, rồi T8/2025 lại cao hơn T7/2025, đúng vậy không?") is None


def test_carried_goods_are_the_quantity_delivered_of_the_orders_placed_that_month():
    raw = {"intent": "value", "period": {"kind": "until", "date": "2025-05-01"},
           "measures": [{"metric": "delivery_count", "filters": [
               {"field": "product", "value": "Dây điện Cadivi"}, {"field": "order_status", "value": "completed"}]}]}
    plan = _accept("Tới hôm nay, xe đã giao tổng cộng mấy cuộn Dây điện Cadivi cho khách đặt tháng 4/2025?", raw)
    assert plan is not None and plan.measures[0].metric == "delivered_qty"
    assert [f.field for f in plan.measures[0].filters] == ["product"]
    assert (plan.period.kind, plan.period.year, plan.period.month) == ("month", 2025, 4)


def test_a_count_of_days_over_an_amount_in_money_is_a_revenue_bound():
    raw = {"intent": "count_where", "period": {"kind": "month", "year": 2025, "month": 8},
           "threshold": {"entity": "day", "metric": "quantity", "op": "gte", "value": 10}}
    plan = _accept("Tháng 8/2025 có mấy bữa tiệm bán được từ 10 củ trở lên?", raw)
    assert plan is not None and plan.threshold.metric == "revenue" and plan.threshold.value == 10_000_000
    assert "th" in nlu.GENERIC_VALUES  # "Dthu th 6/26 … so th 6/25" read with product = th


def test_an_average_per_weekday_is_avg_per_weekday():
    """N134: §3 "trung bình mỗi ngày thứ X của kỳ: chia cho số ngày thứ X trong kỳ"."""
    raw = {"intent": "value", "period": {"kind": "month", "year": 2026, "month": 3},
           "measures": [{"metric": "ticket_count", "filters": [{"field": "weekday", "value": "wed"}]}]}
    plan = _accept("Th3/2026 trung bình mỗi thứ Tư tiệm sửa mấy lượt xe?", raw)
    assert plan is not None and plan.measures[0].aggregate == "avg_per_weekday"
    assert _accept("Th3/2026 các ngày thứ Tư tiệm sửa tổng cộng mấy lượt xe?", raw).measures[0].aggregate == "total"


def test_installment_periods_due_of_a_customer_are_counted():
    """N135: "khách X góp tới hạn mấy kỳ rồi, tính luôn kỳ hạn hôm nay" is the periods due by today, not money."""
    raw = {"intent": "value", "period": {"kind": "until", "date": "2026-06-30"},
           "measures": [{"metric": "amount_due_total", "filters": [{"field": "customer", "value": "Tạ Dũng Long"},
                                                                    {"field": "payment_method", "value": "Trả góp"}]}]}
    plan = _accept("Hết hnay, khách Tạ Dũng Long góp tới hạn mấy kỳ rồi, tính luôn kỳ hạn hôm nay nha?", raw)
    assert plan is not None and plan.measures[0].metric == "installments_due" and plan.period.kind == "today"
    assert [f.field for f in plan.measures[0].filters] == ["customer"]


def test_phones_sold_in_a_month_that_came_back_for_warranty():
    """N136: phones of the orders placed that month the warranty book received, not that month's visits."""
    raw = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 8},
           "measures": [{"metric": "warranty_count", "filters": [{"field": "product_line", "value": "phones"}]}]}
    plan = _accept("Máy bán ra tháng 8/2025, tới hnay có bao nhiêu máy đã mang lại bảo hành rồi?", raw)
    assert plan is not None and plan.measures[0].metric == "phones_warrantied" and plan.period.month == 8
    # visits of a month, no phones sold: unchanged
    visits = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 8},
              "measures": [{"metric": "warranty_count", "filters": []}]}
    assert _accept("Tháng 8/2025 có bao nhiêu lượt bảo hành?", visits).measures[0].metric == "warranty_count"


def test_size_xxl_is_not_size_xl():
    from datamate.metrics.frames import _stage_core
    assert _stage_core("Size XXL") == "xxl" and _stage_core("XL") == "xl" and _stage_core("Số 2") == "2"
    assert _stage_core("size xl") == _stage_core("Size XL")
