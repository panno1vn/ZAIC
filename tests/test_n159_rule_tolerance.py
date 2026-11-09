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
