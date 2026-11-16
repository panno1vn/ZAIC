"""N170–N180 (train blanks 10/11): debt readings ("nowj", unit_split on money, a debt age left out, a customer left
out, a debt written only as a term of credit), the catalogue's cost of a moved mapping, "hàng tồn kho" as no filter,
counting in ly ("ly ta", revenue not asked, "mọi món tính theo ly", unit_split without "chẵn / lẻ")."""
import pandas as pd

from datamate import nlu
from datamate.contracts import CanonicalDB, QueryPlan
from datamate.nlu import grounding
from datamate.verify import not_recorded


def plan(**kw) -> QueryPlan:
    return QueryPlan.model_validate({"period": {"kind": "until", "date": "2025-10-30"}, "intent": "value", **kw})


def test_no_typed_with_telex_is_no_customer():
    assert nlu._generic_value("nowj", "customer")
    assert nlu._generic_value("nợ", "customer")
    assert not nlu._generic_value("Nguyễn Văn Nợ", "customer")


def test_money_has_no_whole_and_odd_units():
    p = plan(measures=[{"metric": "debt_total", "unit_split": True,
                        "filters": [{"field": "debt_age_days", "op": "gt", "value": 15}]}])
    assert p.answer_type == "list"
    out = grounding.split_only_quantities(p)
    assert not out.measures[0].unit_split and out.answer_type == "number"
    stock = plan(measures=[{"metric": "stock_qty", "unit": "hộp", "unit_split": True,
                            "filters": [{"field": "product", "value": "X"}]}])
    assert grounding.split_only_quantities(stock) is stock


def test_a_debt_age_the_plan_left_out():
    q = "den het ngay 30/10/2025, nhung don dat cach do hon 15 ngay ma chua tra het con no tong cong bn"
    p = plan(measures=[{"metric": "debt_total", "filters": [{"field": "order_status", "value": "completed"},
                                                            {"field": "payment_method", "value": "credit"}]}])
    out = grounding.debt_age_added(q, p)
    assert [(f.field, f.op, f.value) for f in out.measures[0].filters] == [("debt_age_days", "gt", 15.0)]
    # the whole debt, no age written: as it was
    assert grounding.debt_age_added("đến hết 30/10/2025 khách còn nợ bao nhiêu", p) is p
    # two ages: no single reading
    assert grounding.debt_age_added("nợ các đơn quá 7 ngày và quá 15 ngày", p) is p


def test_the_customer_written_after_khach():
    customers = pd.DataFrame({"customer_key": ["k1", "k2"], "customer_name": ["Cao Thu Hạnh", "Lê Văn Tám"]})
    db = CanonicalDB(tables={"customers": customers, "orders": pd.DataFrame({"order_key": ["d1"]})}, readme="")
    q = "e thang 7/2026 khach cao thu hanh ghi no them bao nhieu va tra no dc bao nhieu"
    p = QueryPlan.model_validate({"intent": "value", "period": {"kind": "month", "year": 2026, "month": 7},
                                  "measures": [{"metric": "debt_added"}, {"metric": "debt_paid"}]})
    from datamate.contracts import ResolvedPlan
    r = ResolvedPlan.model_construct(plan=p, linked={}, link_scores={}, omitted=[])
    out = nlu.named_customer_added(r, db, q).plan
    assert all([(f.field, f.value) for f in m.filters] == [("customer", "cao thu hanh")] for m in out.measures)
    # no "khách" before the name, or a ranking: as it was
    assert nlu.named_customer_added(r, db, "cao thu hanh ghi no them bao nhieu") is r


def test_a_debt_written_only_as_a_term_of_credit():
    readme = ("# Dữ liệu\n## Cột trong `SoHanNo.xlsx`\n- **So hoa don**: mã đơn\n"
              "- **Hạn nợ (ngày)**: số ngày được nợ\n- **Han tra**: hạn thanh toán\n"
              "## Quy ước\n- **Hạn thanh toán**: chỉ đơn bán nợ có hạn.\n")
    db = CanonicalDB(tables={"orders": pd.DataFrame({"order_key": ["d1"], "customer_key": ["k"]})}, readme=readme, conventions=())
    p = plan(intent="rank", rank={"entity": "customer", "by": "debt_amount", "k": 3, "with_values": True},
             answer_type="table")
    assert not_recorded(p, "cho bảng 3 khách còn nợ nhìu nhất", db) == "công nợ"
    owed = CanonicalDB(tables=db.tables, readme=readme + "- **Còn nợ**: còn nợ\n")
    assert not_recorded(p, "cho bảng 3 khách còn nợ nhìu nhất", owed) is None


def test_the_stock_itself_is_no_category():
    assert nlu._generic_value("hàng tồn kho", "category")
    assert nlu._generic_value("mon tinh theo ly", "product")
    assert nlu._generic_value("mọi mặt hàng tính theo ly", "product")
    assert not nlu._generic_value("Trà sữa theo mùa", "product")


def test_counting_in_ly():
    p = QueryPlan.model_validate({"intent": "value", "period": {"kind": "yesterday"},
                                  "measures": [{"metric": "quantity", "unit": "ly"},
                                               {"metric": "quantity", "unit": "ly ta"}]})
    out = grounding.unit_particle_restated(p)
    assert [(m.metric, m.unit) for m in out.measures] == [("quantity", "ly")] and out.answer_type == "number"
    q = "quan ban duoc bn ly size l trong thang 4/2025, cong moi mon nhi"
    p = QueryPlan.model_validate({"intent": "value", "period": {"kind": "month", "year": 2025, "month": 4},
                                  "measures": [{"metric": "quantity", "unit": "ly",
                                                "filters": [{"field": "size", "value": "L"}]},
                                               {"metric": "revenue", "filters": [{"field": "size", "value": "L"}]}]})
    assert [m.metric for m in grounding.money_not_asked(q, p).measures] == ["quantity"]
    assert grounding.money_not_asked("bán bn ly size L và doanh thu size L", p) is p


def test_whole_and_odd_units_only_when_asked():
    m = {"metric": "quantity", "unit": "ly", "unit_split": True, "filters": [{"field": "product", "value": "X"}]}
    p = QueryPlan.model_validate({"intent": "value", "period": {"kind": "month", "year": 2026, "month": 4},
                                  "measures": [m]})
    assert not grounding.split_not_asked("tháng 4 bán đc mấy ly sinh tố xoài (m)", p).measures[0].unit_split
    asked = "cuối ngày hôm nay còn mấy hộp chẵn, mấy cái lẻ"
    assert grounding.split_not_asked(asked, p) is p


def test_the_catalogue_cost_a_moved_mapping_left_out():
    """N175: the catalogue's own "Giá vốn" (by its README meaning, else by its name: a POS's GiaVonHang)."""
    from pathlib import Path

    from datamate.contracts import ColumnMap, Mapping, RawBusiness, TableMap
    from datamate.mapping.from_readme import catalogue_cost
    from test_mapping_readme import section, table

    goods = {"Mã hàng": "mã hàng", "Tên hàng": "tên", "Giá bán": "giá bán hiện tại", "Giá vốn": "giá vốn"}

    def moved(columns):
        return Mapping(tables=[TableMap(target="products", sources=["sp.csv"], columns=[
            ColumnMap(target="product_key", source=columns[0]), ColumnMap(target="product_name", source=columns[1])])])

    raw = RawBusiness(root=Path("."), readme=section("sp.csv", goods),
                      tables=[table("sp.csv", [("SP1", "Panadol", "20000", "15000")], list(goods))])
    got = catalogue_cost(moved(list(goods)), raw)
    assert {c.target: c.source for c in got.tables[0].columns}["unit_cost"] == "Giá vốn"
    pos = ["MaHangHoa", "TenGoi", "GiaBanLe", "GiaVonHang"]
    raw = RawBusiness(root=Path("."), readme=section("sp.csv", {"MaHangHoa": "mã hàng", "TenGoi": "tên"}),
                      tables=[table("sp.csv", [("SP1", "Panadol", "20000", "15000")], pos)])
    got = catalogue_cost(moved(pos), raw)
    assert {c.target: c.source for c in got.tables[0].columns}["unit_cost"] == "GiaVonHang"
    # no cost column: as it was
    raw = RawBusiness(root=Path("."), readme="", tables=[table("sp.csv", [("SP1", "Panadol", "20000")], pos[:3])])
    m = moved(pos)
    assert catalogue_cost(m, raw) is m
