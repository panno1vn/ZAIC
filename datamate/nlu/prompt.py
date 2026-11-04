"""Prompt for [C]: a short guide to the QueryPlan contract, the business's data card and the closest hand-written
plans (BM25 on folded questions). The JSON schema itself is enforced by the server's grammar, so the prompt explains
meaning, not syntax.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from datamate.contracts import CODED_VALUES, DataCard, QueryPlan

from .baseline import fold

BANK_FILES = sorted((Path(__file__).resolve().parents[2] / "assets" / "plans").glob("*.jsonl"))
VERIFIED_FILE = "verified_train.jsonl"  # LLM plans verified by the train answers (T4, eval/build_bank.py)
HAND_FILES = [f for f in BANK_FILES if f.name != VERIFIED_FILE]  # what build_bank and K3 may use as examples

# Generation schema: one branch per intent, its fields required and in reading order. With every field optional the
# server's grammar let the model close an object early: K3 (05/11) found plans without a period (10/123), without the
# filters the question names (7) or without measures (5). Writing "filters" explicitly, even as [], is required.
INTENT_FIELDS = {  # intent -> (required after intent, optional), in the order the model writes them
    "value": (["period", "measures"], []),
    "compare": (["period", "measures", "compare"], []),
    "share": (["period", "measures"], ["share_of"]),
    "rank": (["period", "rank"], ["measures"]),
    "count_where": (["period", "threshold"], ["measures"]),
    "trend": (["period", "measures"], []),
    "series": (["period", "measures"], []),
    "list_items": (["list_spec"], ["period"]),
    "out_of_scope": (["out_of_scope_reason"], []),
}


def generation_schema() -> dict:
    """QueryPlan as an anyOf of intent branches (the contract still validates the result)."""
    base = QueryPlan.model_json_schema()
    defs = base.pop("$defs")
    measure = defs["Measure"]
    order = ["metric", "filters"] + [k for k in measure["properties"] if k not in ("metric", "filters")]
    measure["properties"] = {k: measure["properties"][k] for k in order}
    measure["required"] = ["metric", "filters"]
    def non_null(schema: dict) -> dict:  # a required field may not be written as null
        opts = [s for s in schema.get("anyOf", []) if s.get("type") != "null"]
        out = dict(opts[0]) if len(opts) == 1 else ({**schema, "anyOf": opts} if opts else dict(schema))
        if out.get("type") == "array":
            out["minItems"] = 1
        return out

    branches = []
    for intent, (required, optional) in INTENT_FIELDS.items():
        props = {"intent": {"const": intent}}
        props.update({k: non_null(base["properties"][k]) for k in required})
        props.update({k: base["properties"][k] for k in optional})
        if intent == "value":  # a measure of "other" needs its answer type stated
            props["answer_type"] = base["properties"]["answer_type"]
        branches.append({"type": "object", "properties": props, "required": ["intent", *required],
                         "additionalProperties": False})
    return {"$defs": defs, "anyOf": branches}


PLAN_SCHEMA = generation_schema()

GUIDE = """Bạn đọc câu hỏi tiếng Việt (thường không dấu, viết tắt, gõ sai) của chủ cửa hàng nhỏ về dữ liệu bán hàng và viết ra
một kế hoạch truy vấn JSON (QueryPlan). Bạn KHÔNG tính toán gì: code sẽ tính theo kế hoạch của bạn.

Quy tắc:
- Chỉ ghi những gì câu hỏi nói. Không thêm bộ lọc câu hỏi không nêu. Thiếu thông tin thì để trống trường đó.
- Kỳ ghi dạng ký hiệu: "tháng này" → {"kind":"this_month"}; "tháng 6/2025" → {"kind":"month","year":2025,"month":6};
  "hôm qua" → yesterday; "tuần trước" → last_week; "30 ngày gần nhất" → last_n_days n=30; "từ đầu năm" → ytd;
  "quý 2/2026" → quarter; "từ X đến hết Y" → range (start, end dạng YYYY-MM-DD hoặc YYYY-MM);
  "tính đến hết ngày X" (còn nợ, còn tồn) → until date=X; "N ngày kể từ ngày D" → days_from (date, n);
  "Tết" → tet (lunar_year nếu câu hỏi ghi năm); chuỗi tháng "qua 3 tháng 4/2025, 5/2025, 6/2025" → months.
  Ngày trong câu hỏi chép lại dạng YYYY-MM-DD; không tự cộng trừ ngày.
- So sánh: "so với tháng trước / kỳ trước" → compare previous; "cùng kỳ tháng trước" (tháng này) → previous_same_days;
  "cùng kỳ năm trước" → same_period_last_year; "trước Tết" → before_tet; "N ngày trước đó" → before_days_from;
  "ca chiều so với ca sáng" → compare kind filter. output: pct_change (bao nhiêu %), diff (hơn/kém bao nhiêu), which_more.
- Câu hỏi nêu mặt hàng, nhóm hàng, kênh bán (tại quầy, online…), hình thức thanh toán, ca, nhân viên, khách, nhóm
  khách, size thì measure PHẢI có filter tương ứng. Bỏ sót một bộ lọc là trả lời sai cả câu. Không có thì "filters": [].
- Tên hàng, nhóm hàng, khách, kênh, hình thức thanh toán, nhân viên: ghi đúng như trong câu hỏi.
- Công nợ: "bao nhiêu khách còn nợ" → debtor_count; "tổng nợ" → debt_total; nợ của một khách → debt_amount;
  "N khách nợ nhiều nhất, mỗi người bao nhiêu" → rank theo debt_amount, with_values=true.
- Hạn dùng: "lô gần hết hạn nhất có hạn dùng ngày nào" → nearest_expiry (kèm filter mặt hàng).
- "doanh thu mỗi tháng / từng tháng" của một chuỗi tháng → intent series (đáp án là list); "có tăng liên tục" → trend.
- Các trường sau ghi MÃ: """ + "; ".join(f"{k} = {' / '.join(str(v).lower() for v in vs)}" for k, vs in CODED_VALUES.items()) + """.
- "bán chạy" xếp theo quantity; "bán được nhiều tiền / doanh thu cao" theo revenue; "lời nhất" theo gross_profit.
  "top 5" → rank k=5; một đối tượng → k=1; "ngày nào cao nhất" → rank entity day.
- "bao nhiêu mặt hàng ế" → list_items condition unsold_in_period, count=true. "số khách mua ≥ 3 đơn" → count_where
  threshold (entity customer, metric order_count, op gte, value 3).
- Câu hỏi nhiều số ("mỗi bên bao nhiêu", "lần lượt") → nhiều measures theo đúng thứ tự câu hỏi.
- Câu hỏi đánh giá chủ quan hoặc cần kiến thức ngoài dữ liệu → intent out_of_scope kèm out_of_scope_reason.
- answer_type có thể bỏ trống (code tự suy ra)."""


class ExampleBank:
    """Hand-written plans for train questions, retrieved by BM25 over the folded question text."""

    def __init__(self, files: list[Path] = BANK_FILES):
        self.items = []
        for f in files:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    e = json.loads(line)
                    plan = {k: v for k, v in e["plan"].items() if k not in ("answer_type", "notes")}
                    self.items.append({"id": e["id"], "question": e["question"], "as_of_date": e["as_of_date"], "plan": plan})
        self.bm25 = BM25Okapi([fold(e["question"]).split() or ["_"] for e in self.items]) if self.items else None

    def select(self, question: str, k: int = 6, exclude_ids: frozenset[str] = frozenset()) -> list[dict]:
        """The k plans whose questions are closest to `question`, most similar last (closest to the question)."""
        if self.bm25 is None:
            return []
        scores = self.bm25.get_scores(fold(question).split() or ["_"])
        order = sorted(range(len(self.items)), key=lambda i: (-scores[i], self.items[i]["id"]))
        chosen = [self.items[i] for i in order if self.items[i]["id"] not in exclude_ids][:k]
        return chosen[::-1]


@lru_cache(maxsize=1)
def default_bank() -> ExampleBank:
    return ExampleBank()


def card_text(card: DataCard) -> str:
    """The data card as a few lines: what the shop records, so the plan uses fields that exist."""
    lines = [f"Ngành: {card.industry or 'không rõ'}; dữ liệu từ {card.date_min or '?'} đến {card.date_max or '?'}"]
    if card.tables:
        lines.append("Bảng có dữ liệu: " + ", ".join(card.tables))
    for label, values in (("Nhóm hàng", card.product_groups), ("Kênh bán", card.channels),
                          ("Hình thức thanh toán", card.payment_methods), ("Nhóm khách", card.customer_groups),
                          ("Đơn vị", card.units), ("Nhân viên", card.employees)):
        if values:
            lines.append(f"{label}: " + ", ".join(values[:30]))
    return "\n".join(lines)


def build_messages(question: str, as_of: date, card: DataCard, examples: list[dict]) -> list[dict]:
    """Chat messages: guide (system), then each example as a user/assistant pair, then the question."""
    messages = [{"role": "system", "content": GUIDE + "\n\nDữ liệu của cửa hàng này:\n" + card_text(card)}]
    for e in examples:
        messages.append({"role": "user", "content": user_text(e["question"], date.fromisoformat(e["as_of_date"]))})
        messages.append({"role": "assistant", "content": json.dumps(e["plan"], ensure_ascii=False)})
    messages.append({"role": "user", "content": user_text(question, as_of)})
    return messages


def user_text(question: str, as_of: date) -> str:
    return f"(Hôm nay là {as_of.isoformat()}) {question}"
