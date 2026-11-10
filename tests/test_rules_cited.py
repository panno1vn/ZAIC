"""N166: a rule row is cited when the plan depends on it (filter, ranked entity, comparison, period kind), so a
rulebook that edits an industry's section no longer blanks every answer; the §2 period rows are cited by period kind."""
from datetime import date
from pathlib import Path

import pytest

from datamate import metrics, pipeline, rules
from datamate.contracts import QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.metrics import sales, stock
from tests.test_metrics_sales import JUNE, shop

DATA = Path(__file__).resolve().parents[1] / "data"
OLD_BLANKET = ("§1.doanh_thu_theo_hinh_thuc_thanh_toan", "§1.doanh_thu_theo_nhom_khach", "§2.ca_sang_ca_chieu",
               "§3.nhom_hang", "§3.xac_dinh_khach", "§6.ca_phe.size_m_size_l", "§6.nha_thuoc.doanh_thu_theo_hoat_chat",
               "§6.nha_thuoc.thuoc_ke_don", "§8.ten_goi_nhan")


def cited(raw: dict, period=JUNE, linked=None, compare_period=None) -> set[str]:
    plan = ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=date(2026, 6, 30), period=period,
                        linked=linked or {}, compare_period=compare_period)
    r = metrics.execute(plan, shop())
    assert r is not None
    return set(r.rule_ids)


def value(filters=(), metric="revenue", period=None, **kw):
    raw = {"intent": "value", "measures": [{"metric": metric, "filters": list(filters)}],
           "period": period or {"kind": "this_month"}}
    return cited(raw, **kw)


def test_plain_revenue_cites_no_filter_or_industry_row():
    ids = value()
    assert not ids & set(OLD_BLANKET)
    assert {"§1.don_tinh_vao_doanh_thu", "§2.thang_nay"} <= ids


@pytest.mark.parametrize("field,val,linked,expected", [
    ("payment_method", "tiền mặt", {"tiền mặt": "cash"}, "§1.doanh_thu_theo_hinh_thuc_thanh_toan"),
    ("customer_group", "sỉ", {"sỉ": "sỉ"}, "§1.doanh_thu_theo_nhom_khach"),
    ("shift", "morning", None, "§2.ca_sang_ca_chieu"),
    ("product_group", "cà phê", {"cà phê": "cà phê"}, "§3.nhom_hang"),
])
def test_a_filter_cites_its_rows(field, val, linked, expected):
    ids = value([{"field": field, "value": val}], linked=linked)
    assert expected in ids
    assert "§6.ca_phe.size_m_size_l" not in ids and "§6.nha_thuoc.thuoc_ke_don" not in ids


def test_size_and_industry_filters_cite_the_industry_row():
    assert "§6.ca_phe.size_m_size_l" in value([{"field": "size", "value": "M"}], metric="quantity")


def test_a_name_filter_cites_the_naming_row_a_coded_one_does_not():
    assert "§8.ten_goi_nhan" in value([{"field": "product", "value": "bia"}], linked={"bia": "SP3"})
    assert "§8.ten_goi_nhan" not in value([{"field": "shift", "value": "morning"}])


def test_share_denominator_and_compared_filters_count():
    share = {"intent": "share", "measures": [{"metric": "revenue", "filters": []}],
             "share_of": {"metric": "revenue", "filters": [{"field": "payment_method", "value": "tiền mặt"}]},
             "period": {"kind": "this_month"}}
    assert "§1.doanh_thu_theo_hinh_thuc_thanh_toan" in cited(share, linked={"tiền mặt": "cash"})
    comp = {"intent": "compare", "measures": [{"metric": "revenue"}], "period": {"kind": "this_month"},
            "compare": {"kind": "filter", "filters": [{"field": "shift", "value": "morning"}]}}
    assert "§2.ca_sang_ca_chieu" in cited(comp)


def test_compare_cites_its_output_and_kind_only():
    base = {"intent": "compare", "measures": [{"metric": "revenue"}], "period": {"kind": "month", "month": 6}}
    ids = cited({**base, "compare": {"kind": "previous"}},
                compare_period=ResolvedPeriod(start=date(2026, 5, 1), end=date(2026, 5, 31)))
    assert "§1.phan_tram_thay_doi_tang_truong" in ids and "§2.tet_nam_y_dip_tet_mua_tet" not in ids \
        and "§5.hieu_ung_tang_gia" not in ids


def test_rank_cites_by_measure_and_entity():
    q = lambda by, entity: {"intent": "rank", "measures": [{"metric": by}], "period": {"kind": "this_month"},  # noqa: E731
                            "rank": {"entity": entity, "by": by, "k": 1}}
    qty = cited(q("quantity", "product"))
    assert "§3.ban_chay" in qty and "§3.nhan_vien_ban_gioi_nhat" not in qty and "§3.xac_dinh_khach" not in qty
    assert "§3.xac_dinh_khach" in cited(q("revenue", "customer"))
    assert "§3.nhan_vien_ban_gioi_nhat" in cited(q("revenue", "employee"))


def test_period_rows():
    kinds = {"this_week": {"kind": "this_week"}, "last_n_days": {"kind": "last_n_days", "n": 7},
             "ytd": {"kind": "ytd"}, "tet": {"kind": "tet"}}
    want = {"this_week": "§2.tuan", "last_n_days": "§2.n_ngay_gan_nhat", "ytd": "§2.tu_dau_nam_tu_dau_nam_toi_nay",
            "tet": "§2.tet_nam_y_dip_tet_mua_tet"}
    for k, period in kinds.items():
        assert want[k] in value(period=period), k
    assert metrics.YEARLESS[0] in value(period={"kind": "month", "month": 6})
    assert metrics.YEARLESS[0] not in value(period={"kind": "month", "month": 6, "year": 2026})


def test_stock_in_a_larger_unit_cites_its_row_only_when_asked():
    assert "§5.ton_theo_don_vi_lon" not in stock.R_STOCK and stock.R_UNIT_SPLIT == ("§5.ton_theo_don_vi_lon",)


def test_every_citable_rule_is_checked():
    checked = set(pipeline.rule_ids())
    citable = {r for rs in sales.FILTER_RULES.values() for r in rs} | set(sales.R_NAMES) | \
        {r for rs in sales.ENTITY_RULES.values() for r in rs} | {r for rs in metrics.PERIOD_RULES.values() for r in rs} \
        | set(metrics.YEARLESS) | set(sales.R_COMPARE) | set(sales.R_RANK) | set(sales.R_COUNT) | set(stock.R_UNIT_SPLIT)
    assert citable <= checked
    for split in ("train", "public_test"):
        book = DATA / split / "rulebook.md"
        if not book.exists():
            continue
        status = rules.check_rules(book.read_text(encoding="utf-8-sig"), tuple(sorted(citable)))
        have_version = rules.train_rule_ids() if split == "train" else None
        bad = sorted(r for r, ok in status.items() if not ok and (have_version is None or r in have_version))
        assert bad == [] or split == "public_test", (split, bad)
