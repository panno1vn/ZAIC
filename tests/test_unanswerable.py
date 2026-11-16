"""N28: a question whose period (or compared period) lies wholly outside the shop's data is unanswerable (§7 "kỳ nằm
hoàn toàn ngoài khoảng ngày có dữ liệu của shop … không trả lời được, không phải 0"); train 16 of 16 (05/11)."""
from datetime import date

import pandas as pd

from datamate.contracts import CanonicalDB, ExecResult, Mapping, QueryPlan, ResolvedPeriod, ResolvedPlan, Signals
from datamate.decide import decide
from datamate.formatter import to_line
from datamate.verify import R_OUTSIDE, collect_signals

SPAN = (date(2025, 5, 1), date(2026, 6, 30))
RULES = {r: True for r in R_OUTSIDE}


def _plan(period, compare=None, kind="month"):
    raw = {"intent": "value", "measures": [{"metric": "revenue"}], "period": {"kind": kind, "year": 2025, "month": 3}}
    if compare is not None:
        raw = {"intent": "compare", "measures": [{"metric": "revenue"}], "period": raw["period"],
               "compare": {"kind": "previous"}}
    return ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=date(2026, 6, 30),
                        period=ResolvedPeriod(start=period[0], end=period[1]),
                        compare_period=None if compare is None else ResolvedPeriod(start=compare[0], end=compare[1]),
                        linked={})


DB = CanonicalDB(tables={"orders": pd.DataFrame({"order_id": ["1"]})}, date_ranges={"orders": SPAN})


def test_a_period_before_the_data_or_a_compared_one_is_outside():
    march = (date(2025, 3, 1), date(2025, 3, 31))
    assert collect_signals(_plan(march), None, DB, Mapping(), RULES).outside_data is True
    may, april = (date(2025, 5, 1), date(2025, 5, 31)), (date(2025, 4, 1), date(2025, 4, 30))
    assert collect_signals(_plan(may, april), None, DB, Mapping(), RULES).outside_data is True  # "so với tháng trước"
    assert collect_signals(_plan(may), None, DB, Mapping(), RULES).outside_data is False
    partly = (date(2025, 4, 15), date(2025, 5, 15))  # §7: a period partly inside is worked out on what is inside
    assert collect_signals(_plan(partly), None, DB, Mapping(), RULES).outside_data is False
    # the rulebook row changed or missing: no decision rests on it
    assert collect_signals(_plan(march), None, DB, Mapping(), {}).outside_data is None


def _signals(**kw):
    base = dict(intent_known=True, mapping_ok=True, entities_ok=True, outside_data=True)
    return Signals(**{**base, **kw})


def test_unanswerable_only_when_the_question_was_read_and_its_data_is_usable():
    d = decide(_signals(), None)
    assert d.kind == "unanswerable"
    line = to_line("q1", d, None).to_dict()
    assert line["type"] == "unanswerable" and isinstance(line.get("reason", ""), str)
    for bad in (dict(mapping_ok=False), dict(entities_ok=False), dict(twin_ok=False), dict(terms_known=False),
                dict(out_of_scope=True), dict(outside_data=None)):
        assert decide(_signals(**bad), None).kind == "abstain", bad
    res = ExecResult(value=0, answer_type="number", source="D1")  # §7: no data is not 0
    assert decide(_signals(), res).kind == "unanswerable"


def test_a_question_out_of_scope_without_a_time_is_unanswerable():
    """N37, train 05/11: 8 questions read out of scope; the 7 with no time in them are unanswerable (skill, manners,
    dosage: §7 "shop không ghi loại thông tin câu hỏi cần"); the one with a month ("nhân viên bán giỏi nhất tháng
    12/2025") is a ranking the LLM misread: it still abstains."""
    from datetime import date

    from datamate.contracts import CanonicalDB, Mapping, QueryPlan, ResolvedPlan
    from datamate.decide import decide
    from datamate.verify import R_OUTSIDE, collect_signals

    plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "out_of_scope", "answer_type": "unanswerable",
                                                          "out_of_scope_reason": "chủ quan"}),
                        as_of=date(2026, 6, 30))
    rules = {r: True for r in R_OUTSIDE}

    def kind(question, rule_status=rules):
        s = collect_signals(plan, None, CanonicalDB(), Mapping(), rule_status, question)
        return decide(s, None).kind
    assert kind("Nhân viên Phùng Thu Trang làm việc có tận tâm với khách không?") == "unanswerable"
    assert kind("thuốc có hoạt chất nhôm phosphat người lớn nên uống mỗi lần mấy viên") == "unanswerable"
    assert kind("Nhân viên bán giỏi nhất tháng 12/2025 là ai?") == "abstain"
    assert kind("hôm qua ai bán giỏi nhất") == "abstain"
    assert kind("Nhân viên nào tận tâm nhất?", {}) == "abstain"  # §7 changed or not checked: no unanswerable
    assert kind("") == "abstain"  # no question given (old callers): as before


def test_purchases_a_shop_does_not_record_are_unanswerable():
    """N38, train 05/11: the README conventions name "**Nhập hàng**" in every shop recording purchases; the 104
    purchase questions of those shops are answerable, the 5 of the shops without it all unanswerable (§7 "shop không
    ghi loại thông tin câu hỏi cần")."""
    from datetime import date

    import pandas as pd

    from datamate.contracts import CanonicalDB, Mapping, QueryPlan, ResolvedPeriod, ResolvedPlan
    from datamate.decide import decide
    from datamate.mapping.build import readme_conventions
    from datamate.verify import R_OUTSIDE, collect_signals

    readme = "# Dữ liệu\n\n## Quy ước\n- Dữ liệu có đến hết 30/06/2026.\n- **Giá vốn**: **Giá vốn** là giá vốn.\n"
    assert readme_conventions(readme) == ("gia von",)
    assert readme_conventions("# Dữ liệu\n") is None  # no conventions at all: nothing is known to be missing
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "purchase_amount"}],
                                                       "period": {"kind": "this_month"}}),
                        as_of=date(2026, 6, 30), period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30)))
    rules = {r: True for r in R_OUTSIDE}
    orders = pd.DataFrame({"order_id": ["D1"], "order_time": [pd.Timestamp("2026-06-01")]})

    def kind(conventions, purchases=False, rule_status=rules):
        db = CanonicalDB(tables={"orders": orders}, conventions=conventions,
                         date_ranges={"orders": (date(2026, 1, 1), date(2026, 6, 30))})
        if purchases:
            db.tables["purchases"] = pd.DataFrame({"receipt_id": ["P1"], "unit_cost": [1.0]})
        m = Mapping(checks=[])
        s = collect_signals(plan, None, db, m, rule_status, "tháng này nhập hàng hết bao nhiêu tiền")
        s.mapping_ok = True
        return decide(s, None).kind
    assert kind(("gia von",)) == "unanswerable"
    assert kind(("gia von", "nhap hang")) == "abstain"  # recorded: a missing figure is ours to find
    assert kind(("gia von",), purchases=True) == "abstain"  # a purchase table was mapped
    assert kind(None) == "abstain"  # the README writes no conventions
    assert kind(("gia von",), rule_status={}) == "abstain"  # §7 changed


# ---- N176: a README without a "## Quy ước" section proves no absence
def test_thin_readme_never_says_not_recorded():
    from datamate.contracts import CanonicalDB
    from datamate.nlu.grounding import customer_trait_not_recorded
    from datamate.verify import not_recorded
    q = "Công nợ của khách Lan tính đến hết hôm nay là bao nhiêu?"
    assert not_recorded(None, q, CanonicalDB(readme="# Cửa hàng ABC", conventions=None)) is None
    assert customer_trait_not_recorded("khách nữ chiếm bao nhiêu % doanh thu", "# Cửa hàng ABC") is False
    assert customer_trait_not_recorded("khách nữ chiếm bao nhiêu % doanh thu", "# Cửa hàng ABC\n## Quy ước\n") is True
