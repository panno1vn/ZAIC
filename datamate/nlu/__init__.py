"""[C] Understand the question: ask the LLM for a QueryPlan (structured output), cross-checked with the rule-based
baseline. Work package G3. [C3] Link names in the plan to values in the data. Work package G6.

Without an LLM only the baseline answers (a few frequent shapes). With an LLM, a plan is kept only if it validates and,
when the baseline also reads the question, both readers agree: two readings that differ are not worth a guess.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date

from datamate.contracts import STOCK_METRICS, CanonicalDB, DataCard, QueryPlan, ResolvedPlan
from datamate.llm import LLMClient

from datamate.verify import LINKED_FIELDS, SUBJECTIVE_REASON, filter_keys

from . import baseline, jobs, linking, prompt, repair
from .grounding import (anchor_by_price, count_as_value, count_not_list, drop_month_as_weekday, drop_restated_metric,
                        debt_age_from_question, in_minus_out, k_not_the_month, rulebook_rank_terms, share_as_value,
                        weekday_as_stated, which_time_as_rank, whole_as_share_of,
                        drop_restated_status, drop_ungrounded_years, month_of_short_year, one_name_no_values,
                        orders_not_money, overdue_customers, rate_as_value, scale_money, split_debt_ages,
                        subjective_quality,
                        ungrounded_dates,
                        ungrounded_filters, ungrounded_measures, unit_filter_as_unit, unpaid_as_debt, whole_not_part,
                        widen_each_table, written_last_year)


def _fold_value(v):
    if isinstance(v, str):
        t = unicodedata.normalize("NFD", v.lower()).replace("đ", "d")
        return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())
    return [_fold_value(x) for x in v] if isinstance(v, list) else v


def canonical_plan(plan: QueryPlan) -> dict:
    """The plan as compared between readers, with the differences that do not change its meaning removed: defaults,
    free-text notes, the derived answer type, case and diacritics of names and units, the measure that only repeats
    the ranking or threshold metric, and "today" as the period of a stock metric (no period means today too)."""
    d = plan.model_dump(mode="json", exclude_none=True, exclude_defaults=True,
                        exclude={"notes", "out_of_scope_reason", "answer_type"})

    def walk(x):
        if isinstance(x, dict):
            return {k: (_fold_value(v) if k in ("value", "unit") else walk(v)) for k, v in x.items() if k != "note"}
        return [walk(v) for v in x] if isinstance(x, list) else x
    d = walk(d)
    own = d.get("rank", {}).get("by") or d.get("threshold", {}).get("metric")
    if own and d.get("measures") == [{"metric": own}]:
        d.pop("measures")
    if d.get("period") == {"kind": "today"} and plan.measures and all(m.metric in STOCK_METRICS for m in plan.measures):
        d.pop("period")
    return d


RETRY_ASK = ("JSON vừa viết không hợp lệ với schema: {error}\nHãy viết lại plan cho đúng câu hỏi trên, sửa đúng chỗ sai, "
             "chỉ dùng các giá trị schema cho phép; câu không nói tới điều gì thì không thêm bộ lọc đó.")


def _valid_plan(out, question: str) -> tuple[QueryPlan | None, str | None]:
    """(the plan, None) when `out` is valid; (the repaired plan, the error) when N32 repairs it; (None, the error)."""
    try:
        return QueryPlan.model_validate(out), None
    except Exception as e:  # N32: an invalid shape seen on train, rewritten into the plan it means
        fixed = repair.repair(out, question, str(e))
        try:
            return (QueryPlan.model_validate(fixed) if fixed is not None else None), str(e)
        except Exception:
            return None, str(e)


def llm_plan(question: str, as_of: date, card: DataCard, llm: LLMClient,
             bank: prompt.ExampleBank | None = None, exclude_ids: frozenset[str] = frozenset(),
             trace: dict | None = None) -> QueryPlan | None:
    """The LLM's plan, or None when the call fails or times out, the output is not a valid plan, or it has a filter
    or a day the question gives no ground for (grounding.py). A year the question does not state is dropped, so §2
    decides it. `trace` (the run's log of the question) gets the raw output and why a plan was not used."""
    trace = {} if trace is None else trace
    bank = bank or prompt.default_bank()
    messages = prompt.build_messages(question, as_of, card, bank.select(question, exclude_ids=exclude_ids))
    try:
        out = llm.generate_json(messages, prompt.PLAN_SCHEMA)
    except Exception as e:
        trace["llm_error"] = type(e).__name__
        return None
    trace["llm_raw"] = out
    plan, error = _valid_plan(out, question)
    if plan is None and error is not None:
        # N78: one more call with the output and what is wrong with it (run11 07/11: 14 public outputs broke the
        # schema in a way no repair knows, e.g. a shift filter "store"); greedy decoding repeats itself, the error does
        # not. The retried plan goes through every gate as any other.
        retry = messages + [{"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                            {"role": "user", "content": RETRY_ASK.format(error=error[:600])}]
        try:
            again = llm.generate_json(retry, prompt.PLAN_SCHEMA)
        except Exception as e:
            trace["retry_error"] = type(e).__name__
            again = None
        if again is not None:
            trace["llm_raw_retry"] = again
            plan, _ = _valid_plan(again, question)
        trace["retry"] = "ok" if plan is not None else "failed"
    if plan is None:
        trace["invalid"] = "unrepaired"
        return None
    if error is not None and "retry" not in trace:
        trace["invalid"] = "repaired"
    plan, problems = plan_problems(question, plan, as_of)
    if problems and GROUND_RETRY and "retry" not in trace:
        # N79: the plan has parts the question gives no ground for (most often the LLM read one case as another: "bnhiu
        # đh" as revenue); one more call shown those parts, at most one retry per question. The new plan meets the
        # same gates, and the twin gate after them.
        trace["rejected_first"] = problems
        retry = messages + [{"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                            {"role": "user", "content": RETRY_GROUND.format(parts=", ".join(problems))}]
        try:
            again = llm.generate_json(retry, prompt.PLAN_SCHEMA)
        except Exception as e:
            trace["retry_error"] = type(e).__name__
            again = None
        second = None
        if again is not None:
            trace["llm_raw_retry"] = again
            second, _ = _valid_plan(again, question)
        if second is not None:
            plan, problems = plan_problems(question, second, as_of)
        trace["retry"] = "ok" if second is not None and not problems else "failed"
    if problems:
        trace["rejected"] = problems
    return None if problems else plan


# N79: one retry when the grounding gates refuse a plan. ON since 08/11: train as run (prod_train, 1500 questions)
# 16 more right, 0 wrong; public s41r − s41 = +0.020, the 20 answers it opened all right
GROUND_RETRY = True
RETRY_GROUND = ("Plan vừa viết có phần câu hỏi không nói tới, hoặc đọc sai loại câu: {parts}.\nĐọc lại câu hỏi và viết "
                "lại plan chỉ theo đúng điều câu hỏi hỏi: đúng chỉ số (tiền, số đơn, số lượng, số khách…), đúng loại câu "
                "(một số, so sánh, xếp hạng, danh sách…), không thêm bộ lọc hay kỳ mà câu không nêu.")


def plan_problems(question: str, plan: QueryPlan, as_of: date | None = None) -> tuple[QueryPlan, list[str]]:
    """The plan after the drops (years the question does not state, restated filters) and what in it has no ground
    in the question: filters, days, measures (grounding.py)."""
    plan = which_time_as_rank(question, rulebook_rank_terms(question, in_minus_out(question, plan)))
    # whole_not_part first: a share_of written as the part itself hides the whole written as a second measure (a full
    # public run 08/11: "bỉm size NB … % tổng số bịch bỉm" read so on one run, without the share_of on the other)
    plan = k_not_the_month(question, whole_as_share_of(whole_not_part(debt_age_from_question(question, plan))))
    plan = weekday_as_stated(question, share_as_value(question, count_not_list(question, plan)))
    plan = widen_each_table(question, one_name_no_values(question, plan))
    plan = scale_money(question, count_as_value(month_of_short_year(question, plan)))
    plan = orders_not_money(question, unit_filter_as_unit(question, rate_as_value(plan)))
    plan = overdue_customers(question, unpaid_as_debt(question, plan))
    plan = whole_not_part(split_debt_ages(drop_month_as_weekday(question, anchor_by_price(question, plan, as_of))))
    plan = written_last_year(plan)
    plan = drop_ungrounded_years(question, plan, as_of)
    plan = drop_restated_metric(drop_restated_status(question, drop_implied_filters(plan)))
    return plan, (ungrounded_filters(question, plan) + ungrounded_dates(question, plan, as_of)
                  + ungrounded_measures(question, plan))


def accept_plan(question: str, plan: QueryPlan, as_of: date | None = None) -> QueryPlan | None:
    """An LLM plan as the pipeline may use it: years the question does not state dropped, None when a filter or a
    day has no ground in the question (grounding.py)."""
    plan, problems = plan_problems(question, plan, as_of)
    return None if problems else plan


def drop_implied_filters(plan: QueryPlan) -> QueryPlan:
    """cancel_count / cancel_rate count cancelled orders already: an order_status = cancelled filter on them only
    restates the metric (12 of 2895 build_bank plans, 04/11), and on cancel_rate would make every rate 100%."""
    def fix(m):
        kept = [f for f in m.filters if not (f.field == "order_status" and f.value == "cancelled")]
        return m.model_copy(update={"filters": kept}) if len(kept) < len(m.filters) else m
    measures = [fix(m) if m.metric in ("cancel_count", "cancel_rate") else m for m in plan.measures]
    return plan.model_copy(update={"measures": measures}) if measures != list(plan.measures) else plan


def parse_question(question: str, as_of: date, card: DataCard, llm: LLMClient | None = None,
                   exclude_ids: frozenset[str] = frozenset(), trace: dict | None = None) -> QueryPlan | None:
    """QueryPlan for the question, or None when it cannot be parsed into a valid plan both readers agree on.
    `exclude_ids`: examples the LLM may not see (development runs on train leave out the business's own questions).
    `trace` gets how the reading went (llm_plan's notes, the baseline's plan when the two disagree)."""
    trace = {} if trace is None else trace
    base = baseline.parse(question)
    if llm is None:
        return base
    plan = llm_plan(question, as_of, card, llm, exclude_ids=exclude_ids, trace=trace)
    if plan is None and base is None and subjective_quality(question):
        # N83: no reading holds and the question asks a quality the data does not record: unanswerable (§7)
        trace["subjective"] = True
        return QueryPlan(intent="out_of_scope", out_of_scope_reason=SUBJECTIVE_REASON)
    if plan is None:
        return base  # the LLM failed or its plan had no ground: the baseline's reading, if it has one
    if plan.intent == "out_of_scope" and subjective_quality(question):
        # N83: the LLM reads it out of scope and the question asks a quality the data does not record: unanswerable
        # even with a time ("Khách trung thực nhất tháng 10/2025 là ai?"), which N37 otherwise leaves blank
        plan = plan.model_copy(update={"out_of_scope_reason": SUBJECTIVE_REASON})
    if base is not None and canonical_plan(_without_generic(plan)) != canonical_plan(base):
        trace["disagree_baseline"] = base.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
        return None
    return plan


def link_entities(plan: ResolvedPlan, db: CanonicalDB, question: str = "") -> ResolvedPlan:
    """Fill plan.linked / plan.link_scores: each name a filter carries, as written -> the data value it names
    (linking.py, G6). A name is left out when no value is clearly meant; [V] then makes the question abstain.
    `link_scores` keeps the best score of every name tried, linked or not, for the logs."""
    plan = attribute_in_its_field(product_as_attribute(unit_or_all_as_product(plan, db), db), db)
    plan = unit_from_question(drop_generic_filters(plan, db), db, question)
    p = plan.plan
    measures = list(p.measures) + ([p.share_of] if p.share_of else [])
    filters = [f for m in measures for f in m.filters] + list((p.compare.filters or []) if p.compare else [])
    linked, scores = dict(plan.linked), dict(plan.link_scores)
    for f in filters:
        if f.field not in LINKED_FIELDS:
            continue
        if f.field == "service":  # a repair job is a code of jobs.py, not a name of the data (§6 Sửa xe)
            for key in filter_keys(f):
                job = jobs.job_of(key) if db.has("orders", "services") else None
                scores[key] = 100.0 if job else 0.0
                if job:
                    linked[key] = job
            continue
        cands = linking.candidates(f.field, db)
        units = linking.units(db) if f.field == "product" else ()
        for key in filter_keys(f):
            got = linking.link_value(f.field, key, question, cands, units)
            scores[key] = got.score
            if got.value is not None:
                linked[key] = got.value
    omitted = (omitted_names(filters, db, question) + unit_not_recorded(plan, db, question)) if question else []
    return plan.model_copy(update={"linked": linked, "link_scores": scores, "omitted": omitted})


ATTRIBUTE_FIELDS = ("category", "product_line", "brand", "product_group")
_EVERY = {"tat ca", "tat ca cac mon", "tat ca mon", "tat ca mat hang", "tat ca cac mat hang", "moi mat hang", "moi mon",
          "toan bo", "toan bo mat hang", "cac mon", "all", "tat ca khach", "moi khach", "all customers"}


def unit_or_all_as_product(plan: ResolvedPlan, db: CanonicalDB) -> ResolvedPlan:
    """N76. A product filter that names no product of the shop but one of its counting units ("hôm qua bán được bao
    nhiêu ly": product = ly; train 07/11, 3 questions) is the unit the quantity counts in; a product or customer filter
    that names every one ("tất cả các món", "mọi mặt hàng", customer = all) is no filter. Only on a quantity, and
    only a value that links to no product."""
    p = plan.plan
    cands = units = None
    measures, changed = [], False
    for m in p.measures:
        kept, unit = [], m.unit
        for f in m.filters:
            v = linking.norm(f.value) if isinstance(f.value, str) and f.op == "eq" else None
            if v is not None and f.field in ("product", "customer") and v in _EVERY and len(p.measures) == 1:
                # one figure only: "mấy ly size M, cộng tất cả các món" read as [size M, every item] asks one figure
                # (train 07/11: dropping the second filter answered a list of two, 2 wrong)
                changed = True
                continue
            if v is not None and f.field == "product" and m.metric == "quantity":
                if cands is None:
                    cands, units = linking.candidates("product", db), linking.units(db)
                if v in units and (unit is None or linking.norm(unit) == v)                         and linking.link_value("product", f.value, "", cands, ()).value is None:
                    unit, changed = f.value, True
                    continue
            kept.append(f)
        measures.append(m.model_copy(update={"filters": kept, "unit": unit}) if kept != list(m.filters) else m)
    if not changed:
        return plan
    return plan.model_copy(update={"plan": p.model_copy(update={"measures": measures})})


# N88: words the LLM copies from the question into a filter that name no value of the shop: the shop itself ("wán mik",
# "sốp", "tiệm"), its customers in general ("khách"), the figure ("dthu", "tền" for tiền), a particle ("z"), a month
# ("T8"). Public run11: 9 such plans, every one stopped with no figure.
GENERIC_VALUES = frozenset({"quan", "wan", "shop", "sop", "tiem", "cua hang", "cuahang", "mik", "minh", "khach",
                            "khach hang", "dthu", "doanh thu", "tien", "ten", "z", "vay", "nha"})  # not "dt": "đt" is a phone
_MONTH_VALUE = re.compile(r"^(?:t|th|thang)\s?\d{1,2}(?:\s\d{2,4})?$")
GENERIC_FIELDS = ("product", "product_group", "category", "product_line", "brand", "customer", "customer_group",
                  "payment_method", "channel")


def _without_generic(plan: QueryPlan) -> QueryPlan:
    """The plan as the baseline is compared with it (N88): a filter of a generic word ("Th9/2025 tiệm tổng doanh thu":
    product = tiem) is no difference, drop_generic_filters removes it once the shop's names are known."""
    def keep(f) -> bool:
        if f.field not in GENERIC_FIELDS or f.op != "eq" or not isinstance(f.value, str):
            return True
        v = linking.norm(f.value)
        return v not in GENERIC_VALUES and not _MONTH_VALUE.match(v)
    measures = [m.model_copy(update={"filters": [f for f in m.filters if keep(f)]}) for m in plan.measures]
    return plan.model_copy(update={"measures": measures}) if measures != list(plan.measures) else plan


def drop_generic_filters(plan: ResolvedPlan, db: CanonicalDB) -> ResolvedPlan:
    """N88. A filter whose value is one of GENERIC_VALUES or a month, and links to no value of the shop, is no filter
    ("Doanh thu tháng 1/2025 của sốp mình": customer = sốp). Not when dropping it would leave two equal measures."""
    p = plan.plan

    def generic(f) -> bool:
        if f.field not in GENERIC_FIELDS or f.op != "eq" or not isinstance(f.value, str):
            return False
        v = linking.norm(f.value)
        if v not in GENERIC_VALUES and not _MONTH_VALUE.match(v):
            return False
        if f.field in ("payment_method", "channel"):
            return linking.concept(f.field, f.value) is None
        return linking.link_value(f.field, f.value, "", linking.candidates(f.field, db), ()).value is None

    measures = [m.model_copy(update={"filters": [f for f in m.filters if not generic(f)]})
                if any(generic(f) for f in m.filters) else m for m in p.measures]
    if measures == list(p.measures):
        return plan
    keys = [json.dumps(m.model_dump(mode="json"), sort_keys=True) for m in measures]
    if len(set(keys)) < len(keys):
        return plan
    return plan.model_copy(update={"plan": p.model_copy(update={"measures": measures})})


_COUNT_WORDS = r"(?:bao nhieu|bao nhiu|bnhiu|bnhieu|bn|may|nhieu|nhiu|tong cong|tong|cong)"


def unit_from_question(plan: ResolvedPlan, db: CanonicalDB, question: str) -> ResolvedPlan:
    """N80. §3 "bán được bao nhiêu <đơn vị>" counts only the items whose base unit is that unit. A quantity with no unit
    on a question that counts in one unit of the shop ("hôm qua bán được mấy lon": public 08/11, read with no unit,
    every item of a beer shop counted) gets that unit. Only one unit after a counting word ("bao nhiêu phần trăm" is
    none); not on a share, whose whole would keep counting every item, nor a ranking, threshold or list (§3 ranks items
    of different base units together)."""
    p = plan.plan
    if (not question or p.share_of is not None or p.rank is not None or p.threshold is not None
            or p.list_spec is not None or not any(m.metric == "quantity" and not m.unit for m in p.measures)):
        return plan
    found = _counted_in(question, linking.units(db))
    if len(found) != 1:
        return plan
    unit = found.pop()
    measures = [m.model_copy(update={"unit": unit}) if m.metric == "quantity" and not m.unit else m for m in p.measures]
    return plan.model_copy(update={"plan": p.model_copy(update={"measures": measures})})


def _counted_in(question: str, units) -> set[str]:
    """The units of `units` the question counts in: right after a counting word ("mấy lon", "bao nhiêu ly")."""
    if not units or not question:
        return set()
    alt = "|".join(re.escape(u) for u in units)
    return {m.group(1) for m in re.finditer(rf"\b{_COUNT_WORDS} ({alt})\b(?! tram)", linking.norm(question))}


# units that name a container or a measure, never "any item": "chiếc", "cái", "máy", "món" count every item of a
# shop that records no unit (a phone shop), these do not
SPECIFIC_UNITS = ("lon", "chai", "ly", "coc", "thung", "goi", "hop", "bich", "vi", "vien", "tuyp", "kg", "lit", "dia",
                  "to", "phan", "cay", "ket", "tui", "binh", "hu", "lo")


def unit_not_recorded(plan: ResolvedPlan, db: CanonicalDB, question: str) -> list[str]:
    """N80. A count in a unit the shop does not record ("hôm qua bán được mấy lon" where the mapping has no unit at all:
    public 08/11, two such questions answered with every item counted): the figure cannot be told, so the plan is
    refused like a name it leaves out. Only for a quantity still without its unit (unit_from_question gives a unit the
    shop records)."""
    p = plan.plan
    if (p.share_of is not None or p.rank is not None or p.threshold is not None or p.list_spec is not None
            or not any(m.metric == "quantity" and not m.unit for m in p.measures)):
        return []
    return [f"unit={u}" for u in sorted(_counted_in(question, SPECIFIC_UNITS) - set(linking.units(db)))]


def attribute_in_its_field(plan: ResolvedPlan, db: CanonicalDB) -> ResolvedPlan:
    """N93. A kind, group, line or brand written under another of these fields ("Nhóm gỏi" as category where the shop
    keeps it as product_group; "nhóm máy mới" as product_group where it is the category: public run11, 4 questions
    stopped with no figure): the field where the value is, when it links in none but its own field and is written
    exactly as one value of exactly one other field."""
    p = plan.plan
    if not any(f.field in ATTRIBUTE_FIELDS for m in p.measures for f in m.filters):
        return plan

    def field_of(f) -> str | None:
        if f.field not in ATTRIBUTE_FIELDS or f.op != "eq" or not isinstance(f.value, str):
            return None
        if linking.link_value(f.field, f.value, "", linking.candidates(f.field, db), ()).value is not None:
            return None
        hits = [a for a in ATTRIBUTE_FIELDS if a != f.field and linking.norm(f.value) in linking.candidates(a, db)]
        return hits[0] if len(hits) == 1 else None

    def fix(m):
        fs = [f.model_copy(update={"field": new}) if (new := field_of(f)) else f for f in m.filters]
        return m.model_copy(update={"filters": fs}) if fs != list(m.filters) else m
    measures = [fix(m) for m in p.measures]
    update = {"measures": measures}
    if p.share_of is not None:
        update["share_of"] = fix(p.share_of)
    if measures == list(p.measures) and update.get("share_of") is p.share_of:
        return plan
    return plan.model_copy(update={"plan": p.model_copy(update=update)})


def product_as_attribute(plan: ResolvedPlan, db: CanonicalDB) -> ResolvedPlan:
    """A "product" the shop has no product of, written exactly as one of its kinds, lines or brands (public phone
    ledgers, 06/11: "máy cũ bán mấy chiếc" with product = "máy cũ", the category of the abbreviation sheet; "Xiaomi
    Redmi Note 14" for the line of its 128GB and 256GB phones, §6 "dòng máy"): the filter of that attribute. Only an
    exact match (folded) in exactly one attribute, and only when no product links."""
    p = plan.plan
    if not any(f.field == "product" for m in p.measures for f in m.filters):
        return plan
    cands = linking.candidates("product", db)
    units = linking.units(db)

    def field_of(value) -> str | None:
        if not isinstance(value, str) or linking.link_value("product", value, "", cands, units).value is not None:
            return None
        hits = [a for a in ATTRIBUTE_FIELDS if linking.norm(value) in linking.candidates(a, db)]
        return hits[0] if len(hits) == 1 else None

    products = db.table("products")
    stages = {}
    if products is not None and "stage" in products.columns:
        from datamate.metrics.frames import _stage_core
        stages = {_stage_core(s): s for s in products["stage"].dropna().astype(str) if s.strip()}
    groups = linking.candidates("product_group", db)

    def group_and_stage(value) -> list[dict] | None:
        """"sữa bột số 2": a group of the shop followed by a "Số / Size" of its catalogue (§6 Mẹ và bé)."""
        if not isinstance(value, str) or not stages:
            return None
        v = linking.norm(value)
        for g in sorted(groups, key=len, reverse=True):
            if v.startswith(g + " "):
                from datamate.metrics.frames import _stage_core
                rest = _stage_core(v[len(g) + 1:])
                if rest in stages and len(groups[g]) == 1:
                    return [{"field": "product_group", "value": next(iter(groups[g]))},
                            {"field": "stage", "value": stages[rest]}]
        return None

    def fix(m):
        filters = []
        for f in m.filters:
            if f.field == "product" and (new := field_of(f.value)):
                filters.append(f.model_copy(update={"field": new}))
            elif f.field == "product" and (pair := group_and_stage(f.value)) and \
                    linking.link_value("product", f.value, "", cands, units).value is None:
                filters += [f.model_copy(update=x) for x in pair]
            else:
                filters.append(f)
        return m.model_copy(update={"filters": filters}) if filters != list(m.filters) else m
    measures = [fix(m) for m in p.measures]
    if measures == list(p.measures):
        return plan
    return plan.model_copy(update={"plan": p.model_copy(update={"measures": measures})})


OMISSION_FIELDS = ("customer", "product")


def omitted_names(filters: list, db: CanonicalDB, question: str) -> list[str]:
    """N36: names of the shop's customers or products (two words or more) the question writes as whole words while the
    plan has no filter of that field, nor a filter value holding the name ("nhóm cà phê sữa"). Train 05/11: "khách
    cao thu hạnh ghi nợ thêm bao nhiêu" read without the customer gave the shop's total; that was the only train
    question with such a name left out."""
    fields = {f.field for f in filters}
    values = [linking.norm(v) for f in filters for v in (f.value if isinstance(f.value, list) else [f.value])
              if isinstance(v, str)]
    text = f" {linking.norm(question)} "
    out = set()
    for field in OMISSION_FIELDS:
        if field in fields:
            continue
        for name in linking.candidates(field, db):
            if len(name.split()) >= 2 and f" {name} " in text and not any(name in v for v in values):
                out.add(f"{field}={name}")
    return sorted(out)
