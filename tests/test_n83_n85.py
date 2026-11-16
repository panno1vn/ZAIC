"""N83–N85 (08/11): questions the gates refused while the LLM had read them, or which ask what the data does not hold.
N83 a quality of people or suppliers (unanswerable, §7); N84 typing noise on the measure words; N85 plans of the
wrong shape for what the question asks, rewritten by the rule the rulebook gives."""
from datetime import date

from datamate import nlu
from datamate.contracts import QueryPlan
from datamate.decide import decide
from datamate.nlu import grounding
from datamate.verify import SUBJECTIVE_REASON

AS_OF = date(2026, 6, 30)
MONTH = {"kind": "month", "year": 2026, "month": 2}


def plan(raw: dict) -> QueryPlan:
    return QueryPlan.model_validate(raw)


def test_a_quality_the_data_does_not_record():
    """Train: the 5 questions this reads are all unanswerable ("nhân viên nào có tay nghề cao nhất tiệm")."""
    for q in ("Khách thân thiện nhất tháng 12/2025 là ai?", "Trong tháng 3/2026, ai là thợ nhiệt tình nhất?",
              "Xem giúp mình tháng 11/2025, nhà cung cấp uy tín của cửa hàng là ai?",
              "nhân viên nào có tay nghề cao nhất tiệm"):
        assert grounding.subjective_quality(q), q
    for q in ("Xem giúp mình tháng 11/2025, nhà cung cấp chính của cửa hàng là ai?",  # §5 defines it
              "Khách sộp nhất tháng 5/2026 là ai?", "Khách trung thành nhất tháng 5/2026 là ai?",  # §3
              "Th6/2025 ai là khách mua nhiều đơn nhất?", "Nhân viên bán giỏi nhất tháng 12/2025 là ai?"):
        assert not grounding.subjective_quality(q), q


class _Refused:
    """An LLM whose plan every gate refuses (a revenue plan for a question with no money word)."""

    def generate_json(self, messages, schema):
        return {"intent": "rank", "period": {"kind": "month", "year": 2025, "month": 12},
                "rank": {"entity": "customer", "by": "revenue"}}


def test_no_reading_of_a_quality_question_is_unanswerable(monkeypatch):
    monkeypatch.setattr(nlu, "GROUND_RETRY", False)
    from datamate.contracts import DataCard
    got = nlu.parse_question("Khách thân thiện nhất tháng 12/2025 là ai?", AS_OF, DataCard(), _Refused())
    assert got is not None and got.intent == "out_of_scope" and got.out_of_scope_reason == SUBJECTIVE_REASON
    assert nlu.parse_question("Khách mua nhiều tiền nhất tháng 12/2025 là ai?", AS_OF, DataCard(), _Refused()) \
        is not None  # a figure asked: the LLM's plan, not unanswerable


def test_the_subjective_reason_is_unanswerable_with_a_time():
    from datamate.contracts import Signals
    s = Signals(out_of_scope=True, subjective=True)
    assert decide(s, None).kind == "unanswerable"


def test_typing_noise_on_the_measure_words():
    count = {"intent": "count_where", "period": {"kind": "month", "year": 2025, "month": 11},
             "threshold": {"entity": "customer", "metric": "order_count", "op": "gte", "value": 4}}
    assert grounding.ungrounded_measures("Khách mua ít nhất 4 đơng trong tháng 11/2025 có mấy người?", plan(count)) == []
    money = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 9},
             "measures": [{"metric": "revenue", "filters": [{"field": "product", "value": "Nước giặt"}]}]}
    assert "metric=revenue" not in grounding.ungrounded_measures("Nước giặt tháng 9/2025, tiềng báng nhiêu z?", plan(money))
    rank = {"intent": "rank", "period": MONTH, "rank": {"entity": "customer", "by": "order_count"}}
    assert grounding.ungrounded_measures("Th2/2026 ai là khách mua nhiềuđơn nhất quán z?", plan(rank)) == []
    assert grounding.denoised("đồng hồ tiếng Anh") == "đồng hồ tiếng anh"  # real words left as they are


def test_a_count_of_items_not_their_list():
    lst = {"intent": "list_items", "list_spec": {"entity": "product", "condition": "unsold_in_period"},
           "period": {"kind": "last_n_days", "n": 7}}
    q = "7 ngày gần nhất có mấy mặt hàng ế, không bán được cái nào?"
    assert grounding.count_not_list(q, plan(lst)).list_spec.count is True
    assert grounding.count_not_list("7 ngày gần nhất những mặt hàng nào bị ế?", plan(lst)).list_spec.count is not True


def test_a_share_without_a_percent_word_is_the_figure():
    share = {"intent": "share", "period": MONTH,
             "measures": [{"metric": "revenue", "filters": [{"field": "product_group", "value": "bánh kẹo"}]}]}
    got = grounding.share_as_value("Nhóm bánh kẹo tháng 2 năm 2026 dthu nhiêu?", plan(share))
    assert got.intent == "value" and got.answer_type == "number"
    assert grounding.share_as_value("Nhóm bánh kẹo tháng 2/2026 chiếm bao nhiêu %?", plan(share)).intent == "share"


def test_rulebook_ranking_terms():
    bought = {"intent": "value", "period": MONTH, "measures": [{"metric": "purchase_amount"}]}
    got = grounding.rulebook_rank_terms("Tháng 2/2026, nhà cung cấp chính của cửa hàng là ai?", plan(bought))
    assert got.intent == "rank" and (got.rank.entity, got.rank.by, got.rank.k) == ("supplier", "receipt_count", 1)
    sop = {"intent": "rank", "period": MONTH, "rank": {"entity": "customer", "by": "revenue"}}
    got = grounding.rulebook_rank_terms("Khách sộp nhất tháng 2/2026 là ai?", plan(sop))
    assert (got.rank.by, got.rank.min_orders) == ("avg_order_value", 3)
    assert grounding.rulebook_rank_terms("Khách mua nhiều tiền nhất tháng 2/2026 là ai?", plan(sop)) == plan(sop)


def test_the_weekday_the_question_names():
    raw = {"intent": "value", "period": {"kind": "this_month"},
           "measures": [{"metric": "ticket_count", "filters": [{"field": "weekday", "value": "wed"}],
                         "aggregate": "avg_per_weekday"}]}
    got = grounding.weekday_as_stated("các ngày thứ 3 tháng này trung bình 1 ngày bao nhiêu lượt xe?", plan(raw))
    assert got.measures[0].filters[0].value == "tue"
    assert grounding.weekday_as_stated("cuối tuần tháng này bao nhiêu lượt xe?", plan(raw)) == plan(raw)  # two days


def test_overdue_instalments_are_the_overdue_amount():
    due = {"intent": "value", "period": {"kind": "until", "date": "2025-11-26"},
           "measures": [{"metric": "amount_due_total", "filters": [{"field": "payment_method", "value": "Trả góp"}]}]}
    got = grounding.unpaid_as_debt("Hết ngày 26/11/2025 tiền chậm góp của khách trả góp tổng cộng bnhiu?", plan(due))
    assert got.measures[0].metric == "overdue_amount"


class _OutOfScope:
    def generate_json(self, messages, schema):
        return {"intent": "out_of_scope", "out_of_scope_reason": "không có trong dữ liệu"}


def test_an_out_of_scope_reading_of_a_quality_question_is_unanswerable():
    from datamate.contracts import DataCard
    got = nlu.parse_question("Khách trung thực nhất tháng 10/2025 là ai?", AS_OF, DataCard(), _OutOfScope())
    assert got.out_of_scope_reason == SUBJECTIVE_REASON
    other = nlu.parse_question("Doanh thu tháng 10/2025 bao nhiêu?", AS_OF, DataCard(), _OutOfScope())
    assert other is None or other.out_of_scope_reason != SUBJECTIVE_REASON  # as before (here: the baseline disagrees)


def test_in_minus_out_is_one_figure_in_the_unit_asked():
    stock = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 3},
             "measures": [{"metric": "stock_qty", "filters": [{"field": "product", "value": "Telfast HD 180mg"}]}]}
    got = grounding.in_minus_out("Tháng 3/2025, số nhập trừ số bán của Telfast HD 180mg là bao nhiêu viên?", plan(stock))
    assert [m.metric for m in got.measures] == ["purchase_minus_sales"] and got.measures[0].unit == "vien"
    two = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 11}, "measures": [
        {"metric": "purchase_amount", "filters": [{"field": "product", "value": "Biosubtyl-II"}], "unit": "gói"},
        {"metric": "stock_qty", "filters": [{"field": "product", "value": "Biosubtyl-II"}], "unit": "gói"}]}
    got = grounding.in_minus_out("Biosubtyl-II T11/2025: tổng gói nhập trừ tổng gói bán?", plan(two))
    assert len(got.measures) == 1 and got.measures[0].metric == "purchase_minus_sales"
    assert grounding.in_minus_out("Tháng này nhập bao nhiêu tiền, bán được bao nhiêu?", plan(two)) == plan(two)


def test_the_age_the_question_states():
    """N87: debt_age_days written with a word for its value ("gt") takes the N the question states."""
    raw = {"intent": "value", "period": {"kind": "until", "date": "2025-12-28"},
           "measures": [{"metric": "debt_total", "filters": [{"field": "debt_age_days", "op": "gt", "value": "gt"}]}]}
    got = grounding.debt_age_from_question("Tới hết ngày 28/12/2025 khách còn nợ ở các đơn đã đặt quá 7 ngày bao nhiêu?",
                                           plan(raw))
    f = got.measures[0].filters[0]
    assert (f.op, f.value) == ("gt", 7.0)
    two = "nợ quá 7 ngày và quá 15 ngày mỗi nhóm bao nhiêu?"
    assert grounding.debt_age_from_question(two, plan(raw)) == plan(raw)  # two ages: left to the gates


def test_the_second_measure_is_the_whole_of_the_share():
    raw = {"intent": "share", "period": MONTH, "measures": [
        {"metric": "quantity", "filters": [{"field": "product_group", "value": "bỉm tã"}, {"field": "size", "value": "NB"}],
         "unit": "bịch"},
        {"metric": "quantity", "filters": [{"field": "product_group", "value": "bỉm tã"}], "unit": "bịch"}]}
    got = grounding.whole_as_share_of(plan(raw))
    assert len(got.measures) == 1 and got.share_of is not None and len(got.share_of.filters) == 1


def test_generic_words_are_no_filter():
    """N88: "Doanh thu tháng 1/2025 của sốp mình" (customer = sốp), "Nhập hàng T8/2025" (product = T8)."""
    import test_metrics_sales
    from datamate.contracts import ResolvedPlan
    raw = {"intent": "value", "period": {"kind": "this_month"},
           "measures": [{"metric": "revenue", "filters": [{"field": "customer", "value": "sốp"}]}]}
    r = ResolvedPlan(plan=plan(raw), as_of=AS_OF, period=test_metrics_sales.JUNE)
    assert nlu.drop_generic_filters(r, test_metrics_sales.shop()).plan.measures[0].filters == []
    month = dict(raw, measures=[{"metric": "revenue", "filters": [{"field": "product", "value": "T8"}]}])
    r = ResolvedPlan(plan=plan(month), as_of=AS_OF, period=test_metrics_sales.JUNE)
    assert nlu.drop_generic_filters(r, test_metrics_sales.shop()).plan.measures[0].filters == []
    phone = dict(raw, measures=[{"metric": "revenue", "filters": [{"field": "channel", "value": "đt"}]}])
    r = ResolvedPlan(plan=plan(phone), as_of=AS_OF, period=test_metrics_sales.JUNE)
    assert nlu.drop_generic_filters(r, test_metrics_sales.shop()).plan.measures[0].filters  # "đt" may be a phone


def test_gender_or_street_a_shop_does_not_record():
    """N89, train: the 10 such questions are all unanswerable, in shops whose README names neither column."""
    plain = "## Quy ước\n## Cột trong `don.csv`\n- **Khách**: tên khách\n"  # N176: a README with the section
    assert grounding.customer_trait_not_recorded("Tháng 11/2025 khách nam mua tổng cộng bao nhiêu tiền?", plain)
    assert grounding.customer_trait_not_recorded("có bnhiu khách hàng ở đường hậu giang", plain)
    assert not grounding.customer_trait_not_recorded("Khách năm 2025 mua bao nhiêu tiền?", plain)  # a year
    assert not grounding.customer_trait_not_recorded("Doanh thu tháng 11/2025?", plain)
    kept = plain + "- **Addr**: địa chỉ\n- **Giới tính**: giới tính khách\n"
    assert not grounding.customer_trait_not_recorded("khách ở đường Trần Não mua bao nhiêu?", kept)
    assert not grounding.customer_trait_not_recorded("khách nữ mua bao nhiêu?", kept)
    empty = plain + "- **Giới tính**: cột trống, không có dữ liệu\n"
    assert grounding.customer_trait_not_recorded("khách nữ mua bao nhiêu?", empty)


def test_a_month_before_its_year_is_no_top_k():
    """N91: "5-2026 khách nào mua nhiều đơn nhất" ranked with k = 5."""
    raw = {"intent": "rank", "period": {"kind": "month", "year": 2026, "month": 5},
           "rank": {"entity": "customer", "by": "order_count", "k": 5}}
    assert grounding.k_not_the_month("5-2026 khách nào mua nhiều đơn nhất hả?", plan(raw)).rank.k == 1
    assert grounding.k_not_the_month("Top 5 khách mua nhiều đơn nhất 5/2026", plan(raw)).rank.k == 5
    assert grounding.k_not_the_month("5 khách mua nhiều đơn nhất tháng 5/2026", plan(raw)).rank.k == 5


class _Tiem:
    def generate_json(self, messages, schema):
        return {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 9},
                "measures": [{"metric": "revenue", "filters": [{"field": "product", "value": "tiem"}]}]}


def test_a_generic_filter_is_no_disagreement_with_the_baseline(monkeypatch):
    from datamate.contracts import DataCard
    monkeypatch.setattr(nlu, "GROUND_RETRY", False)
    got = nlu.parse_question("Th9/2025 tiem tong doanh thu duoc bao nhieu vay?", AS_OF, DataCard(), _Tiem())
    assert got is not None and got.measures[0].metric == "revenue"  # the link step drops "tiem" (N88)


def test_a_group_written_under_the_other_attribute_field():
    """N93: "Nhóm gỏi" planned as category where the shop keeps it as product_group."""
    import pandas as pd
    import test_metrics_sales
    from datamate.contracts import ResolvedPlan
    db = test_metrics_sales.shop()
    db.tables["products"] = pd.DataFrame({"product_key": ["SP1"], "product_name": ["Gỏi cuốn"], "product_group": ["gỏi"]})
    raw = {"intent": "value", "period": {"kind": "this_month"},
           "measures": [{"metric": "revenue", "filters": [{"field": "category", "value": "gỏi"}]}]}
    r = ResolvedPlan(plan=plan(raw), as_of=AS_OF, period=test_metrics_sales.JUNE)
    assert nlu.attribute_in_its_field(r, db).plan.measures[0].filters[0].field == "product_group"
    other = dict(raw, measures=[{"metric": "revenue", "filters": [{"field": "category", "value": "lẩu"}]}])
    r = ResolvedPlan(plan=plan(other), as_of=AS_OF, period=test_metrics_sales.JUNE)
    assert nlu.attribute_in_its_field(r, db).plan.measures[0].filters[0].field == "category"  # found nowhere


def test_money_in_minus_money_out_is_not_the_quantity_figure():
    two = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 11}, "measures": [
        {"metric": "purchase_amount", "filters": [{"field": "product", "value": "Biosubtyl-II"}]},
        {"metric": "revenue", "filters": [{"field": "product", "value": "Biosubtyl-II"}]}]}
    q = "Biosubtyl-II T11/2025: tiền nhập trừ tiền bán được bao nhiêu?"
    assert grounding.in_minus_out(q, plan(two)) == plan(two)


def test_a_relative_month_that_is_not_the_month_written():
    """N95: "8/26 tiền bán ca chiều" (as of 19/09/2026) read as this month."""
    raw = {"intent": "value", "period": {"kind": "this_month"}, "measures": [{"metric": "revenue"}]}
    as_of = date(2026, 9, 19)
    assert "kind=this_month" in grounding.ungrounded_dates("8/26 tiền bán ca chiều là bnhiu?", plan(raw), as_of)
    assert grounding.ungrounded_dates("9/26 tiền bán là bnhiu?", plan(raw), as_of) == []  # this month written
    assert grounding.ungrounded_dates("Tháng này tiền bán là bnhiu?", plan(raw), as_of) == []  # none written
    last = dict(raw, period={"kind": "last_month"})
    assert grounding.ungrounded_dates("8/26 tiền bán là bnhiu?", plan(last), as_of) == []


def test_a_whole_after_a_share_of_written_as_the_part():
    """Full public run 08/11: share_of = the part (NB), the whole as a second measure."""
    part = {"metric": "quantity", "filters": [{"field": "product_group", "value": "bỉm tã"}, {"field": "size", "value": "NB"}],
            "unit": "bịch"}
    whole = {"metric": "quantity", "filters": [{"field": "product_group", "value": "bỉm tã"}], "unit": "bịch"}
    raw = {"intent": "share", "period": MONTH, "measures": [part, whole], "share_of": part}
    got = nlu.accept_plan("01/2026 tính tất cả các hãng, bỉm size NB được mấy % tổng số bịch bỉm bán ra nhỉ?", plan(raw),
                          AS_OF)
    assert got is not None and len(got.measures) == 1 and len(got.share_of.filters) == 1


def test_customers_with_an_overdue_instalment():
    """N96: "có bnhiu khách quá hạn góp" read as the debt in money on one full run."""
    raw = {"intent": "value", "period": {"kind": "day", "date": "2026-09-02"},
           "measures": [{"metric": "debt_amount", "filters": [{"field": "payment_method", "value": "Trả góp"}]}]}
    got = grounding.overdue_customers("Tại ngày 02/09/2026 có bnhiu khách quá hạn góp z?", plan(raw))
    assert got.measures[0].metric == "overdue_installment_count" and got.measures[0].filters
    money = "Tại ngày 02/09/2026 khách quá hạn góp bao nhiêu tiền?"
    assert grounding.overdue_customers(money, plan(raw)).measures[0].metric == "debt_amount"


def test_months_ranked_over_the_months_listed():
    """N97: "Th2, th3, th4/2026 tháng nào … nhất" ranked over February alone answered February whatever the data."""
    raw = {"intent": "rank", "period": {"kind": "month", "year": 2026, "month": 2},
           "rank": {"entity": "month", "by": "revenue", "k": 1}}
    got = nlu.accept_plan("Th2, th3, th4/2026 tháng nào tiệm bán được nhiều tiền nhất z?", plan(raw), AS_OF)
    assert got is not None and got.period.months == ["2026-02", "2026-03", "2026-04"]
    assert grounding.listed_months("tháng 2, 3 và 4/2026 tháng nào cao nhất") == ["2026-02", "2026-03", "2026-04"]
    assert nlu.accept_plan("Tháng 2/2026 tháng nào bán nhiều tiền nhất?", plan(raw), AS_OF) is None  # one month


def test_a_bound_every_object_passes_is_the_figure():
    """N98: "Xiaomi Redmi Note 14 tháng này bán được bnhiu chiếc" as products with quantity ≥ 0."""
    raw = {"intent": "count_where", "period": {"kind": "this_month"},
           "measures": [{"metric": "quantity", "filters": [{"field": "product_line", "value": "Xiaomi Redmi Note 14"}]}],
           "threshold": {"entity": "product", "metric": "quantity", "op": "gte", "value": 0}}
    got = grounding.threshold_as_value("Xiaomi Redmi Note 14 th này bán được bnhiu chiếc?", plan(raw))
    assert got.intent == "value" and got.measures[0].metric == "quantity" and got.measures[0].filters
    assert grounding.threshold_as_value("Tháng này có mấy mặt hàng bán được?", plan(raw)).intent == "count_where"
    members = {"intent": "count_where", "period": MONTH,
               "threshold": {"entity": "customer", "metric": "new_customer_count", "op": "gte", "value": 1}}
    got = grounding.threshold_as_value("Số khách thành viên đăng ký mới th 2/26?", plan(members))
    assert got.intent == "value" and got.measures[0].metric == "new_customer_count"


def test_orders_with_an_item_of_the_group_named():
    raw = {"intent": "count_where", "period": MONTH,
           "threshold": {"entity": "order", "metric": "order_presence", "op": "gte", "value": 1}}
    got = grounding.orders_with_group("Trong tháng 2 năm 2026, bao nhiêu đơn có ít nhất một mặt hàng nhóm dùng ngoài?",
                                      plan(raw))
    assert got.intent == "value" and got.measures[0].metric == "order_count"
    assert got.measures[0].filters[0].field == "product_group" and got.measures[0].filters[0].value == "dùng ngoài"


def test_a_series_of_months_written_as_category_filters():
    raw = {"intent": "series", "period": {"kind": "months", "months": ["2026-07", "2026-08", "2026-09"]}, "measures": [
        {"metric": "revenue", "filters": [{"field": "category", "value": f"th{m}"}]} for m in (7, 8, 9)]}
    got = grounding.series_months_as_filters("Dthu th7, th8, th9/2026 lần lượt mỗi tháng bao nhiêu z?", plan(raw))
    assert len(got.measures) == 1 and not got.measures[0].filters
    assert got.period.months == ["2026-07", "2026-08", "2026-09"]


def test_stray_age_and_window_filters():
    debtors = {"intent": "value", "period": {"kind": "until", "date": "2025-11-16"}, "measures": [
        {"metric": "debtor_count", "filters": [{"field": "debt_age_days", "op": "not_in", "value": "missing"}]}]}
    got = grounding.stray_numeric_filters("Đếm các khách còn thiếu tiền đến hết 16/11/2025 được bao nhiêu người?",
                                          plan(debtors))
    assert got.measures[0].filters == []
    lots = {"intent": "value", "period": {"kind": "range", "start": "2026-08-08", "end": "2026-12-06"}, "measures": [
        {"metric": "stock_value", "filters": [{"field": "expiry_within_days", "op": "eq", "value": 365}]}]}
    q = "Mấy lô còn tồn có hạn dùng từ 08/08/2026 tới hết 06/12/2026 đang đọng bnhiu tiền vốn?"
    assert grounding.stray_numeric_filters(q, plan(lots)).measures[0].filters == []
    kept = "Hàng hết hạn trong 365 ngày tới từ 08/08/2026 tới hết 06/12/2026 còn bao nhiêu tiền vốn?"
    assert grounding.stray_numeric_filters(kept, plan(lots)).measures[0].filters  # the question writes 365


def test_lots_expiring_counted():
    """N99, §6 Nhà thuốc: lots still holding goods with an expiry in the window."""
    import test_lots
    stock = {"intent": "value", "period": {"kind": "until", "date": "2026-07-30"}, "measures": [{"metric": "stock_qty"}]}
    got = grounding.lots_expiring_count("Theo tồn kho hôm nay, có mấy lô hàng còn tồn sẽ hết hạn từ nay đến hết ngày "
                                        "30/07/2026?", plan(stock), test_lots.D)
    assert got.intent == "list_items" and got.list_spec.entity == "lot" and got.list_spec.count
    assert test_lots.ask(got.model_dump(mode="json", exclude_none=True)) == 2  # L1 (10/07), L3 (05/07); L2 later
    days = grounding.lots_expiring_count("hiện còn bn lô chưa bán hết mà hạn dùng rơi vào 120 ngày tới",
                                         plan(stock), test_lots.D)
    assert days.list_spec.n == 120 and test_lots.ask(days.model_dump(mode="json", exclude_none=True)) == 3
