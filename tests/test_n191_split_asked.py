"""N191: "còn mấy hộp chẵn, mấy viên lẻ" read without unit_split takes the unit written before "chẵn" and
unit_split; a question without the pair, several measures, or money are left alone."""
from datamate.contracts import QueryPlan
from datamate.nlu.grounding import split_asked


def plan(metric="stock_qty", unit="viên", measures=1) -> QueryPlan:
    m = {"metric": metric, "filters": [{"field": "product", "value": "Savi Losartan 50mg"}], "unit": unit}
    return QueryPlan.model_validate({"intent": "value", "measures": [m] * measures, "period": {"kind": "today"}})


def test_the_pair_takes_the_whole_unit_and_the_split():
    out = split_asked("Cuối ngày hôm nay Savi Losartan 50mg còn mấy hộp chẵn, mấy viên lẻ?", plan()).measures[0]
    assert (out.unit, out.unit_split) == ("hop", True)
    out = split_asked("ton kho X cuoi ngay hom nay dc may vi chan va may vien le", plan()).measures[0]
    assert (out.unit, out.unit_split) == ("vi", True)


def test_left_alone_without_the_pair_or_on_other_plans():
    p = plan()
    assert split_asked("Cuối ngày hôm nay Savi Losartan 50mg còn bao nhiêu viên?", p) is p
    assert split_asked("còn mấy hộp chẵn?", p) is p  # no "lẻ"
    two = plan(measures=2)
    assert split_asked("còn mấy hộp chẵn, mấy viên lẻ?", two) is two
    money = plan(metric="revenue", unit=None)
    assert split_asked("còn mấy hộp chẵn, mấy viên lẻ?", money) is money
