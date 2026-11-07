"""Question templates (T1): template text of a question, plan shape, and why clustering uses token_sort_ratio."""
from rapidfuzz import fuzz

from datamate.contracts import QueryPlan
from datamate.nlu.templates import NameIndex, plan_shape, template_text, tokens

JUNE = {"kind": "month", "year": 2025, "month": 6}


def test_telex_typed_without_input_method_is_undone():
    assert tokens("thangs 7/2025 dduwowcj toongr tawng/giamr nawm naof bowts") == \
        ["thang", "7", "2025", "duoc", "tong", "tang", "giam", "nam", "nao", "bot"]


def test_one_template_whatever_the_spelling():
    variants = ["Tháng 5/2025 cửa hàng bán đc tổng cộng bao nhiêu tiền?",
                "thang 5/2025 cua hang ban duoc tong cong bn tien z",
                "e oi thangs 12/2026 cuwar hangf bans dduwowcj toongr coongj bao nhieeu tieenf"]
    assert {template_text(v) for v in variants} == {"thang # ban duoc tong cong bao nhieu tien"}


def test_numbers_dates_and_money_are_masked():
    assert template_text("đếm số đơn hàng tháng 2/2026 có tiền hàng từ 56.000 đồng trở lên") == \
        "dem so don hang thang # co tien hang tu # tien tro len"
    assert template_text("Đến hết ngày 17/12/2025 còn nợ bao nhiêu") == "den het ngay # con no bao nhieu"


def test_words_that_change_the_question_are_kept():
    assert "khong" in template_text("có bao nhiêu mặt hàng ko bán được cái nào").split()
    assert "chi phi" in template_text("trừ hết chi phí rồi thì tháng 1/2025 còn lãi ròng bao nhiêu")
    assert template_text("dthu bình quân mỗi đơn của quán") == "doanh thu trung binh moi don"


def test_names_masked_longest_first_one_word_names_only_after_a_cue():
    names = NameIndex([("nhom", "trà"), ("nhom", "trà sữa"), ("sp", "Trà đào (M)"), ("sp", "Coca Cola 330ml")])
    assert template_text("doanh thu nhóm trà sữa tháng 6", names) == "doanh thu nhom <NHOM> thang #"
    assert template_text("doanh thu nhóm trà tháng 6", names) == "doanh thu nhom <NHOM> thang #"
    assert template_text("tiền khách trả bớt nợ", names) == "tien khach tra bot no"  # "trả", not the group
    assert template_text("bán được bao nhiêu ly Trà đào (M)", names) == "ban duoc bao nhieu ly <SP>"
    # the tag is upper case so the abbreviation rule "sp" -> "san pham" leaves it alone
    assert template_text("doanh thu sp Coca Cola 330ml", names) == "doanh thu san pham <SP>"


def test_plan_shape_masks_values():
    a = QueryPlan.model_validate({"intent": "value", "period": JUNE, "measures": [
        {"metric": "revenue", "filters": [{"field": "product", "value": "Coca Cola 330ml"}]}]})
    b = QueryPlan.model_validate({"intent": "value", "period": {"kind": "this_month"}, "measures": [
        {"metric": "revenue", "filters": [{"field": "product", "value": "Pepsi"}]}]})
    assert plan_shape(a) == "value | revenue[product] | month"
    assert plan_shape(a, period=False) == plan_shape(b, period=False) == "value | revenue[product]"


def test_plan_shape_keeps_what_changes_the_answer_type():
    top1 = QueryPlan.model_validate({"intent": "rank", "period": JUNE, "rank": {"entity": "product", "by": "quantity"},
                                     "measures": [{"metric": "quantity"}]})
    top3 = QueryPlan.model_validate({"intent": "rank", "period": JUNE,
                                     "rank": {"entity": "product", "by": "quantity", "k": 3}})
    assert plan_shape(top1) == "rank | product by quantity k=1 desc | month"
    assert plan_shape(top3) == "rank | product by quantity k=k desc | month"


def test_token_set_ratio_would_merge_a_template_with_its_extension():
    """Why the clustering scores with token_sort_ratio: token_set_ratio gives 100 when one question's words are all in
    the other, so "số đơn" and "số đơn bị huỷ" would be one template (T1 risk, plan §10)."""
    orders = template_text("Tháng 6/2025 có bao nhiêu đơn hàng?")
    cancelled = template_text("Tháng 6/2025 có bao nhiêu đơn hàng bị huỷ?")
    assert fuzz.token_set_ratio(orders, cancelled) == 100
    assert fuzz.token_sort_ratio(orders, cancelled) < 90


def test_twin_gate_trusts_a_plan_shaped_like_a_verified_twin_of_another_business():
    from datamate.contracts import ExecResult, Signals
    from datamate.decide import decide
    from datamate.nlu.twins import TwinIndex, twin_shape

    orders = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "order_count"}],
                                       "period": {"kind": "today"}})
    revenue = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "revenue"}],
                                        "period": {"kind": "today"}})
    index = TwinIndex([{"id": "a", "business_id": "shop1", "text": template_text("hôm nay bán được mấy đơn"),
                        "shape": twin_shape(orders)}])
    text = template_text("hnay ban dc bn don z")
    assert index.twin(text, orders).score == 100.0
    assert index.twin(text, revenue).score == 0.0  # no verified question read that way
    assert index.twin(text, orders, exclude_business="shop1").score == 0.0  # leave-one-business-out
    assert index.twin(text, orders).passes(0) and not index.twin(text, revenue).passes(0)  # no twin never passes
    yesterday = orders.model_copy(update={"period": orders.period.model_copy(update={"kind": "yesterday"})})
    until = orders.model_copy(update={"period": orders.period.model_copy(update={"kind": "until"})})
    assert index.twin(text, yesterday).passes(0)  # one family: today / yesterday / a given day
    assert not index.twin(text, until).passes(0)  # "until" asks for stock, not one day's sales
    result = ExecResult(value=3, answer_type="number", source="D1")
    ok = dict(intent_known=True, mapping_ok=True, entities_ok=True, required_fields_present=True, sane=True,
              rules_unchanged=True, period_coverage="full")
    assert decide(Signals(**ok, twin_ok=None), result).kind == "answer"  # gate off
    assert decide(Signals(**ok, twin_ok=False), result).kind == "abstain"


def test_twin_gate_is_off_by_default():
    """N16/N24: on public (05/11) the 28 answers the gate held back were 24 right / 4 wrong. A gate pays only when
    more than half of what it holds back is wrong, so the run goes without it; train is scored without it too."""
    from datamate.pipeline import twin_check
    from datamate.predict import DEFAULT_CONFIG, load_config

    assert load_config(DEFAULT_CONFIG).twin_threshold is None
    plan = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "order_count"}],
                                     "period": {"kind": "today"}})
    assert twin_check("hôm nay bán được mấy đơn", plan, None, None, {}) is None  # off: never consulted
