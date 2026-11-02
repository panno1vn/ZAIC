"""[B] Map a business's raw tables onto the canonical schema, check the result and build its data card. Work package G2.

map_business is still a stub (returns a mapping with no tables, so the business abstains). build_canonical,
run_checks and build_card are the skeleton versions G2 extends (transforms, joins, units).
"""
from __future__ import annotations

from datamate.contracts import BusinessProfile, CheckResult, Mapping, RawBusiness
from datamate.llm import LLMClient

from .build import REQUIRED_CHECKS, build_canonical, build_card, run_checks


def map_business(raw: RawBusiness, profile: BusinessProfile, rulebook: str, llm: LLMClient | None = None) -> Mapping:
    """Synonym rules first, the LLM fills the gaps (G2). Stub: no mapping."""
    return Mapping(checks=[CheckResult(name="mapping", passed=False, detail="map_business chưa cài đặt (G2)")])


__all__ = ["REQUIRED_CHECKS", "build_canonical", "build_card", "map_business", "run_checks"]
