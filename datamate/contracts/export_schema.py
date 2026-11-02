"""Write the JSON schemas of the contracts the LLM fills or that are stored as JSON.

    python -m datamate.contracts.export_schema

The query-plan schema is what [C] passes to structured output; tests fail if a committed schema is out of date.
"""
from __future__ import annotations

import json
from pathlib import Path

from .mapping import Mapping
from .plan import QueryPlan

SCHEMA_DIR = Path(__file__).with_name("schemas")
MODELS = {"query_plan": QueryPlan, "mapping": Mapping}


def render(name: str) -> str:
    return json.dumps(MODELS[name].model_json_schema(), ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    for name in MODELS:
        (SCHEMA_DIR / f"{name}.schema.json").write_text(render(name), encoding="utf-8")
        print("wrote", SCHEMA_DIR / f"{name}.schema.json")


if __name__ == "__main__":
    main()
