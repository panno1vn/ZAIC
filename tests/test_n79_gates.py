"""N79 (08/11): parts a plan leaves out that the question asks. Retrying refused plans (public, 76 refused) opened 34
answers, ~8 of them by dropping the very part the gate had refused (a unit, the whole of a share, the age of a debt, a
table, a number of instalments) or by reading a month as a top 5. These gates refuse such plans, first or retried."""
from datetime import date

from datamate import nlu
from datamate.contracts import QueryPlan, ResolvedPlan
from datamate.nlu import grounding
from test_metrics_sales import JUNE, shop

MONTH = {"kind": "month", "year": 2026, "month": 2}


def bad(question: str, raw: dict) -> list[str]:
    plan = QueryPlan.model_validate(raw)
    return grounding.ungrounded_filters(question, plan) + grounding.ungrounded_measures(question, plan)


def test_the_part_may_repeat_the_group_of_its_whole():
    """§6 Mẹ và bé: a size's share divides by every "bỉm tã"; the part written with the group too is grounded by it."""
    plan = {"intent": "share", "period": MONTH,
            "measures": [{"metric": "quantity", "filters": [{"field": "product_group", "value": "bỉm tã"},
                                                            {"field": "size", "value": "L"}]}],
            "share_of": {"metric": "quantity", "filters": [{"field": "product_group", "value": "bỉm tã"}]}}
    assert bad("T2/2026 bỉm size L chiếm mấy % số bịch bỉm bán ra?", plan) == []
    alone = {"intent": "value", "period": MONTH,  # no whole: the group needs its own words
             "measures": [{"metric": "quantity", "filters": [{"field": "product_group", "value": "bỉm tã"}]}]}
    assert "product_group=bỉm tã" in bad("T2/2026 bán mấy bịch bỉm?", alone)


def test_phones_revenue_is_not_the_whole_shop():
    plan = {"intent": "share", "period": MONTH,
            "measures": [{"metric": "revenue", "filters": [{"field": "category", "value": "máy cũ"}]}],
            "share_of": {"metric": "revenue", "filters": []}}
    assert "share_of=phones" in bad("T2/2026 máy cũ chiếm bao nhiêu % tiền bán máy?", plan)
    assert "share_of=phones" not in bad("T2/2026 máy cũ chiếm bao nhiêu % doanh thu cả shop?", plan)


def test_a_debt_of_aged_orders_needs_the_age():
    until = {"kind": "until", "date": "2025-12-20"}
    whole = {"intent": "value", "period": until, "measures": [{"metric": "debt_total"}]}
    q = "Tới hết ngày 20/12/2025, khách còn nợ bao nhiêu ở các đơn đã đặt quá 10 ngày?"
    assert "asks=debt_age" in bad(q, whole)
    aged = {"intent": "value", "period": until, "measures": [
        {"metric": "debt_total", "filters": [{"field": "debt_age_days", "op": "gt", "value": 10}]}]}
    assert "asks=debt_age" not in bad(q, aged)
    assert "asks=debt_age" not in bad("Tới hết ngày 20/12/2025 khách còn nợ bao nhiêu?", whole)


def test_a_number_of_instalments_is_no_money():
    plan = {"intent": "value", "period": {"kind": "until", "date": "2026-03-01"},
            "measures": [{"metric": "debt_amount", "filters": [{"field": "customer", "value": "Lê Văn A"}]}]}
    assert "asks=periods" in bad("Tới hôm nay khách Lê Văn A đã tới hạn bao nhiêu kỳ góp?", plan)
    assert "asks=periods" not in bad("Tới hôm nay khách Lê Văn A còn nợ bao nhiêu?", plan)


def test_a_ranking_needs_a_ranking_word():
    top5 = {"intent": "rank", "period": MONTH, "rank": {"entity": "customer", "by": "revenue", "k": 5}}
    assert "intent=rank" in bad("2-2026 khách nam mua bao nhiêu tiền?", top5)
    for q in ("T2/2026 top 5 khách mua nhiều tiền nhất?", "2/2026 5 khách nào mua nhìu tiền nhứt?",
              "th2/2026 5 khách mua caonhất là ai", "5 best seller tháng 2/2026 là những mặt hàng nào",
              "Nhà cung cấp chính tháng 2/2026 là ai?", "T2/2026 5 món bán chạy là những món gì"):
        assert "intent=rank" not in bad(q, top5), q


def test_every_object_is_not_the_first_one():
    first = {"intent": "rank", "period": MONTH, "rank": {"entity": "employee", "by": "commission"}}
    assert "asks=every" in bad("cho xin bảng tiền hoa hồng của mọi thợ th2/2026, xếp từ cao xuống thấp", first)
    assert "asks=every" not in bad("th2/2026 thợ nào được hoa hồng cao nhất?", first)
    table = {"intent": "rank", "period": MONTH, "rank": {"entity": "employee", "by": "commission", "with_values": True}}
    assert "asks=every" not in bad("cho xin bảng tiền hoa hồng của mọi thợ th2/2026, xếp từ cao xuống thấp", table)


def resolved(raw: dict) -> ResolvedPlan:
    return ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=date(2026, 6, 30), period=JUNE)


def test_a_count_in_a_unit_of_the_shop_takes_that_unit():
    """§3 "bán được bao nhiêu <đơn vị>": only the items whose base unit is that unit."""
    plain = {"intent": "value", "period": {"kind": "this_month"}, "measures": [{"metric": "quantity"}]}
    got = nlu.unit_from_question(resolved(plain), shop(), "Tháng này bán được nhiêu lon vậy?")
    assert got.plan.measures[0].unit == "lon"
    for q in ("Tháng này bán được bao nhiêu?", "Tháng này bán mấy ly và mấy lon?", "Tháng này bán được nhiều lắm không"):
        assert nlu.unit_from_question(resolved(plain), shop(), q).plan.measures[0].unit is None, q
    share = dict(plain, intent="share", share_of={"metric": "quantity"})
    assert nlu.unit_from_question(resolved(share), shop(), "bán mấy lon, chiếm bao nhiêu %").plan.measures[0].unit is None
    rank = {"intent": "rank", "period": {"kind": "this_month"}, "rank": {"entity": "product", "by": "quantity"},
            "measures": [{"metric": "quantity"}]}
    assert nlu.unit_from_question(resolved(rank), shop(), "món nào bán nhiều ly nhất").plan.measures[0].unit is None


def test_installments_not_paid_yet_are_a_debt():
    """§6 Điện thoại: the unpaid part of an instalment plan is what the customer still owes."""
    due = {"intent": "value", "period": {"kind": "until", "date": "2026-03-01"}, "measures": [
        {"metric": "amount_due_total", "filters": [{"field": "payment_method", "value": "Trả góp"}]}]}
    plan = QueryPlan.model_validate(due)
    q = "Tới hôm nay các hợp đồng trả góp còn bao nhiêu tiền chưa góp?"
    got = grounding.unpaid_as_debt(q, plan)
    assert got.measures[0].metric == "debt_total" and got.measures[0].filters == plan.measures[0].filters
    assert nlu.accept_plan(q, plan, date(2026, 3, 1)) is not None
    paid = "Tháng 2/2026 tổng tiền khách phải trả, tính cả phần còn nợ, là bao nhiêu?"
    assert grounding.unpaid_as_debt(paid, plan).measures[0].metric == "amount_due_total"


def test_which_one_is_a_name_not_a_one_row_table():
    one = {"intent": "rank", "period": MONTH, "rank": {"entity": "product", "by": "revenue", "k": 1, "with_values": True},
           "measures": [{"metric": "revenue", "filters": [{"field": "product_group", "value": "bánh"}]}]}
    q = "T2/2026 trong nhóm bánh, mặt hàng nào bán được nhiều tiền nhất?"
    got = grounding.one_name_no_values(q, QueryPlan.model_validate(one))
    assert got.rank.with_values is False and got.answer_type == "string"  # not the "table" derived before (08/11)
    ResolvedPlan(plan=got, as_of=date(2026, 6, 30), period=JUNE)  # a plan whose answer type agrees with it
    month = dict(one, rank={"entity": "month", "by": "revenue", "k": 1, "with_values": True}, measures=[])
    q2 = "So sánh 3/26, 4/26 và 5/26 xem tháng nào bán được nhiều tiền nhất"
    ResolvedPlan(plan=grounding.one_name_no_values(q2, QueryPlan.model_validate(month)), as_of=date(2026, 6, 30),
                 period=JUNE)
    for asks in ("T2/2026 trong nhóm bánh, mặt hàng nào bán được nhiều tiền nhất, bán bao nhiêu tiền?",
                 "T2/2026 mặt hàng nào bán nhiều tiền nhất, kèm doanh thu"):
        assert grounding.one_name_no_values(asks, QueryPlan.model_validate(one)).rank.with_values is True, asks
    top3 = dict(one, rank=dict(one["rank"], k=3))
    assert grounding.one_name_no_values(q, QueryPlan.model_validate(top3)).rank.with_values is True
    every = dict(one, rank=dict(one["rank"], k=None))
    got = grounding.one_name_no_values(q, QueryPlan.model_validate(every))
    assert got.rank.k == 1 and got.rank.with_values is False
    phones = "T2/2026 trong nhóm máy mới, mặt hàng nào bán được nhiều máy nhất?"  # "máy" is no "mấy"
    assert grounding.one_name_no_values(phones, QueryPlan.model_validate(one)).rank.with_values is False
    assert grounding.one_name_no_values("T2/2026 mặt hàng nào bán nhiều nhất, mấy cái?",
                                        QueryPlan.model_validate(one)).rank.with_values is True
    plural = "T2/2026 liệt kê các mặt hàng nào bán được nhiều tiền nhất"
    assert grounding.one_name_no_values(plural, QueryPlan.model_validate(every)).rank.k is None


def test_a_count_in_a_unit_the_shop_does_not_record_is_refused():
    """Public 08/11: "hôm qua bán được mấy lon" in a shop whose mapping records no unit counted every item."""
    import test_lots
    plain = {"intent": "value", "period": {"kind": "this_month"}, "measures": [{"metric": "quantity"}]}
    no_units = test_lots.shop()
    assert nlu.unit_not_recorded(resolved(plain), no_units, "Hôm qua bán được mấy lon?") == ["unit=lon"]
    assert nlu.unit_not_recorded(resolved(plain), no_units, "Hôm qua bán được mấy chiếc?") == []  # any item
    assert nlu.unit_not_recorded(resolved(plain), shop(), "Hôm qua bán được mấy chai?") == ["unit=chai"]  # not its unit
    assert nlu.unit_not_recorded(resolved(plain), shop(), "Hôm qua bán được bao nhiêu?") == []
    with_unit = {"intent": "value", "period": {"kind": "this_month"}, "measures": [{"metric": "quantity", "unit": "lon"}]}
    assert nlu.unit_not_recorded(resolved(with_unit), shop(), "Hôm qua bán được mấy lon?") == []
