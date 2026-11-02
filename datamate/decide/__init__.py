"""[E] Decide: answer, unanswerable or abstain. Wrong answers cost a point, so anything short of every gate abstains.
Leader.
"""
from __future__ import annotations

from datamate.contracts import Decision, ExecResult, Signals

GATES = ("intent_known", "mapping_ok", "entities_ok", "required_fields_present", "sane", "rules_unchanged")


def decide(signals: Signals, result: ExecResult | None) -> Decision:
    if signals.out_of_scope:  # unanswerable is enabled only once it is measured on train
        return Decision(kind="abstain", reason="ngoài phạm vi dữ liệu: chưa bật unanswerable")
    if result is None:
        return Decision(kind="abstain", reason="không có kết quả")
    failed = [g for g in GATES if getattr(signals, g) is not True]
    if signals.period_coverage != "full":
        failed.append(f"period_coverage={signals.period_coverage}")
    if signals.compare_coverage not in (None, "full"):
        failed.append(f"compare_coverage={signals.compare_coverage}")
    if failed:
        return Decision(kind="abstain", reason="cổng chưa qua: " + ", ".join(failed))
    return Decision(kind="answer", confidence=1.0)
