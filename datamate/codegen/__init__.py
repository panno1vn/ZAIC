"""[D2] Fallback path: the LLM writes pandas code for questions outside the metric library. Work package G3, if time
allows. Code runs in a subprocess with a timeout and writes only under /tmp.

Stub: never answers.
"""
from __future__ import annotations

from datamate.contracts import CanonicalDB, ExecResult, ResolvedPlan
from datamate.llm import LLMClient


def solve(question: str, plan: ResolvedPlan, db: CanonicalDB, rulebook: str, llm: LLMClient | None = None
          ) -> ExecResult | None:
    return None
