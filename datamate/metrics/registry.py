"""Registry of metric functions [D1]. Each function declares the canonical fields it needs and the rulebook rows it
implements, so [V] can tell a missing field (unanswerable) and [R] can tell a changed rule (lower confidence)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from datamate.contracts import CanonicalDB, ExecResult, ResolvedPlan

MetricFn = Callable[[ResolvedPlan, CanonicalDB], ExecResult | None]


@dataclass(frozen=True)
class MetricSpec:
    intent: str
    metric: str
    fn: MetricFn
    requires: tuple[str, ...]  # canonical "table.column"
    rules: tuple[str, ...]  # rule ids checked by [R], e.g. "§1.don_tinh_doanh_thu"


REGISTRY: dict[tuple[str, str], MetricSpec] = {}


def metric(intent: str, name: str, requires: tuple[str, ...] = (), rules: tuple[str, ...] = ()):
    """Register a function computing `name` for questions of `intent`."""
    def wrap(fn: MetricFn) -> MetricFn:
        REGISTRY[(intent, name)] = MetricSpec(intent, name, fn, requires, rules)
        return fn
    return wrap


def lookup(intent: str, name: str) -> MetricSpec | None:
    return REGISTRY.get((intent, name))
