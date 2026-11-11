"""N148–N158 (09/11, toward 0,99): readings that add or change what the question says, rewritten from its own words;
"khách ở <Nơi>" not recorded; money words break a rulebook term; purchased quantity; fallback readings."""
from datetime import date

from datamate import nlu, rules
from datamate.contracts import QueryPlan
from datamate.nlu import baseline
from datamate.nlu.grounding import customer_trait_not_recorded

AS_OF = date(2026, 6, 30)


def _accept(question: str, raw: dict, as_of: date = AS_OF):
    return nlu.accept_plan(question, QueryPlan.model_validate(raw), as_of)


def _revenue(filters: list[dict]) -> dict:
    return {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 4},
            "measures": [{"metric": "revenue", "filters": filters}]}


def test_an_employee_code_the_question_never_writes_becomes_the_name_it_writes():
    p = _accept("cko e coi tổng tiền hàng kác đơn nv Từ Hùng Hằng bán trog th4/2025 jùm mik nha",
                _revenue([{"field": "employee", "value": "NV003"}]))
    assert p is not None and p.measures[0].filters[0].value == "Từ Hùng Hằng"
    # a code the question writes stays
    p = _accept("Tháng 4/2025 nhân viên mã NV003 bán được bao nhiêu tiền?", _revenue([{"field": "employee", "value": "NV003"}]))
    assert p is not None and p.measures[0].filters[0].value == "NV003"


def test_every_employee_written_out_for_all_of_them_is_the_table_of_all():
    raw = {"intent": "rank", "period": {"kind": "month", "year": 2025, "month": 11},
           "rank": {"entity": "employee", "by": "commission", "order": "desc"},
           "measures": [{"metric": "commission", "filters": [{"field": "employee", "value": "Hà Loan Đạt"},
                                                             {"field": "employee", "value": "Lương Chi Đức"}]}]}
    p = _accept("e ơi cko a xin cái bảng tien hoa hồng kua mọi thợ th11/2025 nha, xep tu cao xuong thap", raw)
    assert p is not None and not p.measures and p.rank.with_values and p.answer_type == "table"


def test_the_shop_asking_about_itself_is_no_channel():
    p = _accept("Nho xem 8/2025 doanh thu tiem minh duoc bao nhieu?",
                {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 8},
                 "measures": [{"metric": "revenue", "filters": [{"field": "channel", "value": "Tại tiệm"}]}]})
    assert p is not None and not p.measures[0].filters


def test_sold_out_goods_are_counted_as_out_of_stock():
    raw = {"intent": "rank", "period": {"kind": "today"}, "rank": {"entity": "product", "by": "quantity", "k": 1},
           "measures": [{"metric": "quantity"}]}
    p = _accept("Cuoi ngay hom nay co may mat hang dang chay hang?", raw)
    assert p is not None and p.list_spec.condition == "out_of_stock_end_of_day" and p.list_spec.count


def test_buying_in_is_purchases_money_or_count():
    p = _accept("Tháng 6/2025 tiệm cất hàng hết tổng cộng bao nhiêu tiền?",
                {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 6},
                 "measures": [{"metric": "revenue", "filters": [{"field": "order_status", "value": "completed"}]}]})
    assert p is not None and p.measures[0].metric == "purchase_amount" and not p.measures[0].filters
    p = _accept("Thang 6 nam 2025 nhap ve bnhiu vien Tiffy Dey hop 25 vi x 4 vien?",
                {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 6},
                 "measures": [{"metric": "purchase_amount", "unit": "viên",
                               "filters": [{"field": "product", "value": "Tiffy Dey hop 25 vi x 4 vien"}]}]})
    assert p is not None and p.measures[0].metric == "purchased_qty"


def test_payments_written_out_go_and_the_debt_age_comes_from_the_question():
    raw = {"intent": "value", "period": {"kind": "until", "date": "2025-06-09"},
           "measures": [{"metric": "debt_total", "filters": [
               {"field": "order_status", "value": "completed"}, {"field": "payment_method", "value": "COD"},
               {"field": "payment_method", "value": "Tiền mặt"}, {"field": "payment_method", "value": "Ví điện tử"}]}]}
    p = _accept("ad ơi tíh tới hết ngày 9/6/2025 á, tien khach kòn nợ o nhug don dat hon 7 ngay chua tra het la bnhiu",
                raw, date(2025, 6, 9))
    assert p is not None
    assert [(f.field, f.op, f.value) for f in p.measures[0].filters] == [("debt_age_days", "gt", 7.0)]


def test_a_customer_place_written_with_a_capital_is_an_address():
    q = "Tháng 8/2025 khách ở Trường Chinh mua nhiều tiềng hơn hay khách ở Lạc Long Quân?"
    assert customer_trait_not_recorded(q, "# Dữ liệu\n")
    assert not customer_trait_not_recorded(q, "- **Địa chỉ**: địa chỉ khách\n")
    assert not customer_trait_not_recorded("khách ở lại mua bao nhiêu tiền tháng 8/2025", "# Dữ liệu\n")


def test_money_between_the_words_is_no_rulebook_term():
    rb = "## 6\n| Từ | Nghĩa |\n|---|---|\n| Thợ làm nhiều nhất | theo **số lượt xe** |\n"
    assert rules.unverified_terms("tháng 3 thợ nào làm nhiều nhất", rb, [])
    assert not rules.unverified_terms("3/26 thợ mô làm ra nhiều tiền nhất rứa?", rb, [])


def test_fallback_readings_only_for_their_shapes():
    p = baseline.fallback("Khách có mua th5/2025, mấy % mua từ 4 đơn trở lên?")
    assert p.intent == "count_where" and p.threshold.as_share and p.threshold.value == 4
    p = baseline.fallback("nè, hết ngày 8/2/2026 shop mik kó mí ngừi trả góp kòn kỳ quá hạn chưa đóng")
    assert p.measures[0].metric == "overdue_installment_count" and p.period.date == "2026-02-08"
    assert baseline.fallback("doanh thu tháng 5/2025") is None
