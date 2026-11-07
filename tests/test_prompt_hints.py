"""Hints for what train never asks (public rulebook §2 "trung bình mỗi ngày thứ X", §6 Sửa xe, a README's commission):
added to the guide only for a shop that records it or a question that says it, so every train prompt stays the one
its verified plan was read with (the 3000 stored train plans are only valid for those prompts)."""
import json
from datetime import date
from pathlib import Path

import pytest

from datamate.contracts import DataCard
from datamate.nlu import prompt

TRAIN = Path(__file__).resolve().parents[1] / "data" / "train" / "questions.jsonl"


@pytest.mark.skipif(not TRAIN.exists(), reason="train data not present")
def test_no_train_question_gets_a_hint():
    card = DataCard(fields=["orders.order_time", "orders.status", "orders.employee", "lines.line_amount"])
    for line in TRAIN.read_text(encoding="utf-8").splitlines():
        if line.strip():
            q = json.loads(line)
            assert prompt.hints(q["question"], card) == "", q["question"]


def test_a_repair_shop_gets_its_hints_and_commission_only_when_asked():
    repair = DataCard(fields=["orders.vehicle_plate", "orders.employee", "employees.commission_pct"])
    assert prompt.hints("Tháng 3/2026 tiệm có bao nhiêu phiếu?", repair) == prompt.REPAIR_HINTS
    asked = prompt.hints("thang 8/2025 tho Phuc lanh bao nhieu tien hue hong", repair)
    assert prompt.REPAIR_HINTS in asked and prompt.COMMISSION_HINT in asked
    assert prompt.hints("hoa hồng tháng này bao nhiêu", DataCard()) == ""  # no percent recorded: no metric to point to


def test_an_average_per_weekday_question_gets_its_hint():
    for q in ("Tháng 3 trung bình mỗi thứ Tư bán mấy đơn?", "cac ngay thu 3 thang nay trung binh 1 ngay bnhiu don",
              "binh quan moi chu nhat doanh thu bao nhieu"):
        assert prompt.hints(q, DataCard()) == prompt.WEEKDAY_AVG_HINT, q
    assert prompt.hints("trung bình mỗi ngày bán mấy ly", DataCard()) == ""


def test_the_hint_goes_into_the_system_message_only_when_there_is_one():
    plain = prompt.build_messages("doanh thu hôm nay", date(2026, 6, 30), DataCard(), [])
    assert plain[0]["content"].endswith(prompt.card_text(DataCard()))
    repair = DataCard(fields=["orders.vehicle_plate"])
    hinted = prompt.build_messages("doanh thu hôm nay", date(2026, 6, 30), repair, [])
    assert hinted[0]["content"].endswith(prompt.REPAIR_HINTS)
