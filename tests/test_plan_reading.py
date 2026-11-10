"""N30: plans the grounding gate threw away although the question was read right (05/11, 25 train questions the LLM
read with no plan): a status filter that only restates §1's default, and payment words the linker knows."""
from datetime import date

from datamate import nlu
from datamate.contracts import QueryPlan

AS_OF = date(2026, 6, 30)


def _filters(question: str, raw: dict):
    plan = nlu.accept_plan(question, QueryPlan.model_validate(raw), AS_OF)
    return None if plan is None else [[f"{f.field}={f.value}" for f in m.filters] for m in plan.measures]


def count(status) -> dict:
    return {"intent": "value", "period": {"kind": "yesterday"},
            "measures": [{"metric": "order_count", "filters": [{"field": "order_status", "value": status}]}]}


def revenue(payment: str) -> dict:
    return {"intent": "value", "period": {"kind": "this_month"},
            "measures": [{"metric": "revenue", "filters": [{"field": "payment_method", "value": payment}]}]}


def test_a_status_filter_restating_the_default_is_dropped_only_when_no_status_is_named():
    assert _filters("e bua qua cua hang ban duoc may don", count("completed")) == [[]]
    assert _filters("bữa qua có tổng cộng bao nhiu ddown", count(["completed", "delivering"])) == [[]]
    # a status the question names is the question's: kept (the metrics then abstain on it)
    assert _filters("so don hoan thanh hom qua", count("completed")) == [["order_status=completed"]]
    # cancelled orders are no default: an ungrounded cancelled filter still throws the plan away
    assert _filters("e bua qua cua hang ban duoc may don", count("cancelled")) is None


def test_payment_words_of_the_linker_ground_the_filter():
    assert _filters("cho toi biet dthu cac don tra bang tien tuoi thang nay", revenue("tiền mặt")) is not None
    assert _filters("dthu cac don tra bang ck thang nay", revenue("chuyển khoản")) is not None
    assert _filters("cho toi biet dthu thang nay", revenue("tiền mặt")) is None  # no payment word at all


def test_a_doctors_prescription_grounds_the_prescription_filter():
    raw = {"intent": "value", "period": {"kind": "month", "year": 2026, "month": 3},
           "measures": [{"metric": "revenue", "filters": [{"field": "prescription", "value": False}]}]}
    assert _filters("thang 3/2026 ban hang khong can don bac si duoc bao nhieu tien", raw) == [["prescription=False"]]


def test_a_filter_restating_the_measure_is_dropped():
    """N34, train 05/11: "tiền khách trả bớt nợ" read as debt_paid with payment_method = "bớt nợ" (13 questions), "xe
    chở được bao nhiêu đợt hàng" as delivery_count with vehicle_model = "xe chở" (6), "tính theo ly" as a unit filter
    (10). No function takes such a filter, so the plans could only abstain."""
    from datamate.contracts import QueryPlan
    from datamate.nlu.grounding import drop_restated_metric

    def plan(metric, field, value):
        return QueryPlan.model_validate({"intent": "value", "period": {"kind": "this_month"},
                                         "measures": [{"metric": metric, "filters": [{"field": field, "value": value}]}]})
    for metric, field, value in [("debt_paid", "payment_method", "bớt nợ"), ("debt_paid", "payment_method", "mua chiu"),
                                 ("debt_paid", "payment_method", "trả nợ"), ("delivery_count", "vehicle_model", "xe"),
                                 ("delivery_count", "vehicle_model", "xe chở hàng")]:
        assert drop_restated_metric(plan(metric, field, value)).measures[0].filters == []
    kept = [("revenue", "payment_method", "mua chịu"), ("delivery_count", "vehicle_model", "xe tải 2 tấn"),
            ("debt_paid", "payment_method", "chuyển khoản")]
    for metric, field, value in kept:  # a real filter: another metric, a named vehicle, a payment way
        assert drop_restated_metric(plan(metric, field, value)).measures[0].filters != []
    moved = drop_restated_metric(plan("quantity", "unit", "ly")).measures[0]
    assert moved.filters == [] and moved.unit == "ly"  # §3 "bao nhiêu <đơn vị>": the measure's unit
    other = QueryPlan.model_validate({"intent": "value", "period": {"kind": "this_month"}, "measures": [
        {"metric": "quantity", "unit": "chai", "filters": [{"field": "unit", "value": "thùng"}]}]})
    assert drop_restated_metric(other).measures[0].filters != []  # two units: no guess


def test_a_name_of_the_shop_the_plan_leaves_out_stops_the_question():
    """N36, train 05/11: "khách cao thu hạnh ghi nợ thêm bao nhiêu" read without the customer (the LLM wrote a status
    filter instead): the shop's total was answered for one customer's. A customer or product name of the shop (two
    words or more) in the question with no filter of that field in the plan: the question abstains."""
    from datetime import date

    import pandas as pd

    from datamate.contracts import CanonicalDB, Mapping, QueryPlan, ResolvedPlan
    from datamate.nlu import link_entities
    from datamate.verify import collect_signals

    db = CanonicalDB(tables={
        "orders": pd.DataFrame({"order_id": ["D1"], "customer_key": ["KH1"], "customer_name": ["Cao Thu Hạnh"]}),
        "customers": pd.DataFrame({"customer_key": ["KH1"], "customer_name": ["Cao Thu Hạnh"]}),
        "lines": pd.DataFrame({"order_id": ["D1"], "product_key": ["SP1"], "product_name": ["Cà phê sữa"]}),
        "products": pd.DataFrame({"product_key": ["SP1"], "product_name": ["Cà phê sữa"],
                                  "product_group": ["cà phê sữa"]})})

    def resolved(raw):
        return ResolvedPlan(plan=QueryPlan.model_validate({"period": {"kind": "this_month"}, **raw}),
                            as_of=date(2026, 7, 31))
    total = {"intent": "value", "measures": [{"metric": "debt_added"}]}
    # N173: written right after "khách", the name becomes the filter; written elsewhere, N36 still stops the question
    added = link_entities(resolved(total), db, "e thang 7/2026 khach cao thu hanh ghi no them bao nhieu")
    assert added.omitted == [] and [f.value for f in added.plan.measures[0].filters] == ["cao thu hanh"]
    q = "e thang 7/2026 cao thu hanh ghi no them bao nhieu"
    assert link_entities(resolved(total), db, q).omitted == ["customer=cao thu hanh"]
    one = {"intent": "value", "measures": [{"metric": "debt_added", "filters": [
        {"field": "customer", "value": "cao thu hanh"}]}]}
    assert link_entities(resolved(one), db, q).omitted == []
    group = {"intent": "value", "measures": [{"metric": "revenue", "filters": [
        {"field": "product_group", "value": "cà phê sữa"}]}]}  # the name is another filter's value
    assert link_entities(resolved(group), db, "doanh thu nhóm cà phê sữa tháng này").omitted == []
    assert link_entities(resolved(total), db, "tháng này khách ghi nợ thêm bao nhiêu").omitted == []
    s = collect_signals(link_entities(resolved(total), db, q), None, db, Mapping(), {})
    assert s.entities_ok is False
