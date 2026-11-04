"""[B] Map a business's raw tables onto the canonical schema, check the result and build its data card. Work package G2.

map_business moves the mapping of a hand-mapped train shop of the same export format onto the business (transfer.py):
by column names, else by meaning with the LLM; a business no example fits gets a mapping with no tables, so it abstains. build_canonical, run_checks and build_card
turn a mapping into canonical tables, check them and describe them.
"""
from __future__ import annotations

from datamate.contracts import BusinessProfile, Mapping, RawBusiness
from datamate.llm import LLMClient

from . import transfer
from .build import REQUIRED_CHECKS, build_canonical, build_card, run_checks


def map_business(raw: RawBusiness, profile: BusinessProfile, rulebook: str, llm: LLMClient | None = None) -> Mapping:
    """The first example mapping that moves onto the business and passes every check (T5): matched by column names,
    else (with an LLM) by meaning; else no mapping."""
    mapping, tried = transfer.map_by_transfer(raw, llm=llm)
    return mapping if mapping is not None else transfer.failed(tried)


__all__ = ["REQUIRED_CHECKS", "build_canonical", "build_card", "map_business", "run_checks"]
