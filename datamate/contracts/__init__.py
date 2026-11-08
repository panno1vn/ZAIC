"""Contracts between the pipeline blocks (frozen on 05/11; changes go through the leader).

Flow: [A] RawBusiness → [A2] BusinessProfile → [B] Mapping → CanonicalDB + DataCard
      question → [C] QueryPlan → [C2]/[C3] ResolvedPlan → [D1]/[D2] ExecResult → [V] Signals → [E] Decision
      → [F] SubmissionLine
"""
from .answer import AnswerType, SubmissionLine, format_error
from .canonical import ORDER_STATUSES, TABLES, CanonicalDB, ExtraTable, check_frame
from .card import DataCard
from .mapping import CheckResult, ColumnMap, ExtraTableSpec, Mapping, TableMap
from .plan import (CODED_VALUES, INTERNAL_METRICS, STOCK_METRICS, Compare, Filter, ListSpec, Measure, PeriodExpr, QueryPlan, Rank,
                   ResolvedPeriod, ResolvedPlan, Threshold, expected_answer_type)
from .raw import BusinessProfile, ColumnProfile, RawBusiness, RawTable, TableProfile
from .results import Decision, ExecResult, Signals

__all__ = [
    "AnswerType", "SubmissionLine", "format_error", "ORDER_STATUSES", "TABLES", "CanonicalDB", "ExtraTable",
    "check_frame", "DataCard", "CheckResult", "ColumnMap", "ExtraTableSpec", "Mapping", "TableMap", "Compare",
    "Filter", "ListSpec", "Measure", "PeriodExpr", "QueryPlan", "Rank", "ResolvedPeriod", "ResolvedPlan", "Threshold",
    "expected_answer_type", "CODED_VALUES", "INTERNAL_METRICS", "STOCK_METRICS",
    "BusinessProfile", "ColumnProfile", "RawBusiness", "RawTable", "TableProfile", "Decision", "ExecResult",
    "Signals",
]
