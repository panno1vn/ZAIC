"""[C] with an LLM: llama-server client (against a fake local server), prompt, example bank, cross-check with baseline."""
import json
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from datamate.contracts import DataCard, QueryPlan
from datamate.llm import LlamaServerLLM, MockLLM
from datamate.nlu import canonical_plan, llm_plan, parse_question, prompt

AS_OF = date(2026, 8, 24)
JUNE = {"kind": "month", "year": 2026, "month": 6}
REVENUE_JUNE = {"intent": "value", "measures": [{"metric": "revenue"}], "period": JUNE}
COCA = {"intent": "value", "period": JUNE,
        "measures": [{"metric": "revenue", "filters": [{"field": "product", "value": "Coca Cola 330ml"}]}]}


@pytest.fixture
def fake_server():
    """A llama-server stand-in on localhost: answers with `reply`, after `delay` seconds; keeps the last request."""
    state = {"reply": REVENUE_JUNE, "delay": 0.0, "request": None}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state["request"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            time.sleep(state["delay"])
            body = json.dumps({"choices": [{"message": {"content": json.dumps(state["reply"])}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:  # the client gave up (timeout test)
                pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()


def test_llama_server_client_sends_greedy_schema_request(fake_server):
    llm = LlamaServerLLM(fake_server["url"], timeout_s=5)
    assert llm.healthy()
    plan = llm_plan("dthu thang 6/2026", AS_OF, DataCard(), llm)
    assert plan is not None and plan.measures[0].metric == "revenue"
    req = fake_server["request"]
    assert req["temperature"] == 0 and req["response_format"]["json_schema"]["schema"] == prompt.PLAN_SCHEMA
    assert req["chat_template_kwargs"] == {"enable_thinking": False}
    assert req["messages"][-1]["content"].startswith("(Hôm nay là 2026-08-24)")


def test_a_call_over_its_timeout_gives_no_plan(fake_server):
    fake_server["delay"] = 1.5
    t0 = time.monotonic()
    assert llm_plan("dthu thang 6/2026", AS_OF, DataCard(), LlamaServerLLM(fake_server["url"], timeout_s=0.3)) is None
    assert time.monotonic() - t0 < 1.4  # the client stops waiting at its timeout (H12)


def test_llm_plan_kept_when_baseline_cannot_read_the_question():
    plan = parse_question("Doanh thu của Coca Cola 330ml trong tháng 6 năm 2026", AS_OF, DataCard(), MockLLM([COCA]))
    assert plan is not None and plan.measures[0].filters[0].value == "Coca Cola 330ml"


def test_two_readers_must_agree():
    q = "tong dthu thang 6 nam 2026 la bn"  # the baseline reads it as revenue of June 2026
    assert parse_question(q, AS_OF, DataCard(), MockLLM([REVENUE_JUNE])) is not None
    other = {**REVENUE_JUNE, "measures": [{"metric": "order_count"}]}
    assert parse_question(q, AS_OF, DataCard(), MockLLM([other])) is None


@pytest.mark.parametrize("reply", [{"intent": "value"}, {"intent": "value", "measures": [{"metric": "revenue"}],
                                                         "period": JUNE, "filter": []}])
def test_invalid_output_gives_no_plan(reply):
    assert parse_question("doanh thu nhom nuoc ngot thang 6/2026", AS_OF, DataCard(), MockLLM([reply])) is None


def test_failing_llm_gives_no_plan():
    assert parse_question("doanh thu nhom nuoc ngot thang 6/2026", AS_OF, DataCard(), MockLLM([])) is None


def test_canonical_plan_ignores_case_and_diacritics_of_names():
    a = QueryPlan.model_validate(COCA)
    b = QueryPlan.model_validate(json.loads(json.dumps(COCA).replace("Coca Cola 330ml", "coca cola 330ML")))
    assert canonical_plan(a) == canonical_plan(b) != canonical_plan(QueryPlan.model_validate(REVENUE_JUNE))


def test_example_bank_excludes_the_question_itself_and_puts_the_closest_last():
    bank = prompt.ExampleBank()
    q = next(e for e in bank.items if e["id"] == "q_00c4e64fe706")
    chosen = bank.select(q["question"], k=4, exclude_ids=frozenset({q["id"]}))
    assert len(chosen) == 4 and q["id"] not in {e["id"] for e in chosen}
    assert all("answer_type" not in e["plan"] for e in chosen)
    msgs = prompt.build_messages(q["question"], AS_OF, DataCard(industry="tạp hóa"), chosen)
    assert msgs[0]["role"] == "system" and "tạp hóa" in msgs[0]["content"] and len(msgs) == 2 + 2 * 4


def test_k3_scorer_gives_full_marks_to_the_hand_plans_themselves():
    from datamate.eval.k3 import score
    bank = prompt.ExampleBank()
    rows = score(bank, MockLLM([e["plan"] for e in bank.items[:12]]), limit=12)
    assert len(rows) == 12 and all(r["valid"] and r["exact"] for r in rows)


# ---------------------------------------------------------------- K3 run 2: generation schema and grounding
def test_generation_schema_has_one_branch_per_intent_with_its_fields_required():
    branches = {b["properties"]["intent"]["const"]: b for b in prompt.PLAN_SCHEMA["anyOf"]}
    assert branches["rank"]["required"] == ["intent", "period", "rank"]
    assert list(branches["compare"]["properties"])[:4] == ["intent", "period", "measures", "compare"]
    assert prompt.PLAN_SCHEMA["$defs"]["Measure"]["required"] == ["metric", "filters"]
    assert all(b["additionalProperties"] is False for b in branches.values())


def test_a_plan_cannot_carry_another_intents_section():
    with pytest.raises(Exception):
        QueryPlan.model_validate({**REVENUE_JUNE, "threshold": {"entity": "day", "metric": "revenue", "op": "gt",
                                                                "value": 0}})


@pytest.mark.parametrize("question,filt,grounded", [
    ("Doanh thu của Coca Cola 330ml tháng 6/2026", {"field": "product", "value": "Coca Cola 330ml"}, True),
    ("doanh thu tu khach nhom than thiet thang 7", {"field": "customer_group", "value": "thanh thiet"}, True),  # typo
    ("5 khách hàng mua nhiều nhất tháng 1/2025", {"field": "customer", "value": "all"}, False),
    ("Ca sáng tháng 5/2025 doanh thu", {"field": "shift", "value": "morning"}, True),
    ("doanh thu Tết năm nay so với Tết năm trước", {"field": "order_status", "value": "completed"}, False),
])
def test_filters_must_be_grounded_in_the_question(question, filt, grounded):
    from datamate.nlu.grounding import ungrounded_filters
    plan = QueryPlan.model_validate({"intent": "value", "period": JUNE,
                                     "measures": [{"metric": "revenue", "filters": [filt]}]})
    assert (ungrounded_filters(question, plan) == []) is grounded


def test_hand_plans_are_all_grounded():
    from datamate.nlu.grounding import ungrounded_filters
    assert all(not ungrounded_filters(e["question"], QueryPlan.model_validate(e["plan"]))
               for e in prompt.ExampleBank().items)
