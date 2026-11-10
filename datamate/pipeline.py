"""Run the agent on one split: per business (load, map, once) then per question (plan → compute → decide → write).

Each answer is written as soon as it is decided. A failure in one business or one question makes only those
questions abstain. Near the time budget the run stops computing and writes abstain for what is left.
"""
from __future__ import annotations

import json
import re
import time
import traceback
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from datamate import codegen, decide, diagnose, formatter, loader, mapping, metrics, nlu, rules, temporal, verify
from datamate.contracts import (BusinessProfile, CanonicalDB, DataCard, Mapping, QueryPlan, RawBusiness,
                                ResolvedPlan, SubmissionLine)
from datamate.llm import LLMClient
from datamate.nlu import twins
from datamate.nlu.grounding import customer_trait_not_recorded
from datamate.verify import NOT_RECORDED_REASON
from datamate.output import SubmissionWriter, TimeGuard, append_log, keep_logged, reset_questions_log, write_log


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
    resume: bool = False  # N165: a second process keeps the answers already written and answers only what is missing


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


QUESTION_FILES = ("questions.jsonl", "questions.json")


def questions_file(folder: Path) -> Path | None:
    """The questions file of a folder, whatever its case (N165)."""
    try:
        names = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    except OSError:
        return None
    return next((names[n] for n in QUESTION_FILES if n in names), None)


def find_split_dir(data: Path) -> Path:
    """`data` itself when it holds the questions file, else the shallowest folder under it that does (N165: /data may
    be the split, its parent, or hold it deeper; two splits: the shallowest, then the first by name, never a crash)."""
    if questions_file(data) is not None:
        return data
    found = sorted((p for p in data.rglob("*") if p.is_dir() and "logs" not in p.relative_to(data).parts
                    and questions_file(p) is not None), key=lambda d: (len(d.relative_to(data).parts), str(d)))
    if not found:
        raise FileNotFoundError(f"không tìm thấy questions.jsonl trong {data}")
    return found[0]


def _find(split_dir: Path, name: str) -> Path | None:
    """A file of the split by name, whatever its case."""
    if not split_dir.is_dir():
        return None
    return next((p for p in split_dir.iterdir() if p.is_file() and p.name.lower() == name), None)


def load_questions(split_dir: Path) -> list[dict]:
    """Questions with an id (a string, or a whole number: written "12345"); unreadable lines are skipped (they have
    no id to answer anyway). BOM, UTF-16 and a JSON array in one file are tolerated (N165)."""
    path = questions_file(split_dir)
    if path is None:
        return []
    text = loader._decode(path.read_bytes())[0].lstrip("\ufeff")
    items = None
    if path.suffix.lower() == ".json" or text.lstrip().startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            items = None
    if not isinstance(items, list):
        items = []
        for line in text.splitlines():
            try:
                items.append(json.loads(line) if line.strip() else None)
            except json.JSONDecodeError:
                continue
    questions = []
    for q in items:
        if not isinstance(q, dict):
            continue
        qid = q.get("id")
        if isinstance(qid, int) and not isinstance(qid, bool):
            q["id"] = qid = str(qid)
        if isinstance(qid, str):
            q["business_id"] = str(q.get("business_id") or "")
            q["question"] = str(q.get("question") or "")
            q["as_of_date"] = iso_day(q.get("as_of_date"))
            questions.append(q)
    return questions


def iso_day(value) -> str:
    """N160: as_of_date as YYYY-MM-DD. The task writes it so; a time after it ("2026-08-27T00:00:00", "2026-08-27
    00:00") or a Vietnamese day-first date ("27/08/2026") would otherwise make every question of the split fail to
    parse and abstain. Anything else is left as it is (the question abstains, as before)."""
    s = str(value or "").strip()
    if m := re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:$|[T\s])", s):
        y, mo, d = m.groups()
    elif m := re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?:$|[T\s])", s):
        d, mo, y = m.groups()
    else:
        return s
    try:
        return date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return s


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
    if not path.is_dir() and root.is_dir():  # N165: " DEV_x " finds dev_x on a case-sensitive disk; one match only
        same = [d for d in root.iterdir() if d.is_dir() and d.name.strip().casefold() == business_id.strip().casefold()]
        if len(same) == 1:
            return same[0].resolve()
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
    return tuple(sorted({r for spec in metrics.REGISTRY.values() for r in spec.rules} | set(verify.R_OUTSIDE)
                        | set(metrics.sales.CONDITIONAL_RULES)))


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
        reading: dict = {}  # how the reading went: the LLM's raw output, why a plan was not used (counted by run_stats)
        plan = nlu.parse_question(q["question"], as_of, ctx.card, reader, exclude_examples, trace=reading)
        if ctx.raw is not None and customer_trait_not_recorded(q["question"], ctx.raw.readme or ""):
            # N89: the customers' gender or street, which this shop does not record: unanswerable (§7)
            reading["not_recorded"] = True
            plan = QueryPlan(intent="out_of_scope", out_of_scope_reason=NOT_RECORDED_REASON)
        log["plan"] = plan
        log["reading"] = reading
        resolved: ResolvedPlan | None = temporal.resolve(plan, as_of, calendar, ctx.db) if plan is not None else None
        if resolved is not None:
            resolved = nlu.link_entities(resolved, ctx.db, q["question"])
        log["resolved"] = resolved
        result = None
        no_result: dict = {}  # why a plan gave no result (N72): counted by run_stats
        if resolved is not None and resolved.plan.intent != "out_of_scope":
            result = metrics.execute(resolved, ctx.db, no_result) \
                or codegen.solve(q["question"], resolved, ctx.db, rulebook, llm)
        elif plan is not None and resolved is None:
            no_result["why"] = "period_unresolved"
            if diagnose.ENABLED:
                no_result["at"] = diagnose.none_chain(temporal.resolve, plan, as_of, calendar, ctx.db)
        log["result"] = result
        if result is None and no_result:
            log["no_result"] = no_result
        signals = verify.collect_signals(resolved, result, ctx.db, ctx.mapping, rule_status, q["question"])
        if result is not None:  # a term only this rulebook defines, which the function does not implement
            unknown = rules.unverified_terms(q["question"], rulebook, result.rule_ids,
                                             tuple(resolved.linked.values()) if resolved is not None else ())
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
    log.update(audit_fields(log, ctx))
    return line, log


def audit_fields(log: dict, ctx: "BusinessContext") -> dict:
    """Docker guideline 2026 §3.3, per question: `thinking` is null (the LLM is called with Qwen3's thinking turned
    off, LlamaServerLLM: no reasoning is generated; its structured output, the plan, is logged under `reading`);
    a figure computed by a packaged function records `code` (source file::function), its actual `inputs` (the shop's
    folder and the resolved plan: period, measures, filters, the names linked to the data) and its `output`."""
    out: dict = {"thinking": None}
    result = log.get("result")
    if result is not None:
        module, _, fn = result.function.partition(".")
        out["code"] = f"datamate/metrics/{module}.py::{fn}"
        out["inputs"] = {"data_dir": str(ctx.raw.root) if ctx.raw is not None else None,
                         "plan": log.get("resolved")}
        out["output"] = result.value
    else:
        out.update({"code": None, "output": None})
    return out


def run(data_dir: Path, out_dir: Path, config: RunConfig | None = None, llm: LLMClient | None = None) -> RunSummary:
    """Answer every question of the split. Whatever fails, every question ends with exactly one line."""
    config = config or RunConfig()
    guard = TimeGuard(config.time_budget_s, config.reserve_s, start=config.started_at)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = out_dir / "logs"
    try:  # N165: whatever is odd about the data folder, the file is opened below and holds a line per question found
        split_dir = find_split_dir(data_dir)
        questions = load_questions(split_dir)
        if config.question_filter is not None:
            questions = [q for q in questions if config.question_filter(q)]
        rulebook_path = _find(split_dir, "rulebook.md")
        rulebook = loader._decode(rulebook_path.read_bytes())[0].lstrip("\ufeff") if rulebook_path else ""
        rule_status = rules.check_rules(rulebook, rule_ids())
        calendar = _find(split_dir, "calendar.csv") or split_dir / "calendar.csv"
    except Exception:
        split_dir, questions, rulebook, rule_status, calendar = data_dir, [], "", {}, data_dir / "calendar.csv"
        if config.write_logs:
            try:
                write_log(log_dir, "_run_error", {"error": traceback.format_exc()})
            except Exception:
                pass
    if config.write_logs and not config.resume:
        reset_questions_log(log_dir)
    summary = RunSummary(n_questions=len(questions))

    def log(name: str, record: dict) -> None:
        if config.write_logs:
            try:
                write_log(log_dir, name, record)
                if not name.startswith("_business_"):
                    append_log(log_dir, record)  # guideline §3.3: one line per question in logs/questions.jsonl
            except Exception:  # a log that cannot be written must never cost an answer
                pass

    with SubmissionWriter(out_dir / "submission.jsonl", resume=config.resume) as writer:
        if config.write_logs and config.resume:
            try:
                keep_logged(log_dir, writer.written)
            except Exception:
                pass
        try:
            for business_id, qs in group_by_business(questions).items():
                if guard.expired():
                    break
                t0 = time.perf_counter()
                try:
                    ctx = prepare_business(business_dir(split_dir, business_id), rulebook, llm, config.map_fn)
                except Exception:
                    ctx = BusinessContext(None, None, Mapping(), CanonicalDB(), DataCard(), error=traceback.format_exc())
                prep_ms = round((time.perf_counter() - t0) * 1000)
                log(f"_business_{business_id}", {
                    "business_id": business_id, "mapping": ctx.mapping, "warnings": ctx.db.warnings,
                    "error": ctx.error, "elapsed_ms": prep_ms})
                for i, q in enumerate(qs):
                    if guard.expired():
                        break
                    if q["id"] in writer.written:  # resumed run: its line and log stay as they are
                        continue
                    t1 = time.perf_counter()
                    excluded = config.exclude_examples(q) if config.exclude_examples else frozenset()
                    line, record = answer_question(q, ctx, calendar, rule_status, rulebook, llm,
                                                   config.twin_threshold, excluded)
                    # guideline §3.3 "including data reads": the shop's files are read and mapped once, before its
                    # first question, so that question's time includes them (business_prep_ms says how much)
                    record["elapsed_ms"] = round((time.perf_counter() - t1) * 1000) + (prep_ms if i == 0 else 0)
                    if i == 0:
                        record["business_prep_ms"] = prep_ms
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
                                  "decision": "abstain: hết thời gian hoặc không chạy tới", "elapsed_ms": 0,
                                  "thinking": None, "code": None, "output": None})
    summary.elapsed_s = guard.elapsed()
    return summary
