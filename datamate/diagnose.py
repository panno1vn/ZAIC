"""Why a function returned None: run it again under a tracer and keep the `return` lines that gave None.

Development only (tools/replay_run.py turns it on with ENABLED). The run itself never traces: a None result is
logged with the cheap reason metrics.execute knows (no function, a filter the function does not take, the function
gave None), and the replay of that run adds where inside the function it stopped. The functions are deterministic,
so the second call takes the same path as the first.

Only frames of the datamate package are traced line by line; pandas and the rest run untraced.
"""
from __future__ import annotations

import inspect
import linecache
import sys
from pathlib import Path
from typing import Any, Callable

ENABLED = False  # set by development tools; predict leaves it off
PACKAGE_DIR = str(Path(__file__).resolve().parent)
MAX_CHAIN = 6


def _where(frame) -> str:
    """'metrics.sales.value_of:312 if df.empty: return None' (the return line, with the `if` above it)."""
    module = frame.f_globals.get("__name__", "?").removeprefix("datamate.")
    line = frame.f_lineno
    text = linecache.getline(frame.f_code.co_filename, line).strip()
    above = linecache.getline(frame.f_code.co_filename, line - 1).strip()
    if text.startswith("return") and above.startswith(("if ", "elif ")) and above.endswith(":"):
        text = f"{above} {text}"
    return f"{module}.{frame.f_code.co_name}:{line} {text[:120]}"


def _transparent(code) -> bool:
    """A comprehension or a generator: not a step of its own (a generator also 'returns' None when it ends)."""
    return code.co_name.startswith("<") and code.co_name != "<lambda>" or bool(code.co_flags & inspect.CO_GENERATOR)


def none_chain(fn: Callable[..., Any], *args, **kwargs) -> list[str]:
    """Where `fn(*args, **kwargs)` returns None: its own return line, then the call inside it that gave None just
    before (often the cause: `df = frame(...); if df is None: return None`), and so on down, at most MAX_CHAIN.
    [] when the call does not return None; ["raised Error: …"] when it raises."""
    events: list[tuple[int, int, str]] = []  # (serial, parent serial, where) of each datamate frame that gave None
    live: dict[int, int] = {}  # id(frame) → serial, for frames still running
    counter = [0]

    def on_call(frame, event, arg):
        if event != "call" or not frame.f_code.co_filename.startswith(PACKAGE_DIR):
            return None
        parent = live.get(id(frame.f_back), 0)
        if _transparent(frame.f_code):  # `[figure(m) for m in ms]`: figure's None belongs to the function around it
            live[id(frame)] = parent

            def through(frame, event, arg):
                if event == "return":
                    live.pop(id(frame), None)
                return through
            return through
        counter[0] += 1
        serial = counter[0]
        live[id(frame)] = serial

        def local(frame, event, arg):
            if event == "return":
                live.pop(id(frame), None)
                if arg is None:
                    events.append((serial, parent, _where(frame)))
            return local
        return local

    old = sys.gettrace()
    sys.settrace(on_call)
    try:
        out = fn(*args, **kwargs)
    except Exception as e:  # a crash is a reason too
        return [f"raised {type(e).__name__}: {str(e)[:100]}"]
    finally:
        sys.settrace(old)
    if out is not None:
        return []
    roots = [e for e in events if e[1] == 0]
    if not roots:
        return []
    chain, (serial, _, where) = [], roots[-1]
    chain.append(where)
    while len(chain) < MAX_CHAIN:
        callees = [e for e in events if e[1] == serial]
        if not callees:
            break
        serial, _, where = callees[-1]
        chain.append(where)
    return chain
