"""N110: the readings that came out blank on a full public run (08/11) and answered on the run before: "vâu chơ" as
voucher, "cất hàng" as buying goods in, a payment word as an item filter on what the customer pays, JSON cut at
max_tokens."""
import json
from datetime import date

from datamate.contracts import DataCard, QueryPlan
from datamate.nlu import llm_plan, plan_problems
from datamate.nlu.grounding import order_amount_named, order_amount_no_item, stocked_in_as_purchase

AS_OF = date(2026, 9, 19)


def plan(d: dict) -> QueryPlan:
    return QueryPlan.model_validate(d)


def test_vau_cho_is_voucher_even_under_a_filter_that_restates_nothing():
    q = "Tháng 12/2025 vâu chơ giảm cho khách tổng bao nhiêu?"
    raw = plan({"intent": "value", "period": {"kind": "month", "year": 2025, "month": 12},
                "measures": [{"metric": "revenue", "filters": [{"field": "is_warranty", "value": True}]}]})
    p = order_amount_named(q, raw)
    assert [(m.metric, m.filters) for m in p.measures] == [("voucher_discount", [])]
    p, problems = plan_problems(q, raw, AS_OF)
    assert problems == [] and p.measures[0].metric == "voucher_discount"


def test_revenue_kept_when_a_filter_has_ground_or_there_is_none():
    p0 = plan({"intent": "value", "measures": [{"metric": "revenue"}]})
    assert order_amount_named("Doanh thu tháng 6 sau khi trừ voucher là bao nhiêu?", p0) == p0
    p1 = plan({"intent": "value", "measures": [{"metric": "revenue", "filters": [
        {"field": "payment_method", "value": "chuyển khoản"}]}]})
    assert order_amount_named("Tháng 6 đơn chuyển khoản dùng voucher doanh thu bao nhiêu?", p1) == p1


def test_cat_hang_is_buying_goods_in():
    q = "Tháng 8/2026 quán cất hàng hết bao nhiêu tiền?"
    raw = plan({"intent": "value", "period": {"kind": "month", "year": 2026, "month": 8},
                "measures": [{"metric": "stock_value"}]})
    p = stocked_in_as_purchase(q, raw)
    assert [m.metric for m in p.measures] == ["purchase_amount"]
    p, problems = plan_problems(q, raw, AS_OF)
    assert problems == [] and p.measures[0].metric == "purchase_amount"


def test_stock_kept_when_the_question_asks_what_is_left():
    p0 = plan({"intent": "value", "measures": [{"metric": "stock_value"}]})
    assert stocked_in_as_purchase("Hàng cất trong kho còn bao nhiêu tiền?", p0) == p0
    assert stocked_in_as_purchase("Tồn kho cuối tháng 8 bao nhiêu tiền?", p0) == p0
    q = plan({"intent": "value", "measures": [{"metric": "stock_qty"}]})
    assert stocked_in_as_purchase("Tháng 8 cất hàng mấy thùng?", q) == q  # a count bought in: no metric


DUE = "Đơn bán 02/2026, trừ tiền bớt với tiền máy cũ thu lại rồi, khách phải trả tổng cộng bao nhiêu vậy?"


def _due(value: str) -> QueryPlan:
    return plan({"intent": "value", "period": {"kind": "month", "year": 2026, "month": 2},
                 "measures": [{"metric": "amount_due_total", "filters": [{"field": "category", "value": value}]}]})


def test_a_payment_word_as_item_filter_on_what_the_customer_pays_is_dropped():
    for value in ("trả góp", "mua chịu"):
        p, problems = plan_problems(DUE, _due(value), AS_OF)
        assert problems == [] and p.measures[0].filters == [], value


def test_an_item_or_a_stated_payment_word_is_kept():
    ip = _due("iPhone 15")  # an item written short in the question may fail the ground test: never dropped
    assert order_amount_no_item("Tháng 2/2026 ip15 khách phải trả bao nhiêu?", ip) == ip
    gop = _due("trả góp")
    assert order_amount_no_item("Tháng 2/2026 đơn trả góp khách phải trả bao nhiêu?", gop) == gop
    rev = plan({"intent": "value", "measures": [{"metric": "revenue", "filters": [
        {"field": "category", "value": "trả góp"}]}]})
    assert order_amount_no_item(DUE, rev) == rev  # revenue is split by item: not this rule's


GOOD = {"intent": "value", "period": {"kind": "month", "year": 2026, "month": 6}, "measures": [{"metric": "revenue"}]}
Q = "Doanh thu tháng 6/2026 bao nhiêu?"


class _Cut:
    """Cut output (`cuts` times), then the canned answers."""

    def __init__(self, cuts: int, answers: list[dict]):
        self.cuts, self.answers, self.calls = cuts, list(answers), []

    def generate_json(self, messages, schema):
        self.calls.append(messages)
        if len(self.calls) <= self.cuts:
            doc = '{"intent": "value", "note": "' + "lặp " * 500
            return json.loads(doc)
        return self.answers.pop(0)


def test_cut_json_is_asked_once_more():
    llm, trace = _Cut(1, [GOOD]), {}
    p = llm_plan(Q, AS_OF, DataCard(), llm, trace=trace)
    assert p is not None and p.measures[0].metric == "revenue"
    assert len(llm.calls) == 2 and trace["retry"] == "json" and "llm_error" not in trace
    assert llm.calls[1][-2]["role"] == "assistant" and len(llm.calls[1][-2]["content"]) <= 300


def test_cut_twice_is_blank_and_no_third_call_follows_the_retry():
    llm, trace = _Cut(2, []), {}
    assert llm_plan(Q, AS_OF, DataCard(), llm, trace=trace) is None
    assert len(llm.calls) == 2 and trace["llm_error"] == "JSONDecodeError" and trace["retry"] == "failed"
    bad = {"intent": "value", "measures": [{"metric": "no_such_metric"}]}  # invalid after the retry: no N78 call
    llm, trace = _Cut(1, [bad, GOOD]), {}
    assert llm_plan(Q, AS_OF, DataCard(), llm, trace=trace) is None
    assert len(llm.calls) == 2
