"""N159: the rulebook check keeps a rule whose accepted text is still there word for word (sentences or list items
added), and finds rules by name when the sections are numbered otherwise. The private rulebook is read by the frozen
image: public's three edited train rows and a renumbered rulebook must not switch the functions off."""
import json
import re
from pathlib import Path

import pytest

from datamate import rules
from datamate.rules import check_rules, extends, new_terms, parse_rulebook

DATA = Path(__file__).resolve().parents[1] / "data"
OLD = "theo **ngày đặt**, không theo ngày giao hay ngày thu tiền"
SAMPLE = """# Rulebook

## 1. Đơn hàng
| Luật | Mặc định |
|---|---|
| Đơn thuộc kỳ nào | theo **ngày đặt**, không theo ngày giao hay ngày thu tiền |
| Khách sộp | chỉ xét khách có **từ 3 đơn trở lên** |

## 2. Thời gian
| Luật | Mặc định |
|---|---|
| Đến hết ngày X | hỏi số còn lại (còn nợ, còn tồn, còn hàng…): tình trạng lúc hết ngày đó |
"""


def _shift(text: str) -> str:
    return re.sub(r"^(##\s*)(\d+)", lambda m: m.group(1) + str(int(m.group(2)) + 1), text, flags=re.M)


def test_added_sentence_or_list_item_keeps_the_rule():
    assert extends(OLD, OLD + ". Đơn trả hàng sau kỳ, kể cả trả sau hôm nay, vẫn bị loại khỏi doanh thu kỳ đặt")
    assert extends("Số đợt giao trong tháng X = số đợt có ngày giao trong tháng X",
                   "tính đến hết hôm nay. Số đợt giao trong tháng X = số đợt có ngày giao trong tháng X. Đợt đã chở vẫn tính")
    assert extends("hỏi số còn lại (còn nợ, còn tồn, còn hàng…): tình trạng lúc hết ngày đó",
                   "hỏi số còn lại (còn nợ, còn tồn, còn hàng, chưa giao…): tình trạng lúc hết ngày đó")


def test_changed_word_number_or_narrowing_is_a_changed_rule():
    assert not extends(OLD, OLD.replace("ngày đặt", "ngày giao"))
    assert not extends("chỉ xét khách có từ 3 đơn trở lên", "chỉ xét khách có từ 5 đơn trở lên")
    assert not extends("tính đơn huỷ", "tính đơn không huỷ")  # a word inserted inside the sentence
    assert not extends("còn nợ, còn tồn", "còn nợ, không tính còn tồn")  # a narrowing list item
    assert not extends(OLD, "theo ngày đặt")  # words removed
    assert not extends("", "bất kỳ")


def test_extended_rows_pass_and_changed_rows_fail():
    ref = {rid: r.text for rid, r in parse_rulebook(SAMPLE).items()}
    ids = tuple(ref)
    added = SAMPLE.replace("thu tiền |", "thu tiền. Đơn trả hàng sau kỳ vẫn bị loại |")
    assert all(check_rules(added, ids, ref).values())
    changed = SAMPLE.replace("từ 3 đơn", "từ 5 đơn")
    assert check_rules(changed, ids, ref)["§1.khach_sop"] is False


def test_renumbered_sections_find_their_rules():
    ref = {rid: r.text for rid, r in parse_rulebook(SAMPLE).items()}
    status = check_rules(_shift(SAMPLE), tuple(ref), ref)
    assert all(status.values()), status


@pytest.mark.skipif(not (DATA / "public_test" / "rulebook.md").exists(), reason="cần data/")
def test_public_first_contact_and_renumbered():
    """With only the train versions (as when public arrived) every train rule public still has passes; renumbering
    public's sections changes nothing; no train term becomes a new one."""
    from datamate.pipeline import rule_ids
    public = (DATA / "public_test" / "rulebook.md").read_text(encoding="utf-8-sig")
    raw = json.loads(rules.REFERENCE.read_text(encoding="utf-8"))
    train_only = {rid: [v["text"] for v in e["versions"] if v.get("source") == "train"] for rid, e in raw.items()}
    ids = rule_ids()
    first = check_rules(public, ids, train_only)
    present = set(rules.canonical_rows(parse_rulebook(public), train_only))
    assert [r for r in ids if train_only.get(r) and r in present and not first[r]] == []
    assert check_rules(_shift(public), ids) == check_rules(public, ids)
    assert new_terms(_shift(public)) == new_terms(public)


# ---- N167: an added sentence or item with a bounding word or a number is a changed rule
def test_added_exception_sentences_are_a_changed_rule():
    k = "chỉ xét khách có **từ 3 đơn trở lên**"
    cases = [(OLD, OLD + ". Riêng đơn sỉ tính theo ngày giao"), (OLD, OLD + ". Đơn huỷ không tính"),
             (k, k + ", hoặc tổng chi từ 5 triệu"), (k, k + ". Từ 01/2026 là từ 5 đơn trở lên"),
             ("theo ngày đặt, không theo ngày giao", "theo ngày đặt. Đơn sỉ theo ngày giao, không theo ngày giao"),
             ("Đơn đang giao vẫn tính.", "Đơn đang giao vẫn tính. Đơn COD chưa thu tiền không tính vào doanh thu"),
             ("Dòng **Phí phục vụ** không phải mặt hàng: không xếp hạng, không đếm.",
              "Dòng **Phí phục vụ** không phải mặt hàng: không xếp hạng, không đếm. Dòng quà tặng giá 0 đồng cũng không phải mặt hàng.")]
    for old, new in cases:
        assert not extends(old, new), new


def test_plain_clarifying_sentence_still_accepted():
    assert extends("Đơn đang giao vẫn tính", "Đơn đang giao vẫn tính. Đơn trả hàng sau kỳ vẫn bị loại khỏi kỳ đặt")


@pytest.mark.skipif(not (DATA / "public_test" / "rulebook.md").exists(), reason="cần data/")
def test_public_additions_still_extend_train():
    train = parse_rulebook((DATA / "train" / "rulebook.md").read_text(encoding="utf-8-sig"))
    public = parse_rulebook((DATA / "public_test" / "rulebook.md").read_text(encoding="utf-8-sig"))
    for rid in ("§1.don_thuoc_ky_nao", "§2.den_het_ngay_x_tinh_den_hom_nay", "§6.vat_lieu_xay_dung.giao_nhieu_dot"):
        assert extends(train[rid].text, public[rid].text), rid


# ---- N168: a renamed row, or one written as a bullet, is found by its text
def _ref():
    return {rid: r.text for rid, r in parse_rulebook(SAMPLE).items()}


def test_renamed_row_found_by_its_text():
    ref = _ref()
    ids = tuple(ref)
    renamed = SAMPLE.replace("| Đơn thuộc kỳ nào |", "| Đơn tính vào kỳ nào |")
    assert check_rules(SAMPLE, ids, ref)["§1.don_thuoc_ky_nao"] is True
    assert check_rules(renamed, ids, ref) == check_rules(SAMPLE, ids, ref)


def test_bullet_row_found_by_its_text():
    ref = _ref()
    ids = tuple(ref)
    row = "| Đơn thuộc kỳ nào | theo **ngày đặt**, không theo ngày giao hay ngày thu tiền |\n"
    bullet = SAMPLE.replace(row, "").replace(
        "\n## 2.", "\n- **Đơn thuộc kỳ nào**: theo **ngày đặt**, không theo ngày giao hay ngày thu tiền\n\n## 2.")
    assert bullet != SAMPLE
    assert check_rules(bullet, ids, ref)["§1.don_thuoc_ky_nao"] is True


def test_two_rows_with_the_same_text_adopt_nothing():
    ref = _ref()
    ids = tuple(ref)
    twice = SAMPLE.replace("| Đơn thuộc kỳ nào |", "| Đơn tính vào kỳ nào |").replace(
        "| Khách sộp |", "| Đơn kỳ nào |", 1).replace("chỉ xét khách có **từ 3 đơn trở lên**",
                                                      "theo **ngày đặt**, không theo ngày giao hay ngày thu tiền")
    assert check_rules(twice, ids, ref)["§1.don_thuoc_ky_nao"] is False


def test_renamed_and_changed_is_still_changed():
    ref = _ref()
    ids = tuple(ref)
    bad = SAMPLE.replace("| Khách sộp | chỉ xét khách có **từ 3 đơn trở lên** |",
                         "| Khách quan trọng | chỉ xét khách có **từ 5 đơn trở lên** |")
    assert check_rules(bad, ids, ref)["§1.khach_sop"] is False


def test_short_text_not_adopted():
    ref = {"§1.so_don": "đếm đơn"}
    book = "## 1. Đơn\n| Luật | Mặc định |\n|---|---|\n| Số lượng đơn | đếm đơn |\n"
    assert check_rules(book, ("§1.so_don",), ref)["§1.so_don"] is False


@pytest.mark.skipif(not (DATA / "public_test" / "rulebook.md").exists(), reason="cần data/")
def test_renamed_row_is_not_a_new_term():
    text = (DATA / "public_test" / "rulebook.md").read_text(encoding="utf-8-sig")
    old = "| Đơn thuộc kỳ nào |"
    if old in text:
        assert new_terms(text.replace(old, "| Đơn tính vào kỳ nào cho ngày đặt |")) == new_terms(text)


@pytest.mark.skipif(not (DATA / "public_test" / "rulebook.md").exists(), reason="cần data/")
def test_renamed_rows_of_the_public_rulebook_change_nothing():
    from datamate import pipeline
    text = (DATA / "public_test" / "rulebook.md").read_text(encoding="utf-8-sig")
    base = check_rules(text, pipeline.rule_ids())
    for old, new in (("| Đơn tính vào doanh thu |", "| Đơn được tính doanh thu |"),
                     ("| Đơn thuộc kỳ nào |", "| Đơn tính vào kỳ nào |")):
        if old in text:
            assert check_rules(text.replace(old, new), pipeline.rule_ids()) == base, old


# ---- T015: a reworded row is the same rule, one changed content word is not
def _edits():
    import sys
    tools = str(Path(__file__).resolve().parents[1] / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import robust_rulebook
    return robust_rulebook


# rewordings of the planner's and the fixer's list the gate must accept; the five it cannot (a content word is
# inserted or changed: "hết ngày hôm nay", "liên tiếp", "đơn trả", "không tính từ", "Kết quả … đến") stay blank
WONTFIX_REWORD = {"reword_11", "reword_13", "reword_14", "reword_16", "reword_18"}


def _verdict(rb, text, name):
    from datamate import pipeline
    rid = rb.EDITS[name][3]
    return check_rules(rb.apply(text, name), tuple(pipeline.rule_ids()) + (rid,))[rid]


@pytest.mark.skipif(not (DATA / "public_test" / "rulebook.md").exists(), reason="cần data/")
def test_reworded_rows_accepted_and_meaning_changes_refused():
    rb = _edits()
    text = (DATA / "public_test" / "rulebook.md").read_text(encoding="utf-8-sig")
    rewords = [n for n in rb.EDITS if n.startswith(("reword_", "held_reword_"))]
    means = [n for n in rb.EDITS if n.startswith(("mean_", "held_mean_"))]
    assert len(rewords) >= 30 and len(means) >= 51
    assert [n for n in means if _verdict(rb, text, n)] == []
    refused = {n for n in rewords if not _verdict(rb, text, n)}
    assert refused == WONTFIX_REWORD


@pytest.mark.skipif(not (DATA / "public_test" / "rulebook.md").exists(), reason="cần data/")
def test_fuzzy_hole_closed():
    """One word of a long row changed: 0.95 similar, no listed word, so the character test accepted it."""
    rb = _edits()
    text = (DATA / "public_test" / "rulebook.md").read_text(encoding="utf-8-sig")
    for name in ("mean_14", "mean_15", "mean_18", "mean_06"):  # hôm qua · Chủ nhật · một khách · đơn COD
        assert not _verdict(rb, text, name), name


def test_reworded_needs_four_content_words():
    assert not rules.reworded("đếm đơn", "đếm các đơn")  # three content words at most: too weak a key
    assert rules.reworded("chỉ tính đơn không huỷ, không trả", "chỉ tính các đơn không hủy, không trả")


def test_unaccented_row_is_the_same_rule():
    old = "theo **ngày đặt**, không theo ngày giao hay ngày thu tiền"
    assert rules.reworded(old, "theo ngay dat, khong theo ngay giao hoac ngay thu tien")
    assert not rules.reworded(old, "theo ngay giao, khong theo ngay dat hoac ngay thu tien")


def test_added_sentence_after_rewording_keeps_n167_limits():
    old = "theo **ngày đặt**, không theo ngày giao hay ngày thu tiền"
    assert rules.accepted_version(old, "theo ngày đặt, không theo ngày giao hoặc ngày thu tiền. Kết quả là số nguyên")
    assert not rules.accepted_version(old, "theo ngày đặt, không theo ngày giao hoặc ngày thu tiền. Đơn sỉ không tính")
    assert not rules.accepted_version(old, "theo ngày đặt, không theo ngày giao hoặc ngày thu tiền. Từ 2026 là 5 đơn")


def test_order_inside_a_sentence_is_a_fact():
    assert not rules.reworded("theo ngày đặt, không theo ngày giao", "theo ngày giao, không theo ngày đặt")
    assert rules.reworded("Đơn đang giao vẫn tính. Đơn huỷ không tính vào doanh thu",
                          "Đơn huỷ không tính vào doanh thu. Đơn đang giao vẫn tính")  # whole sentences may swap


@pytest.mark.skipif(not rules.REFERENCE.exists(), reason="cần assets/rules")
def test_every_reference_version_accepts_itself_and_the_fuzzy_path_gave_the_same_verdict():
    ref = rules.load_reference()
    for rid, versions in ref.items():
        for a in versions:
            assert rules.accepted_version(a, a), rid
            for b in versions:
                before = rules.same_rule(a, b) or rules.extends(a, b)
                if before:
                    assert rules.accepted_version(a, b), (rid, b[:60])


def test_edited_known_sentence_is_a_changed_rule_but_a_recut_one_is_not():
    """T016: the sentence public added to a train row, said the other way, is a changed rule; the same sentence cut
    at another place, or a new sentence with little in common with the known ones, is not."""
    train = "theo ngày đặt, không theo ngày giao hay ngày thu tiền"
    public = train + ". Đơn trả hàng sau kỳ vẫn bị loại khỏi doanh thu kỳ đặt"
    versions = [train, public]
    assert rules.accepted_row(public, versions)
    assert not rules.accepted_row(train + ". Đơn trả hàng sau kỳ vẫn tính vào doanh thu kỳ đặt", versions)
    assert rules.accepted_row(train + ". Đơn trả hàng sau kỳ; vẫn bị loại khỏi doanh thu kỳ đặt", versions)
    assert rules.accepted_row(public + ". Kết quả là số nguyên", versions)
