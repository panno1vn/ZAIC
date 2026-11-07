"""The jobs of a repair ticket (public rulebook §6 Sửa xe, "Việc ghi trong ô Làm gì"): the cell lists every job of the
ticket, several to a cell ("thay nhớt Motul + lọc gió", "BD, bố sau, curoa"), each written many ways ("BD", "bdtq",
"bảo dưỡng xe"; "vs nồi", "làm nồi"). A job named in a question and a job written in the ledger meet on one code.

The rulebook's own readings come first: "`Nhớt` ghi trơn là nhớt máy, không phải nhớt láp; `ruột` ghi trơn là thay
ruột mới, không phải vá. Sửa điện không gồm thay bóng đèn, thay ắc quy. Phiếu bảo hành không tính là lượt làm việc
đó". The other names are the trade's usual ones (nhớt láp = nhớt hộp số = dầu láp; bố thắng = má phanh; NSD = nhông
sên dĩa; bình = ắc quy). A ledger with a job none of them reads makes every job filter abstain: a ticket that might
hold the asked job is never left out silently.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .linking import norm

WARRANTY = re.compile(r"^(bh|bao hanh)\b\s*")  # "BH vá", "bảo hành ruột": a warranty item, not the job (§6)
JOBS: tuple[tuple[str, re.Pattern], ...] = tuple((code, re.compile(p)) for code, p in (
    ("nhot_lap", r"^(nhot|dau) (lap|hop so)\b|^lap\b"),
    ("nhot_may", r"^(nhot|dau nhot|dau may)\b|^(castrol|motul|shel|shell)\b"),  # "nhớt" ghi trơn là nhớt máy
    ("va", r"^va\b"),
    ("thay_ruot", r"^ruot\b"),  # "ruột" ghi trơn là thay ruột mới
    ("bao_duong", r"^(bao duong|bd|bdtq)\b"),
    ("kim_phun", r"\bkim phun\b"),
    ("rua_xe", r"^rua\b"),
    ("noi", r"^((lam|ve sinh|vs) )?noi\b"),
    ("sua_dien", r"^((sua|lam) )?dien\b"),  # bóng đèn, ắc quy are jobs of their own
    ("bong_den", r"^(bong den|den)\b"),
    ("ac_quy", r"^(ac quy|binh)\b"),
    ("nhong_sen_dia", r"^(nsd|nhong sen dia|nhong xich|bo nhong)\b"),
    ("bo_thang_truoc", r"^(bo|bo thang|ma phanh|phanh) truoc\b"),
    ("bo_thang_sau", r"^(bo|bo thang|ma phanh|phanh) sau\b"),
    ("bo_thang", r"^(bo thang|ma phanh|phanh|bo)\b"),
    ("sen", r"^((chinh|can|tang) )?sen\b"),
    ("loc_gio", r"^loc gio\b"),
    ("bugi", r"^bu ?gi\b"),
    ("vo_xe", r"^vo\b"),
    ("curoa", r"^(day )?cu ?roa\b"),
    ("nuoc_mat", r"^nuoc (lam )?mat\b"),
))
WIDER = {"bo_thang_truoc": "bo_thang", "bo_thang_sau": "bo_thang"}  # "thay bố thắng" is either side
_THAY = re.compile(r"^(thay|doi|lam|sua|ve sinh|vs)\s+(?=\S)")  # "thay nhớt", "đổi nhớt": the job is the rest


def _code(item: str) -> str | None:
    for code, pattern in JOBS:
        if pattern.search(item):
            return code
    return None


def job_of(written: str) -> str | None:
    """The job a question names ("thay dầu láp" → nhot_lap), None when it names none or a warranty."""
    item = norm(written)
    if not item or WARRANTY.match(item):
        return None
    return _code(item) or _code(_THAY.sub("", item))


@lru_cache(maxsize=65536)
def cell_jobs(cell: str) -> frozenset[str] | None:
    """The jobs of one ticket's cell, warranty items left out; None when some item is no job we know."""
    out: set[str] = set()
    for part in re.split(r"[,+;/&]", str(cell)):
        item = norm(part)
        if not item:
            continue
        warranty = bool(WARRANTY.match(item))
        item = WARRANTY.sub("", item)
        code = _code(item) or _code(_THAY.sub("", item))
        if code is None:
            return None
        if not warranty:
            out |= {code, WIDER.get(code, code)}
    return frozenset(out)
