"""N159–N169 (N163 / N164 in test_metrics_debt.py): §7 "shop không ghi loại thông tin câu hỏi cần" — "quý mến"
is no quarter, "ghi số lượng" is no debt record, channel / payment method / customer group / expiry the shop does
not record are unanswerable; plan readings rewritten from the question's words (N165–N169)."""
import re

import pandas as pd

from datamate import nlu
from datamate.contracts import CanonicalDB, QueryPlan
from datamate.verify import _TIME, _fold, not_recorded

README = "# Dữ liệu\n\n## Cột trong `ban.csv`\n- **Mã đơn**: mã đơn\n- **Hàng**: tên hàng\n- **Khách**: tên khách\n"
ORDERS = pd.DataFrame({"order_key": ["d1"], "customer_key": ["k1"]})


def db(readme: str = README, **tables) -> CanonicalDB:
    return CanonicalDB(tables={"orders": ORDERS, **tables}, readme=readme)


def plan(**kw) -> QueryPlan:
    return QueryPlan.model_validate({"period": {"kind": "month", "year": 2025, "month": 10}, **kw})


def revenue_by(field: str, *values: str) -> QueryPlan:
    return plan(intent="value", answer_type="list" if len(values) > 1 else "number",
                measures=[{"metric": "revenue", "filters": [{"field": field, "value": v}]} for v in values])


def test_quy_men_is_no_quarter():
    assert not _TIME.search(_fold("Ai trong cửa hàng đc khách quý mến nhất?"))
    for q in ("số đơn quý 2/2026", "doanh thu quý này", "quý trước bán được bao nhiêu"):
        assert _TIME.search(_fold(q)), q


def test_a_written_quantity_is_no_debt_record():
    p = plan(intent="rank", period={"kind": "until", "date": "2026-06-24"}, measures=[{"metric": "debt_amount"}],
             rank={"entity": "customer", "by": "debt_amount", "k": 3, "with_values": True}, answer_type="table")
    quantity = README + "\n## Quy ước\n- **Trả hàng**: hàng trả ghi số lượng âm, cùng mã đơn\n"
    assert not_recorded(p, "liệt kê 3 khách nợ nhiều nhất", db(quantity)) == "công nợ"
    assert not_recorded(p, "liệt kê 3 khách nợ nhiều nhất", db(README + "- **Bán ghi sổ**: đơn bán chịu\n")) is None


def test_a_channel_or_payment_method_the_shop_does_not_record():
    q = "So dthu các đơn trả bằng COD với doanh thu các đơn trả bằng ví điện tử tháng 10/2025"
    assert not_recorded(revenue_by("payment_method", "COD", "ví điện tử"), q, db()) == "hình thức thanh toán"
    paid = db(orders=ORDERS.assign(payment_method=["cod"]))
    assert not_recorded(revenue_by("payment_method", "COD", "ví điện tử"), q, paid) is None
    written = db(README + "- **HTTT**: hình thức thanh toán (tiền mặt, chuyển khoản, COD)\n")
    assert not_recorded(revenue_by("payment_method", "COD", "ví điện tử"), q, written) is None
    q = "tháng này, dthu các đơn bán tại quầy là nhiêu, doanh thu các đơn bán qua zalo oa là bao nhiêu"
    assert not_recorded(revenue_by("channel", "tại quầy", "Zalo OA"), q, db()) == "kênh bán"
    assert not_recorded(revenue_by("channel", "tại quầy", "Zalo OA"), q,
                        db(README + "- **Kênh**: kênh bán\n")) is None
    # a misread value that is no payment code is no payment question
    assert not_recorded(revenue_by("payment_method", "đơn"), "hqua có tổng cộng nhiêu ddown", db()) is None


def test_a_customer_group_the_shop_does_not_record():
    p = plan(intent="share", answer_type="percent",
             measures=[{"metric": "revenue", "filters": [{"field": "customer_group", "value": "thân thiết"}]}])
    q = "Tháng này, doanh thu từ khách nhóm thân thiết chiếm bao nhiêu phần trăm tổng doanh thu?"
    assert not_recorded(p, q, db()) == "nhóm khách"
    assert not_recorded(p, q, db(README + "- **Nhóm khách hàng**: VIP, thân thiết\n")) is None
    assert not_recorded(p, q, db(customers=pd.DataFrame({"customer_key": ["k1"], "customer_group": ["VIP"]}))) is None


def test_expiry_the_shop_does_not_keep():
    p = plan(intent="list_items", period={"kind": "range", "start": "2026-05-20", "end": "2026-08-18"},
             list_spec={"entity": "product", "condition": "expiring_within"}, answer_type="list")
    q = "những sp nào đang còn hàng có hạn dùng từ 20/05/2026 đến hết 18/08/2026"
    assert not_recorded(p, q, db()) == "hạn dùng"
    assert not_recorded(p, q, db(README + "- **HSD**: hạn sử dụng của lô\n")) is None
    assert not_recorded(p, q, db(lots=pd.DataFrame({"lot_key": ["L1"], "expiry_date": ["2026-07-01"]}))) is None
    assert re.search("hạn dùng", q)


def test_an_average_per_day_the_question_never_asks_for_is_the_total():
    raw = {"intent": "compare", "period": {"kind": "days_from", "date": "2026-02-05", "n": 30},
           "compare": {"kind": "before_days_from"},
           "measures": [{"metric": "quantity", "unit": "ly", "aggregate": "avg_per_day",
                         "filters": [{"field": "product", "value": "Latte (L)"}]}]}
    q = ("So số ly Latte (L) bán ra trong 30 ngày kể từ ngày 05/02/2026, ngày tăng giá lên 53.500đ, với 30 ngày ngay "
         "trước ngày đó: tăng hay giảm bao nhiêu %?")
    p = nlu.accept_plan(q, QueryPlan.model_validate(raw), None)
    assert p is not None and p.measures[0].aggregate == "total"
    # an average the question asks for stays
    q = "Kể từ ngày 05/02/2026 tăng giá Latte (L), trung bình mỗi ngày 30 ngày sau bán nhiều hơn 30 ngày trước bao nhiêu %?"
    p = nlu.accept_plan(q, QueryPlan.model_validate(raw), None)
    assert p is None or p.measures[0].aggregate == "avg_per_day"


def test_a_month_note_beside_the_compared_periods_goes():
    raw = {"intent": "compare", "period": {"kind": "month", "year": 2026, "month": 5},
           "compare": {"kind": "same_period_last_year"},
           "measures": [{"metric": "revenue", "filters": [{"field": "other", "value": "thang 5/2025"}]}]}
    p = nlu.accept_plan("dthu thang 5/2026 so vs thang 5/2025 tang hay giam bao nhieu %", QueryPlan.model_validate(raw))
    assert p is not None and not p.measures[0].filters and p.compare.kind == "same_period_last_year"


def test_debt_added_is_what_the_question_calls_no_them():
    raw = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 8}, "answer_type": "list",
           "measures": [{"metric": "debt_amount", "filters": [{"field": "customer", "value": "Ha Anh Tam"}]},
                        {"metric": "debt_paid", "filters": [{"field": "customer", "value": "Ha Anh Tam"}]}]}
    q = "cho hoi khach Ha Anh Tam thang 8/2025 no them bao nhiu, tra dc bao nhieu do"
    p = nlu.accept_plan(q, QueryPlan.model_validate(raw))
    assert p is not None and [m.metric for m in p.measures] == ["debt_added", "debt_paid"]
    # what is still owed at the end of a day stays
    until = {**raw, "period": {"kind": "until", "date": "2025-08-31"}}
    p = nlu.accept_plan("đến hết 31/8/2025 khách Ha Anh Tam còn nợ bao nhiêu, nợ thêm bao nhiêu", QueryPlan.model_validate(until))
    assert p is None or p.measures[0].metric == "debt_amount"


def test_the_nearest_expiry_of_one_product_is_its_date():
    raw = {"intent": "rank", "period": {"kind": "this_month"}, "answer_type": "table",
           "rank": {"entity": "product", "by": "nearest_expiry", "with_values": True},
           "measures": [{"metric": "nearest_expiry", "filters": [{"field": "product", "value": "acyclovir kem 5%"}]}]}
    p = nlu.accept_plan("lô acyclovir kem 5% gần hết hạn nhất có hạn dùng ngày nào", QueryPlan.model_validate(raw))
    assert p is not None and p.intent == "value" and p.rank is None and p.answer_type == "date"


def test_the_base_of_a_comparison_written_twice_is_written_once():
    """N169: the morning both as a second measure and as the comparison's filter."""
    raw = {"intent": "compare", "period": {"kind": "month", "year": 2025, "month": 12}, "answer_type": "list",
           "measures": [{"metric": "revenue", "filters": [{"field": "shift", "value": "afternoon"}]},
                        {"metric": "revenue", "filters": [{"field": "shift", "value": "morning"}]}],
           "compare": {"kind": "filter", "filters": [{"field": "shift", "value": "morning"}]}}
    q = "Xem giúp tháng 12/2025, doanh thu ca chiều tăng hay giảm bao nhiêu % so với ca sáng?"
    p = nlu.accept_plan(q, QueryPlan.model_validate(raw))
    assert p is not None and len(p.measures) == 1 and p.answer_type == "percent"
