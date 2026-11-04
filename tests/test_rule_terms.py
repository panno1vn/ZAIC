"""Terms a rulebook defines that no train version exists for (datamate/rules.unverified_terms)."""
from datamate import rules
from datamate.contracts import Signals
from datamate.decide import decide
from datamate.contracts import ExecResult

RULEBOOK = """## 3. Khách hàng
| Khái niệm | Cách tính |
|---|---|
| Khách trung thành nhất | khách có **nhiều ngày có mua nhất** trong kỳ |
| Nhân viên, thợ chăm chỉ nhất | người có **nhiều ngày làm việc nhất** trong kỳ |
| Bảo hành | phiếu bảo hành không tính doanh thu |
"""


def test_a_term_only_this_rulebook_defines_is_found_in_the_question():
    """Public 04/11: such terms would be read as the nearest train metric (most orders for "trung thành nhất")."""
    assert rules.unverified_terms("Khách nào trung thành nhất trong tháng 5?", RULEBOOK, []) == [
        "§3.khach_trung_thanh_nhat"]
    assert rules.unverified_terms("Nhân viên nào chăm chỉ nhất quý 1?", RULEBOOK, []) == [
        "§3.nhan_vien_tho_cham_chi_nhat"]
    assert rules.unverified_terms("Khách nào mua nhiều nhất?", RULEBOOK, []) == []
    assert rules.unverified_terms("Có bao nhiêu phiếu bảo hành?", RULEBOOK, []) == []  # one word: too common


def test_a_function_that_implements_the_term_answers():
    assert rules.unverified_terms("Khách nào trung thành nhất?", RULEBOOK, ["§3.khach_trung_thanh_nhat"]) == []


def test_terms_of_the_train_rulebook_are_not_held():
    train = open("data/train/rulebook.md", encoding="utf-8-sig").read() if __import__("os").path.exists(
        "data/train/rulebook.md") else ""
    assert rules.new_terms(train) == ()


def test_an_unverified_term_stops_the_answer():
    s = Signals(intent_known=True, mapping_ok=True, entities_ok=True, required_fields_present=True,
                period_coverage="full", sane=True, rules_unchanged=True, terms_known=False)
    r = ExecResult(value=1, answer_type="number", source="D1", function="x", rule_ids=["a"], requires=[])
    assert decide(s, r).kind == "abstain" and "terms" in decide(s, r).reason
    assert decide(s.model_copy(update={"terms_known": True}), r).kind == "answer"
