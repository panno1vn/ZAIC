"""N200: a revenue answer is not held back because the rulebook has a §6 section of a business type the functions
were never checked against (the N190 gate, removed 13/11).

N190 took a shop for one of that type when its README held every word of the section's heading, unaccented and in any
order: "Cửa hàng máy tính" was every shop whose README says "máy POS" and "đơn vị tính". A public replay with that
one section added to the rulebook turned 86 of 1000 answers blank, in two shops of other types. And in a shop that is
of the new type, the six business types the organizers wrote leave the revenue of §1 as it is."""
from pathlib import Path

import pytest

from datamate import pipeline, rules
from datamate.contracts import QueryPlan
from test_metrics_sales import shop

TRAIN = Path(__file__).resolve().parents[1] / "data" / "train" / "rulebook.md"
COMPUTERS = """
### Cửa hàng máy tính
| Luật | Mặc định |
|---|---|
| Bảo hành | **Tỉ lệ bảo hành** của một quý bằng số lượt bảo hành có ngày nhận trong quý, chia cho số máy bán trong quý |
| Linh kiện, máy bộ | **Máy bộ** là hàng thuộc nhóm `Máy bộ`; tỉ trọng linh kiện tính theo doanh thu (§1) |
"""
# a shop of another business type, and one of the new type
READMES = ["File máy POS xuất ra.\n\n## Cột trong `ban_hang.csv`\n- **ĐVT**: đơn vị tính\n",
           "File xuất từ phần mềm bán hàng của cửa hàng máy tính.\n"]

pytestmark = pytest.mark.skipif(not TRAIN.exists(), reason="cần data/")


def with_section(extra: str) -> str:
    text = TRAIN.read_text(encoding="utf-8-sig")
    head = text.index("## 7.")
    return text[:head] + extra + "\n" + text[head:]


@pytest.mark.parametrize("metric", ["revenue", "avg_order_value"])
@pytest.mark.parametrize("readme", READMES)
def test_revenue_is_answered_whatever_business_types_the_rulebook_adds(tmp_path, monkeypatch, metric, readme):
    plan = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": metric}],
                                     "period": {"kind": "this_month"}})
    monkeypatch.setattr(pipeline.nlu, "parse_question", lambda *a, **k: plan)
    db = shop()
    db.readme = readme
    ctx = pipeline.BusinessContext(None, None, pipeline.Mapping(), db, pipeline.DataCard())
    q = {"id": "q", "business_id": "b", "question": "Doanh thu tháng này bao nhiêu?", "as_of_date": "2026-06-30"}
    logs = []
    for book in (with_section(""), with_section(COMPUTERS)):
        _, log = pipeline.answer_question(q, ctx, tmp_path / "calendar.csv",
                                          rules.check_rules(book, pipeline.rule_ids()), book, None)
        assert "error" not in log and log["result"] is not None
        logs.append(log)
    plain, added = logs
    assert added["unverified_terms"] == [] and added["signals"].terms_known
    assert added["result"] == plain["result"] and added["decision"] == plain["decision"]
