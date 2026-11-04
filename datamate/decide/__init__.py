"""[E] Decide: answer, unanswerable or abstain. Wrong answers cost a point, so anything short of every gate abstains.
Leader.
"""
from __future__ import annotations

from datamate.contracts import Decision, ExecResult, Signals

GATES = ("intent_known", "mapping_ok", "entities_ok", "required_fields_present", "sane", "rules_unchanged")
# what an "unanswerable" needs besides the period (N28): the question read and its names found in usable data; on
# train 16 of 16 questions whose period lies wholly outside the shop's data are unanswerable (05/11)
READING = ("intent_known", "mapping_ok", "entities_ok")


def decide(signals: Signals, result: ExecResult | None) -> Decision:
    if signals.out_of_scope:  # unanswerable is enabled only once it is measured on train
        return Decision(kind="abstain", reason="ngoài phạm vi dữ liệu: chưa bật unanswerable")
    if signals.outside_data and all(getattr(signals, g) is True for g in READING)             and signals.twin_ok is not False and signals.terms_known is not False:
        return Decision(kind="unanswerable", reason="kỳ hỏi nằm hoàn toàn ngoài khoảng ngày có dữ liệu của cửa hàng (§7)")
    if result is None:
        return Decision(kind="abstain", reason="không có kết quả")
    failed = [g for g in GATES if getattr(signals, g) is not True]
    if signals.period_coverage != "full":
        failed.append(f"period_coverage={signals.period_coverage}")
    if signals.compare_coverage not in (None, "full"):
        failed.append(f"compare_coverage={signals.compare_coverage}")
    if signals.twin_ok is False:  # an LLM reading the train set never confirmed (T4)
        failed.append("twin")
    if signals.terms_known is False:  # the question uses a term no function was checked against
        failed.append("terms")
    if signals.ranking_clear is False:  # a tie where the answer depends on it: train questions never have one
        failed.append("tie")
    if failed:
        return Decision(kind="abstain", reason="cổng chưa qua: " + ", ".join(failed))
    return Decision(kind="answer", confidence=1.0)
