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
