"""N101 (08/11): a phone shop's amount due per order, the share of its orders with a trade-in, values asked together,
the deductions written as a filter, and a data value that shares its words with a rulebook term (public run11)."""
import hashlib
import json
from datetime import date, datetime

import pandas as pd

from datamate import metrics
from datamate.contracts import (INTERNAL_METRICS, CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan)
from datamate.nlu import link_entities, plan_problems
from datamate.nlu.grounding import drop_restated_metric, due_per_order, trade_in_share, values_together
from datamate.nlu.prompt import PLAN_SCHEMA
from datamate.rules import unverified_terms

NAMES = ["Xiaomi Redmi Note 14 128GB Đen", "iPhone 13 128GB cũ 99%", "Cáp Type-C 1m"]


def shop() -> CanonicalDB:
    o = pd.DataFrame({"order_id": ["1", "2", "3", "4"], "order_time": [datetime(2026, 6, d) for d in (1, 2, 3, 4)],
                      "status": ["completed", "completed", "completed", "cancelled"], "has_time": False,
                      "total_due": [5_000_000.0, 7_000_001.0, 300_000.0, 9_000_000.0],
                      "trade_in_amount": [0.0, 2_000_000.0, None, 1_000_000.0]})
    lines = pd.DataFrame({"order_id": ["1", "2", "3", "4"], "product_key": [NAMES[0], NAMES[1], NAMES[2], NAMES[0]],
                          "product_name": [NAMES[0], NAMES[1], NAMES[2], NAMES[0]], "qty": [1.0, 2.0, 3.0, 1.0],
                          "base_qty": [1.0, 2.0, 3.0, 1.0], "line_amount": [5e6, 9e6, 3e5, 1e7], "is_item": True})
    products = pd.DataFrame({"product_key": NAMES, "product_name": NAMES, "category": ["máy mới", "máy cũ", "phụ kiện"]})
    return CanonicalDB(tables={"orders": o, "lines": lines, "products": products})


def run(raw: dict):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"period": {"kind": "this_month"}, **raw}), as_of=date(2026, 6, 30),
                        period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30)))
    db = shop()
    r = metrics.execute(link_entities(plan, db), db)
    return None if r is None else r.value


def plan(raw: dict) -> QueryPlan:
    return QueryPlan.model_validate({"period": {"kind": "month", "year": 2026, "month": 6}, **raw})


def test_the_internal_metrics_stay_out_of_the_reader_schema():
    """The reader's grammar (and the answers cached under it) is the one before N101."""
    text = json.dumps(PLAN_SCHEMA, ensure_ascii=False, sort_keys=True)
    assert not any(f'"{m}"' in text for m in INTERNAL_METRICS)
    assert hashlib.sha256(text.encode()).hexdigest() == \
        "8212c4578d7eb4e1e8e1b4d4049a64dce01c86bb4477d1a0b000a44d3a50a34c"


def test_the_amount_due_per_order_is_over_the_valid_orders_in_whole_dong():
    """(5 000 000 + 7 000 001 + 300 000) / 3 orders, the cancelled one left out, rounded half up (§3, §9)."""
    assert run({"intent": "value", "measures": [{"metric": "avg_amount_due"}]}) == 4_100_000


def test_the_share_of_orders_with_a_trade_in():
    """1 of the 3 valid orders took an old phone in (the cancelled one did too, and is left out)."""
    v = run({"intent": "share", "measures": [{"metric": "trade_in_order_count"}],
             "share_of": {"metric": "order_count"}})
    assert round(v, 2) == 33.33


def test_an_average_due_per_order_is_read_as_one():
    q = "Cho tôi hỏi 6-2026 trung bình mỗi đơn khách phải trả bao nhiêu?"
    p = due_per_order(q, plan({"intent": "value", "measures": [{"metric": "avg_order_value", "filters": [
        {"field": "payment_method", "value": "Ghi nợ"}]}]}))
    assert [(m.metric, m.filters) for m in p.measures] == [("avg_amount_due", [])]
    q = "08/2025 tinh tien khach phai tra sau khi tru bot va tien may cu thu lai, binh quan mot don la may dong?"
    p = due_per_order(q, plan({"intent": "value", "measures": [{"metric": "amount_due_total"},
                                                                {"metric": "trade_in_amount"},
                                                                {"metric": "avg_order_value"}]}))
    assert [m.metric for m in p.measures] == ["avg_amount_due"]
    # no "phải trả": the average order value stays the revenue's (§3)
    q = "6-2026 trung bình mỗi đơn bao nhiêu tiền?"
    p0 = plan({"intent": "value", "measures": [{"metric": "avg_order_value"}]})
    assert due_per_order(q, p0) == p0
    # the total due, no average asked
    q = "Khách phải trả hết bao nhiêu tiền trong 6-2026 vậy?"
    p0 = plan({"intent": "value", "measures": [{"metric": "amount_due_total"}]})
    assert due_per_order(q, p0) == p0


def test_the_deductions_written_as_a_filter_are_the_metric():
    p = drop_restated_metric(plan({"intent": "value", "measures": [{"metric": "amount_due_total", "filters": [
        {"field": "category", "value": "trừ tiền bớt với tiền máy cũ thu lại"}]}]}))
    assert p.measures[0].filters == []
    p = drop_restated_metric(plan({"intent": "value", "measures": [{"metric": "amount_due_total", "filters": [
        {"field": "category", "value": "trade_in"}]}]}))
    assert p.measures[0].filters == []
    p0 = plan({"intent": "value", "measures": [{"metric": "amount_due_total", "filters": [
        {"field": "category", "value": "máy cũ"}]}]})
    assert drop_restated_metric(p0) == p0  # a kind of goods, not a deduction


def test_a_share_of_orders_with_a_trade_in():
    for q, raw in [("Đơn có thu lại máy cũ 4-2026 chiếm mấy % tổng đơn?",
                    {"intent": "share", "measures": [{"metric": "order_count", "filters": [
                        {"field": "is_warranty", "value": True}]}]}),
                   ("Th này bnhiu % đh có thu máy cũ của khách z?",
                    {"intent": "value", "measures": [{"metric": "trade_in_amount", "filters": [
                        {"field": "order_status", "value": "completed"}]}]})]:
        p = trade_in_share(q, plan(raw))
        assert p.intent == "share" and [m.metric for m in p.measures] == ["trade_in_order_count"]
        assert p.share_of.metric == "order_count" and p.share_of.filters == []
    p0 = plan({"intent": "value", "measures": [{"metric": "trade_in_amount"}]})
    assert trade_in_share("6-2026 tổng tiền thu máy cũ bao nhiêu?", p0) == p0  # no percent


def test_values_asked_together_are_one_figure():
    q = "6-2025 tiệm bán được mấy chiếc điện thoại, gộp cả máy mới với máy cũ nhé?"
    p = values_together(q, plan({"intent": "value", "measures": [{"metric": "quantity", "filters": [
        {"field": "category", "value": "máy mới"}, {"field": "category", "value": "máy cũ"}]}]}))
    assert [(f.field, f.op, f.value) for f in p.measures[0].filters] == [("category", "in", ["máy mới", "máy cũ"])]
    q = "Th7/2025 ban ra tat ca bao nhieu chiec dien thoai, ca may moi lan may cu?"
    p = values_together(q, plan({"intent": "value", "measures": [
        {"metric": "quantity", "filters": [{"field": "category", "value": "máy mới"}]},
        {"metric": "quantity", "filters": [{"field": "category", "value": "máy cũ"}]}]}))
    assert len(p.measures) == 1 and p.measures[0].filters[0].value == ["máy mới", "máy cũ"]
    assert p.answer_type == "number"
    # asked apart: two numbers stay two
    q = "Thang ni doanh thu ban tai quay voi ban qua dien thoai lan luot la bao nhieu dong vay?"
    p0 = plan({"intent": "value", "measures": [{"metric": "revenue", "filters": [{"field": "channel", "value": "tại quầy"}]},
                                               {"metric": "revenue", "filters": [{"field": "channel", "value": "điện thoại"}]}]})
    assert values_together(q, p0) == p0


def test_a_kind_of_goods_named_like_a_term_is_the_kind():
    """"Thu máy cũ" is a public rulebook term (§6 Điện thoại); "máy cũ bán đc mấy chiếc" names the kind of goods."""
    rulebook = "## 6. Ngành\n\n### Cửa hàng điện thoại\n\n| Khái niệm | Cách hiểu |\n|---|---|\n" \
               "| Thu máy cũ | **Khách phải trả** là tiền của đơn sau bớt và sau trừ máy cũ |\n"
    q = "Máy cũ 8/25 bán đc mấy chiếc vậy?"
    found = unverified_terms(q, rulebook, ())
    assert found == ["§6.cua_hang_dien_thoai.thu_may_cu"]  # a term no train rulebook has
    assert unverified_terms(q, rulebook, (), ("máy cũ",)) == []
    assert unverified_terms(q, rulebook, (), ("máy mới",)) == found


def test_the_rewrites_pass_the_gates():
    q = "8-2026 mỗi đơn khách phải trả trung bình bnhiu, đã trừ bớt và máy cũ thu lại?"
    p, problems = plan_problems(q, QueryPlan.model_validate({
        "intent": "value", "period": {"kind": "month", "year": 2026, "month": 8},
        "measures": [{"metric": "avg_order_value", "filters": [{"field": "prescription", "value": False}]},
                     {"metric": "amount_due_total", "filters": [{"field": "prescription", "value": False}]}]}))
    assert problems == [] and [m.metric for m in p.measures] == ["avg_amount_due"]


# N102 (08/11): the phones of a phone shop, its warranty rate, and "T1/2026" as a month

from datamate.nlu import phone_kinds  # noqa: E402
from datamate.nlu.grounding import month_written_as_t, phones_as_whole, warranty_over_sold  # noqa: E402


def resolved(raw: dict) -> ResolvedPlan:
    return ResolvedPlan(plan=QueryPlan.model_validate({"period": {"kind": "this_month"}, **raw}),
                        as_of=date(2026, 6, 30), period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30)))


def test_the_phones_are_every_kind_but_accessories():
    db = shop()
    q = lambda v: {"intent": "value", "measures": [{"metric": "quantity", "filters": [  # noqa: E731
        {"field": "category", "value": v}]}]}
    p = phone_kinds(resolved(q("máy")), db).plan
    assert [(f.field, f.op, f.value) for f in p.measures[0].filters] == [("category", "in", ["máy cũ", "máy mới"])]
    p = phone_kinds(resolved(q("điện thoại cũ")), db).plan
    assert [(f.field, f.value) for f in p.measures[0].filters] == [("category", "máy cũ")]
    assert run(q("máy")) == 3 and run(q("điện thoại cũ")) == 2  # the cancelled order's phone left out
    assert phone_kinds(resolved(q("máy cũ")), db).plan == resolved(q("máy cũ")).plan  # links as it is
    other = shop()
    other.tables["products"]["category"] = ["thuốc", "thuốc", "vật tư"]  # no phone shop
    assert phone_kinds(resolved(q("máy")), other).plan == resolved(q("máy")).plan


def test_a_share_of_the_phone_money():
    q = "Th4/2026 máy mới chiếm mấy % tiền bán máy?"
    p = phones_as_whole(q, plan({"intent": "share", "measures": [{"metric": "revenue", "filters": [
        {"field": "category", "value": "máy mới"}]}], "share_of": {"metric": "revenue"}}))
    assert p.share_of.metric == "revenue" and [(f.field, f.value) for f in p.share_of.filters] == [("category", "máy")]
    q = "Bỏ phụ kiện ra thì dthu máy mới th này chiếm bnhiu % tổng dthu máy?"
    p = phones_as_whole(q, plan({"intent": "share", "measures": [
        {"metric": "revenue", "filters": [{"field": "category", "value": "máy mới"}]},
        {"metric": "revenue", "filters": [{"field": "category", "value": "máy mới"},
                                          {"field": "category", "value": "phụ kiện"}]}]}))
    assert len(p.measures) == 1 and p.share_of.filters[0].value == "máy"
    p0 = plan({"intent": "share", "measures": [{"metric": "revenue", "filters": [
        {"field": "category", "value": "máy mới"}]}]})
    assert phones_as_whole("Th4/2026 máy mới chiếm mấy % doanh thu?", p0) == p0  # the shop's whole revenue


def test_warranty_visits_over_phones_sold_is_the_rate():
    q = "Quý 3/2026 lượt bảo hành so với số máy bán đc chiếm bnhiu %?"
    p = warranty_over_sold(q, QueryPlan.model_validate({
        "intent": "value", "period": {"kind": "quarter", "year": 2026, "quarter": 3},
        "measures": [{"metric": "warranty_count", "filters": [{"field": "order_status", "value": "completed"}]},
                     {"metric": "quantity", "filters": [{"field": "order_status", "value": "completed"}]}]}))
    assert [(m.metric, m.filters) for m in p.measures] == [("warranty_rate", [])] and p.answer_type == "percent"


def test_t1_of_a_year_is_its_first_month():
    p0 = QueryPlan.model_validate({"intent": "value", "period": {"kind": "quarter", "year": 2026, "quarter": 1},
                                   "measures": [{"metric": "revenue"}]})
    p = month_written_as_t("Tổng dthu T1/2026 đc bnhiu?", p0)
    assert (p.period.kind, p.period.year, p.period.month) == ("month", 2026, 1)
    assert month_written_as_t("Quý 1/2026 dthu bnhiu? so với T1/2026", p0) == p0  # the quarter is named
    assert month_written_as_t("Q1/2026 dthu bnhiu?", p0) == p0


def test_warranty_visits_over_phones_typed_percent_is_repaired_to_the_rate():
    from datamate.nlu import _valid_plan
    raw = {"intent": "value", "period": {"kind": "quarter", "year": 2026, "quarter": 3}, "answer_type": "percent",
           "measures": [{"metric": "warranty_count", "filters": [{"field": "order_status", "value": "completed"}]},
                        {"metric": "quantity", "filters": [{"field": "order_status", "value": "completed"}]}]}
    p, error = _valid_plan(raw, "Quý 3/2026 lượt bảo hành so với số máy bán đc chiếm bnhiu %?")
    assert error and [m.metric for m in p.measures] == ["warranty_rate"]


# N103 (08/11): a particle read as a unit, today read as this month, an order amount read as a filter

from datamate.nlu.grounding import order_amount_named, particle_not_unit, today_not_this_month  # noqa: E402


def test_a_particle_is_no_unit():
    p = particle_not_unit(plan({"intent": "value", "measures": [{"metric": "revenue", "filters": [
        {"field": "unit", "value": "hỉ"}]}]}))
    assert p.measures[0].filters == []
    p0 = plan({"intent": "value", "measures": [{"metric": "quantity", "filters": [{"field": "unit", "value": "ly"}]}]})
    assert particle_not_unit(p0) == p0


def test_today_is_not_this_month():
    p0 = QueryPlan.model_validate({"intent": "value", "period": {"kind": "this_month"},
                                   "measures": [{"metric": "order_count"}]})
    assert today_not_this_month("Hom nay ban duoc may don?", p0).period.kind == "today"
    assert today_not_this_month("Tháng này tới hôm nay bán được mấy đơn?", p0) == p0


def test_an_order_amount_written_as_a_filter():
    q = "5/26 tiem thu phi ship duoc bao nhieu tien?"
    p = order_amount_named(q, plan({"intent": "value", "measures": [{"metric": "revenue", "filters": [
        {"field": "channel", "value": "Tại tiệm"}, {"field": "payment_method", "value": "Ship"}]}]}))
    assert [(m.metric, m.filters) for m in p.measures] == [("shipping_fee_total", [])]
    q = "06/2026 khach dung diem tru duoc bao nhieu tien?"
    p = order_amount_named(q, plan({"intent": "value", "measures": [{"metric": "revenue", "filters": [
        {"field": "customer", "value": "dùng điểm"}]}]}))
    assert [m.metric for m in p.measures] == ["points_discount"]
    p0 = plan({"intent": "value", "measures": [{"metric": "revenue", "filters": [
        {"field": "channel", "value": "giao hàng"}]}]})
    assert order_amount_named("Tháng 6 đơn giao hàng doanh thu bao nhiêu?", p0) == p0  # no fee asked


def test_customers_over_a_bound_written_with_a_count_measure_are_repaired():
    """N104: as the train plans of "trong số khách đã mua tháng X, bao nhiêu % mua từ 4 đơn trở lên"."""
    from datamate.nlu import _valid_plan
    raw = {"intent": "count_where", "period": {"kind": "month", "year": 2025, "month": 5},
           "threshold": {"entity": "customer", "metric": "order_count", "op": "gte", "value": 4.0},
           "measures": [{"metric": "customer_count", "filters": [{"field": "order_status", "value": "completed"}]}]}
    p, error = _valid_plan(raw, "Khách có mua th5/2025, mấy % mua từ 4 đơn trở lên?")
    assert error and p.measures == [] and p.threshold.as_share and p.answer_type == "percent"
    p, _ = _valid_plan(raw, "Th5/2025 có mấy khách mua từ 4 đơn trở lên?")
    assert not p.threshold.as_share and p.answer_type == "number"
    other = dict(raw, threshold=dict(raw["threshold"], metric="amount_due_total", op="gt", value=0))
    assert _valid_plan(other, "có mấy người trả góp còn kỳ quá hạn")[0] is None  # not a bound on orders or money


def test_cod_spelled_out():
    from datamate.nlu import linking
    assert linking.concept("payment_method", "xi ô đi") == "cod"
