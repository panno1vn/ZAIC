"""LLM client shared by [B], [C] and [D2]. One interface, two backends: a mock for tests, the local model later.

Inference runs offline: the real backend talks to a model inside the container, never to an external API.
"""
from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def generate_json(self, messages: list[dict], schema: dict) -> dict:
        """Answer the chat `messages` with a JSON object valid against `schema` (structured output, temperature 0)."""
        ...


class MockLLM:
    """Returns canned answers in order; for tests without a GPU."""

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls: list[tuple[list[dict], dict]] = []

    def generate_json(self, messages: list[dict], schema: dict) -> dict:
        self.calls.append((messages, schema))
        if not self.responses:
            raise RuntimeError("MockLLM: hết câu trả lời mẫu")
        return self.responses.pop(0)
