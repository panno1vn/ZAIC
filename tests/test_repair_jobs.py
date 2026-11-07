"""§6 Sửa xe of the public rulebook: the jobs of the "Làm gì" cell and the spellings of a vehicle line.
"Việc ghi trong ô Làm gì: lượt xe có làm một việc = phiếu có việc đó, tính một lượt. `Nhớt` ghi trơn là nhớt máy,
không phải nhớt láp; `ruột` ghi trơn là thay ruột mới, không phải vá. Sửa điện không gồm thay bóng đèn, thay ắc quy.
Phiếu bảo hành không tính là lượt làm việc đó." "Dòng xe: tên dòng xe chỉ khác hoa/thường hoặc ghi tắt là cùng
một dòng." """
from datetime import date, datetime

import pandas as pd

from datamate import metrics
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.nlu import jobs, link_entities, linking


def test_the_rulebook_readings_of_a_job():
    assert jobs.cell_jobs("nhớt") == {"nhot_may"} and jobs.cell_jobs("thay nhớt Motul") == {"nhot_may"}
    assert jobs.cell_jobs("nhớt láp") == {"nhot_lap"} and jobs.cell_jobs("láp") == {"nhot_lap"}
    assert jobs.cell_jobs("ruột") == {"thay_ruot"} and jobs.cell_jobs("vá ruột") == {"va"}
    assert jobs.cell_jobs("thay bóng đèn") == {"bong_den"} and jobs.cell_jobs("bình GS") == {"ac_quy"}
    assert jobs.cell_jobs("làm điện") == {"sua_dien"}
    assert jobs.job_of("thay dầu láp") == "nhot_lap" and jobs.job_of("sửa điện") == "sua_dien"
    assert jobs.job_of("vá ruột xe") == "va" and jobs.job_of("thay nhớt máy") == "nhot_may"
    assert jobs.job_of("đổi nhớt") == "nhot_may" and jobs.job_of("sửa xe") is None


def test_a_cell_lists_several_jobs_and_a_warranty_item_is_none():
    assert jobs.cell_jobs("BD, bố sau, curoa") == {"bao_duong", "bo_thang_sau", "bo_thang", "curoa"}
    assert jobs.cell_jobs("thay nhớt Motul + lọc gió") == {"nhot_may", "loc_gio"}
    assert jobs.cell_jobs("BH vá") == frozenset() and jobs.job_of("bảo hành vá") is None
    assert jobs.cell_jobs("độ pô") is None  # a job none of the names reads: unknown, not "no job"


def test_the_spellings_of_a_line_are_one_line_and_a_shared_word_is_none():
    lines = linking.model_lines(frozenset({"Air Blade", "airblade", "AB", "Wave Alpha", "Wave α", "Alpha",
                                           "Wave RSX", "RSX", "Exciter", "Ex", "SH Mode", "shmode", "Vision 110",
                                           "vision", "Wave"}))
    assert {lines[s] for s in ("Air Blade", "airblade", "AB")} == {"Air Blade"}
    assert {lines[s] for s in ("Wave Alpha", "Wave α", "Alpha")} == {"Wave Alpha"}
    assert {lines[s] for s in ("Wave RSX", "RSX")} == {"Wave RSX"}
    assert lines["Ex"] == "Exciter" and lines["shmode"] == "SH Mode" and lines["vision"] == "Vision 110"
    assert lines["Wave"] is None  # Wave Alpha or Wave RSX


def shop() -> CanonicalDB:
    t = lambda d: datetime(2026, 6, d)  # noqa: E731
    o = pd.DataFrame([
        ("1", t(1), "AB", "59B6-219.16", "thay nhớt Motul + lọc gió", 150_000, False),
        ("2", t(2), "Air Blade", "72L7-223.37", "nhớt láp", 90_000, False),
        ("3", t(3), "airblade", "50K2-994.07", "vá ruột, làm điện", 120_000, False),
        ("4", t(4), "Wave α", "59B6-219.16", "BH vá", 0, True),
        ("5", t(5), "wave alpha", "61V1-102.07", "nhớt, thay bóng đèn", 110_000, False),
    ], columns=["order_id", "order_time", "vehicle_model", "vehicle_plate", "services", "goods_amount", "is_warranty"])
    o["status"], o["has_time"] = "completed", False
    return CanonicalDB(tables={"orders": o})


def run(db, raw):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"period": {"kind": "this_month"}, **raw}), as_of=date(2026, 6, 30),
                        period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30)))
    plan = link_entities(plan, db)
    r = metrics.execute(plan, db)
    return None if r is None else r.value


def test_tickets_of_a_job_and_vehicles_of_a_line():
    """Engine oil: tickets 1 and 5 (2 is nhớt láp); a patch: ticket 3 (4 is a warranty ticket); electrics: 3 (5 is a
    bulb). Air Blade: 3 tickets in three spellings; Wave Alpha: 2 vehicles, the warranty visit included."""
    service = lambda job: {"intent": "value", "measures": [  # noqa: E731
        {"metric": "ticket_count", "filters": [{"field": "service", "value": job}]}]}
    assert run(shop(), service("thay nhớt")) == 2
    assert run(shop(), service("thay dầu láp")) == 1
    assert run(shop(), service("vá ruột xe")) == 1
    assert run(shop(), service("sửa điện")) == 1
    model = lambda name, metric: {"intent": "value", "measures": [  # noqa: E731
        {"metric": metric, "filters": [{"field": "vehicle_model", "value": name}]}]}
    assert run(shop(), model("Air Blade", "ticket_count")) == 3
    assert run(shop(), model("Wave Alpha", "vehicle_count")) == 2
    assert run(shop(), {"intent": "rank", "rank": {"entity": "vehicle_model", "by": "revenue", "k": 1}}) == "Air Blade"


def test_a_ledger_with_an_unread_job_answers_no_job_question():
    db = shop()
    db.tables["orders"].loc[0, "services"] = "độ pô"
    assert run(db, {"intent": "value", "measures": [
        {"metric": "ticket_count", "filters": [{"field": "service", "value": "thay nhớt"}]}]}) is None
