"""LLM client shared by [B], [C] and [D2]. One interface, two backends: a mock for tests, a local llama.cpp server.

Inference runs offline: the real backend talks to a model server inside the container (localhost), never to an
external API. Every call has a timeout (H12) and greedy decoding with a fixed seed, so a re-run gives the same plan.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
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


class LlamaServerLLM:
    """llama.cpp `llama-server` (OpenAI-compatible chat endpoint). Start it with --jinja so Qwen3's thinking can be
    switched off; the JSON schema is turned into a grammar, so the output is always parseable JSON of that shape.

        llama-server -m Qwen3-8B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --parallel 1 --port 8080
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout_s: float = 60.0, seed: int = 0,
                 max_tokens: int = 1024):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.seed = seed
        self.max_tokens = max_tokens

    def generate_json(self, messages: list[dict], schema: dict) -> dict:
        body = {
            "messages": messages, "temperature": 0.0, "top_k": 1, "seed": self.seed, "max_tokens": self.max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        req = urllib.request.Request(f"{self.base_url}/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # raises on timeout: the caller abstains
            data = json.loads(resp.read().decode("utf-8"))
        return json.loads(data["choices"][0]["message"]["content"])

    def healthy(self) -> bool:
        """True when the server answers /health (model loaded)."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/health", timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False


class CachedLLM:
    """Development only (`--llm-cache`): another client's answers kept in a jsonl file under the hash of the request,
    so a run over the train questions can be repeated after a metric fix without asking the model again. The server
    decodes greedily with a fixed seed, so the cache changes the time a run takes, not its answers. Failed calls are
    not kept."""

    def __init__(self, inner, path: str | Path):
        self.inner, self.path = inner, Path(path)
        self.answers: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    e = json.loads(line)
                    self.answers[e["key"]] = e["answer"]

    @staticmethod
    def key(messages: list[dict], schema: dict) -> str:
        return hashlib.sha256(json.dumps([messages, schema], sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def generate_json(self, messages: list[dict], schema: dict) -> dict:
        k = self.key(messages, schema)
        if k not in self.answers:
            answer = self.inner.generate_json(messages, schema)
            self.answers[k] = answer
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"key": k, "answer": answer}, ensure_ascii=False) + "\n")
        return self.answers[k]

    def healthy(self) -> bool:
        return self.inner.healthy()
