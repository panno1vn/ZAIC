"""T008 (C003): the llama-server client calls again after a transport error, refuses at once while the server is judged
down, and leaves a cut output and a bad request to its caller. No network: `_call` and `healthy` are replaced."""
import json
import urllib.error

import pytest

from datamate.llm import LlamaServerLLM

MSG, SCHEMA = [{"role": "user", "content": "x"}], {"type": "object"}


class Fake(LlamaServerLLM):
    def __init__(self, script, **kw):
        super().__init__("http://x", wait_ready_s=0, **kw)
        self.script, self.calls, self.up = list(script), 0, True

    def _call(self, messages, schema):
        self.calls += 1
        r = self.script.pop(0) if self.script else {"ok": 1}
        if isinstance(r, Exception):
            raise r
        return r

    def healthy(self):
        return self.up


def test_transport_error_is_retried_once():
    llm = Fake([urllib.error.URLError("refused"), {"a": 1}])
    assert llm.generate_json(MSG, SCHEMA) == {"a": 1}
    assert llm.stats["retried"] == 1 and llm.stats["failed"] == 0 and llm.calls == 2


def test_two_failures_raise():
    llm = Fake([ConnectionResetError(), ConnectionResetError()])
    with pytest.raises(ConnectionResetError):
        llm.generate_json(MSG, SCHEMA)
    assert llm.stats["failed"] == 1 and llm.calls == 2


def test_cut_output_is_not_retried_here():
    llm = Fake([json.JSONDecodeError("cut", "{", 1)])
    with pytest.raises(json.JSONDecodeError):
        llm.generate_json(MSG, SCHEMA)
    assert llm.calls == 1 and llm.stats["retried"] == 0


def test_http_400_not_retried_but_500_is():
    bad = urllib.error.HTTPError("http://x", 400, "bad", {}, None)
    llm = Fake([bad])
    with pytest.raises(urllib.error.HTTPError):
        llm.generate_json(MSG, SCHEMA)
    assert llm.calls == 1
    err = urllib.error.HTTPError("http://x", 503, "loading", {}, None)
    llm = Fake([err, {"a": 2}])
    assert llm.generate_json(MSG, SCHEMA) == {"a": 2} and llm.calls == 2


def test_down_server_fails_fast_then_recovers():
    llm = Fake([ConnectionRefusedError()] * 10, down_after=5, probe_every=3)
    llm.up = False
    for _ in range(3):  # 3 calls x 2 attempts: 6 failures in a row, the server is judged down
        with pytest.raises(ConnectionRefusedError):
            llm.generate_json(MSG, SCHEMA)
    calls = llm.calls
    with pytest.raises(ConnectionError):  # refused at once, `_call` not reached
        llm.generate_json(MSG, SCHEMA)
    assert llm.calls == calls and llm.stats["fast_failed"] == 1
    llm.up = True
    llm.script = []
    for _ in range(2):  # the probe call is the 3rd skipped call; until then calls are still refused
        try:
            out = llm.generate_json(MSG, SCHEMA)
            break
        except ConnectionError:
            continue
    assert out == {"ok": 1} and llm._fails == 0
