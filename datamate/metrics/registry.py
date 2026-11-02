"""Registry of metric functions [D1]. Each function declares the canonical fields it needs and the rulebook rows it
implements, so [V] can tell a missing field (unanswerable) and [R] can tell a changed rule (lower confidence).

Key: (intent, metric, entity). `entity` is the object ranked, counted or listed (rank / count_where / list_items),
"" for a function that serves every entity or an intent without one. Registering a key twice is an error, so two
work packages can never silently replace each other's function.
"""
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
    entity: str = ""  # rank.entity / threshold.entity / list_spec.entity; "" = any
    filters: tuple[str, ...] = ()  # filter fields the function applies; a plan with any other filter never reaches it


REGISTRY: dict[tuple[str, str, str], MetricSpec] = {}


def metric(intent: str, name: str, requires: tuple[str, ...] = (), rules: tuple[str, ...] = (), entity: str = "",
           filters: tuple[str, ...] = ()):
    """Register a function computing `name` for questions of `intent` (and `entity`, for rankings, counts and lists)."""
    def wrap(fn: MetricFn) -> MetricFn:
        key = (intent, name, entity)
        if key in REGISTRY:
            old = REGISTRY[key].fn
            raise ValueError(f"metric {key} đã được đăng ký bởi {old.__module__}.{old.__name__}")
        REGISTRY[key] = MetricSpec(intent, name, fn, requires, rules, entity, filters)
        return fn
    return wrap


def lookup(intent: str, name: str, entity: str = "") -> MetricSpec | None:
    """The function registered for this entity, else the one registered for any entity."""
    return REGISTRY.get((intent, name, entity)) or REGISTRY.get((intent, name, ""))
