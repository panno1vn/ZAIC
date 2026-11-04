"""Run the agent on one split: per business (load, map, once) then per question (plan → compute → decide → write).

Each answer is written as soon as it is decided. A failure in one business or one question makes only those
questions abstain. Near the time budget the run stops computing and writes abstain for what is left.
"""
from __future__ import annotations

import json
import time
import traceback
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from datamate import codegen, decide, formatter, loader, mapping, metrics, nlu, rules, temporal, verify
from datamate.contracts import (BusinessProfile, CanonicalDB, DataCard, Mapping, QueryPlan, RawBusiness,
                                ResolvedPlan, SubmissionLine)
from datamate.llm import LLMClient
from datamate.nlu import twins
from datamate.output import SubmissionWriter, TimeGuard, write_log


MapFn = Callable[[RawBusiness, BusinessProfile, str, "LLMClient | None"], Mapping]


@dataclass
class RunConfig:
    time_budget_s: float = 5.5 * 3600
    reserve_s: float = 120.0
    write_logs: bool = True
    started_at: float | None = None  # time.monotonic() at process start; None = when run() starts
    twin_threshold: float | None = None  # T4: an LLM plan needs a verified twin this similar (None: gate off)
    # development hook: example ids the LLM may not see for a question (oracle: its business's own train questions)
    exclude_examples: Callable[[dict], frozenset[str]] | None = None
    # development hooks, never set by predict: hand-made mappings, a subset of questions (datamate/eval/oracle.py)
    map_fn: MapFn | None = None
    question_filter: Callable[[dict], bool] | None = None


@dataclass
class RunSummary:
    n_questions: int = 0
    types: Counter = field(default_factory=Counter)
    errors: int = 0
    timed_out: int = 0
    elapsed_s: float = 0.0


@dataclass
class BusinessContext:
    raw: RawBusiness | None
    profile: BusinessProfile | None
    mapping: Mapping
    db: CanonicalDB
    card: DataCard
    error: str | None = None


def find_split_dir(data: Path) -> Path:
    """`data` itself when it holds questions.jsonl, else its only subfolder that does (/data may be either)."""
    if (data / "questions.jsonl").exists():
        return data
    found = [d for d in sorted(data.iterdir()) if d.is_dir() and (d / "questions.jsonl").exists()]
    if len(found) != 1:
        raise FileNotFoundError(f"không tìm thấy đúng một questions.jsonl trong {data} (thấy {len(found)})")
    return found[0]


def load_questions(split_dir: Path) -> list[dict]:
    """Questions with an id; unreadable lines are skipped (they have no id to answer anyway). BOM tolerated."""
    questions = []
    with open(split_dir / "questions.jsonl", encoding="utf-8-sig") as fh:
        for line in fh:
            try:
                q = json.loads(line) if line.strip() else None
            except json.JSONDecodeError:
                continue
            if isinstance(q, dict) and isinstance(q.get("id"), str):
                q.setdefault("business_id", "")
                q.setdefault("question", "")
                q.setdefault("as_of_date", "")
                questions.append(q)
    return questions


def group_by_business(questions: list[dict]) -> dict[str, list[dict]]:
    """Questions grouped per business, in order of first appearance (deterministic)."""
    groups: dict[str, list[dict]] = {}
    for q in questions:
        groups.setdefault(q["business_id"], []).append(q)
    return groups


def business_dir(split_dir: Path, business_id: str) -> Path:
    """Folder of a business. The id is used only to find the folder, never to change behaviour (rule 4)."""
    root = (split_dir / "data").resolve()
    path = (root / business_id).resolve()
    if root not in path.parents:
        raise ValueError(f"business_id không hợp lệ: {business_id!r}")
    return path


def prepare_business(root: Path, rulebook: str, llm: LLMClient | None, map_fn: MapFn | None = None
                     ) -> BusinessContext:
    try:
        raw = loader.load_business(root)
        profile = loader.profile_business(raw)
        m = (map_fn or mapping.map_business)(raw, profile, rulebook, llm)
        db = mapping.build_canonical(raw, m)
        m.checks = list(m.checks) + mapping.run_checks(db, raw.readme)  # the required checks decide Mapping.ok
        return BusinessContext(raw, profile, m, db, mapping.build_card(db))
    except Exception:
        return BusinessContext(None, None, Mapping(), CanonicalDB(), DataCard(), error=traceback.format_exc())


def rule_ids() -> tuple[str, ...]:
    """Every rulebook row the run relies on, checked by [R]: the metric functions' and the decisions' (§7)."""
    return tuple(sorted({r for spec in metrics.REGISTRY.values() for r in spec.rules} | set(verify.R_OUTSIDE)))


def twin_check(question: str, plan: QueryPlan, ctx: BusinessContext, threshold: float | None, log: dict,
               exclude_ids: frozenset[str] = frozenset()) -> bool | None:
    """T4 gate for a plan read with the LLM: True when the baseline reads the question the same way or a verified
    train question of the plan's shape is at least `threshold` similar; None when the gate is off or has no bank."""
    index = twins.default_index()
    if threshold is None or not len(index):
        return None
    base = nlu.baseline.parse(question)
    if base is not None and nlu.canonical_plan(base) == nlu.canonical_plan(plan):
        log["twin"] = {"baseline_agrees": True}
        return True
    twin = index.twin(twins.question_text(question, ctx.db), plan, exclude_ids=exclude_ids)
    log["twin"] = {"score": twin.score, "id": twin.question_id}
    return twin.passes(threshold)


def answer_question(q: dict, ctx: BusinessContext, calendar: Path, rule_status: dict[str, bool], rulebook: str,
                    llm: LLMClient | None, twin_threshold: float | None = None,
                    exclude_examples: frozenset[str] = frozenset()) -> tuple[SubmissionLine, dict]:
    log: dict = {"id": q["id"], "business_id": q["business_id"], "question": q["question"],
                 "as_of_date": q["as_of_date"]}
    try:
        as_of = date.fromisoformat(q["as_of_date"])
        reader = llm if ctx.mapping.ok else None  # no usable data: the question abstains anyway, spare the LLM call
        log["reader"] = "llm+baseline" if reader is not None else "baseline"
        plan = nlu.parse_question(q["question"], as_of, ctx.card, reader, exclude_examples)
        log["plan"] = plan
        resolved: ResolvedPlan | None = temporal.resolve(plan, as_of, calendar, ctx.db) if plan is not None else None
        if resolved is not None:
            resolved = nlu.link_entities(resolved, ctx.db, q["question"])
        log["resolved"] = resolved
        result = None
        if resolved is not None and resolved.plan.intent != "out_of_scope":
            result = metrics.execute(resolved, ctx.db) or codegen.solve(q["question"], resolved, ctx.db, rulebook, llm)
        log["result"] = result
        signals = verify.collect_signals(resolved, result, ctx.db, ctx.mapping, rule_status)
        if result is not None:  # a term only this rulebook defines, which the function does not implement
            unknown = rules.unverified_terms(q["question"], rulebook, result.rule_ids)
            signals.terms_known = not unknown
            log["unverified_terms"] = unknown
        if plan is not None and reader is not None:
            signals.twin_ok = twin_check(q["question"], plan, ctx, twin_threshold, log, exclude_examples)
        log["signals"] = signals
        decision = decide.decide(signals, result)
        log["decision"] = decision
        line = formatter.to_line(q["id"], decision, result)
    except Exception:
        line = SubmissionLine.abstain(q["id"])
        log["error"] = traceback.format_exc()
    log["answer"] = line.to_dict()
    return line, log


def run(data_dir: Path, out_dir: Path, config: RunConfig | None = None, llm: LLMClient | None = None) -> RunSummary:
    """Answer every question of the split. Whatever fails, every question ends with exactly one line."""
    config = config or RunConfig()
    guard = TimeGuard(config.time_budget_s, config.reserve_s, start=config.started_at)
    split_dir = find_split_dir(data_dir)
    questions = load_questions(split_dir)
    if config.question_filter is not None:
        questions = [q for q in questions if config.question_filter(q)]
    rulebook_path = split_dir / "rulebook.md"
    rulebook = rulebook_path.read_text(encoding="utf-8-sig") if rulebook_path.exists() else ""
    rule_status = rules.check_rules(rulebook, rule_ids())
    log_dir = out_dir / "logs"
    summary = RunSummary(n_questions=len(questions))

    def log(name: str, record: dict) -> None:
        if config.write_logs:
            try:
                write_log(log_dir, name, record)
            except Exception:  # a log that cannot be written must never cost an answer
                pass

    with SubmissionWriter(out_dir / "submission.jsonl") as writer:
        try:
            for business_id, qs in group_by_business(questions).items():
                if guard.expired():
                    break
                t0 = time.perf_counter()
                try:
                    ctx = prepare_business(business_dir(split_dir, business_id), rulebook, llm, config.map_fn)
                except Exception:
                    ctx = BusinessContext(None, None, Mapping(), CanonicalDB(), DataCard(), error=traceback.format_exc())
                log(f"_business_{business_id}", {
                    "business_id": business_id, "mapping": ctx.mapping, "warnings": ctx.db.warnings,
                    "error": ctx.error, "elapsed_ms": round((time.perf_counter() - t0) * 1000)})
                for q in qs:
                    if guard.expired():
                        break
                    t1 = time.perf_counter()
                    excluded = config.exclude_examples(q) if config.exclude_examples else frozenset()
                    line, record = answer_question(q, ctx, split_dir / "calendar.csv", rule_status, rulebook, llm,
                                                   config.twin_threshold, excluded)
                    record["elapsed_ms"] = round((time.perf_counter() - t1) * 1000)
                    try:
                        written = writer.write(line)
                    except Exception:  # an answer that cannot be written costs that answer, never the rest of the run
                        record["error"] = traceback.format_exc()
                        line = SubmissionLine.abstain(q["id"])
                        record["answer"] = line.to_dict()
                        written = writer.write(line)
                    if written:
                        summary.types[line.type] += 1
                    summary.errors += "error" in record
                    log(q["id"], record)
        finally:  # time out or unexpected failure: every question left gets an abstain line
            for q in questions:
                if q["id"] not in writer.written:
                    writer.write(SubmissionLine.abstain(q["id"]))
                    summary.types["abstain"] += 1
                    summary.timed_out += 1
                    log(q["id"], {"id": q["id"], "answer": {"id": q["id"], "type": "abstain"},
                                  "decision": "abstain: hết thời gian hoặc không chạy tới", "elapsed_ms": 0})
    summary.elapsed_s = guard.elapsed()
    return summary
