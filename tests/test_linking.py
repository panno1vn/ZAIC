"""[C3] linking (G6): filter names as written -> data values, on a tiny shop built by hand."""
from datetime import date

import pandas as pd

from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPlan
from datamate.nlu import link_entities, linking
from datamate.verify import collect_signals
from datamate.contracts import Mapping


def shop(payment=("Tiền mặt", "Chuyển khoản", "cash"), employee=("NV001", "NV002", "NV001")) -> CanonicalDB:
    lines = pd.DataFrame({
        "order_id": ["o1", "o2", "o3", "o3", "o2"],
        "product_key": ["SP0001", "SP0002", "SP0003", "SP0004", "SP0005"],
        "product_name": ["Nước ép dưa hấu (L)", "Cà phê đen (M)", "Cà phê đen (L)", "Bột ngọt Ajinomoto 400g",
                         "Panadol Extra hộp 15 vỉ"],
        "line_amount": [1.0] * 5,
    })
    products = pd.DataFrame({
        "product_key": ["SP0001", "SP0002", "SP0003", "SP0004", "SP0005", "SP0006"],
        "product_name": ["Nước ép dưa hấu size L", "Cà phê đen (M)", "Cà phê đen (L)", "Bột ngọt Ajinomoto 400g",
                         "Panadol Extra hộp 15 vỉ x 12 viên", "Hapacol 250"],
        "product_group": ["nước ép", "cà phê", "cà phê", "gia vị", "giảm đau hạ sốt", "giảm đau hạ sốt"],
        "active_ingredient": [None, None, None, None, "Paracetamol + Cafein", "Paracetamol"],
    })
    orders = pd.DataFrame({
        "order_id": ["o1", "o2", "o3"], "status": ["completed"] * 3,
        "customer_key": ["KH0001", "KH0002", None], "customer_name": ["Quách Bình Anh", "Hà Lan Nhung", "Khách lẻ"],
        "customer_group": ["thân thiết", "sỉ", None], "channel": ["store", "zalo_oa", "store"],
        "payment_method": list(payment), "employee": list(employee),
    })
    employees = pd.DataFrame({"employee_key": ["NV001", "NV002", "NV009"],
                              "employee_name": ["Bùi Dũng Lan", "La Thu Quân", "Phùng Thu Trang"]})
    return CanonicalDB(tables={"lines": lines, "products": products, "orders": orders, "employees": employees})


def link(field, written, question="", db=None):
    db = db or shop()
    return linking.link_value(field, written, question, linking.candidates(field, db))


def test_exact_after_folding_any_spelling_and_names_of_one_code():
    assert link("product", "nuoc ep dua hau (l)").value == "SP0001"
    assert link("product", "Nước ép dưa hấu size L").value == "SP0001"  # the catalogue's name for the same code
    assert link("product", "nuowcs eps duwa haaus (L)").value == "SP0001"  # telex typed without the input method
    assert link("product", "SP0004") == linking.Link("SP0004", 100.0, "exact")


def test_small_typo_links_by_fuzzy_score():
    got = link("product", "Bot ngot Ajinomoto 400")
    assert (got.value, got.how) == ("SP0004", "fuzzy") and got.score >= linking.THRESHOLD


def test_two_close_candidates_are_not_linked():
    got = link("product", "ca phe den")  # (M) or (L): the question does not say
    assert got.value is None and got.how == "tie"


def test_a_shortened_name_links_to_the_full_name_written_in_the_question():
    got = link("customer", "bình anh", "tháng này khách quách bình anh ghi nợ thêm bao nhiu")
    assert (got.value, got.how) == ("KH0001", "question")
    assert link("customer", "bình anh").value is None  # without the question: too far from any name


def test_a_miscopied_name_links_to_the_name_the_question_carries():
    """Train run 03/11: the LLM wrote "Nguyễn Mai Hiếu" for "khách nghiêm mai hiếu", "sinh tu bo" for "sinh tố bơ (m)"."""
    db = shop()
    db.tables["orders"].loc[1, "customer_name"] = "Nghiêm Mai Hiếu"
    got = link("customer", "Nguyễn Mai Hiếu", "tháng 1/2025 khách nghiêm mai hiếu mua chịu thêm bao nhiêu", db)
    assert (got.value, got.how) == ("KH0002", "question")
    # two names of the question share the words: no guess
    assert link("product", "ca phe", "so cà phê đen (M) với cà phê đen (L)").how == "tie"


def test_a_counting_unit_in_front_of_a_product_name_is_dropped():
    """Train run 03/11: "bình Gas Petrolimex 12kg", "xe 4m3 cát xây tô" (the unit the question counts in)."""
    db = shop()
    sand = pd.DataFrame({"order_id": ["o1"], "product_key": ["SP0009"], "product_name": ["Cát xây tô"],
                         "line_amount": [1.0], "unit": ["xe 4m3"]})
    db.tables["lines"] = pd.concat([db.tables["lines"].assign(unit="ly"), sand], ignore_index=True)
    units = linking.units(db)
    assert units == ("xe 4 m 3", "ly")
    cands = linking.candidates("product", db)
    assert linking.link_value("product", "xe 4m3 cat xay to", "", cands, units).value == "SP0009"
    assert linking.link_value("product", "xe 4m3 cat xay to", "", cands).value is None  # too far for the fuzzy score


def test_names_that_are_not_customers_are_not_linked():
    assert link("customer", "nữ", "tháng 1/2026 khách nữ mua bao nhiêu tiền").value is None
    assert link("customer", "đường Hậu Giang", "có bao nhiêu khách ở đường Hậu Giang").value is None


def test_combination_drug_is_its_own_ingredient():
    assert link("active_ingredient", "paracetamol").value == "Paracetamol"
    assert link("active_ingredient", "Paracetamol + Cafein").value == "Paracetamol + Cafein"


def test_channel_and_payment_link_to_codes_through_synonyms():
    assert link("channel", "tại quầy").value == "store"
    assert link("channel", "Zalo OA").value == "zalo_oa"
    assert link("payment_method", "ck").value == "transfer"
    assert link("payment_method", "tiền tươi").value == "cash"
    assert link("payment_method", "ví điện tử").value is None  # the shop records no e-wallet payment
    assert link("payment_method", "tiền tự").value is None  # an LLM misreading of "tiền tươi": no synonym


def test_matches_reads_codes_and_words_in_one_column():
    col = pd.Series(["cash", "Tiền mặt", "Chuyển khoản", None, "Thu hộ (COD)"])
    assert linking.matches("payment_method", col, "cash").tolist() == [True, True, False, False, False]
    assert linking.matches("payment_method", col, "cod").tolist() == [False, False, False, False, True]
    assert linking.matches("product", pd.Series(["SP0001", None]), "SP0001").tolist() == [True, False]


def test_employee_links_to_the_value_orders_carry():
    assert link("employee", "Bùi Dũng Lan").value == "NV001"
    assert link("employee", "nv002").value == "NV002"
    assert link("employee", "Phùng Thu Trang").value is None  # on the staff list, on no order: filtering would give 0
    by_name = shop(employee=("Bùi Dũng Lan", "La Thu Quân", "Bùi Dũng Lan"))
    assert link("employee", "Bùi Dũng Lan", db=by_name).value == "Bùi Dũng Lan"
    assert link("employee", "NV001", db=by_name).value is None  # a code orders do not carry


def test_link_entities_fills_linked_and_unlinked_names_make_the_question_abstain():
    plan = QueryPlan.model_validate({"intent": "compare", "period": {"kind": "this_month"},
                                     "measures": [{"metric": "revenue", "filters": [{"field": "channel", "value": "tại quầy"}]}],
                                     "compare": {"kind": "filter", "filters": [{"field": "channel", "value": "zalo"}]}})
    db = shop()
    got = link_entities(ResolvedPlan(plan=plan, as_of=date(2026, 6, 1)), db, "doanh thu tại quầy so với zalo")
    assert got.linked == {"tại quầy": "store", "zalo": "zalo_oa"}
    assert collect_signals(got, None, db, Mapping(), {}).entities_ok

    plan = QueryPlan.model_validate({"intent": "value", "period": {"kind": "this_month"},
                                     "measures": [{"metric": "revenue", "filters": [{"field": "product", "value": "ca phe den"}]}]})
    got = link_entities(ResolvedPlan(plan=plan, as_of=date(2026, 6, 1)), db, "doanh thu ca phe den")
    assert got.linked == {} and got.link_scores["ca phe den"] >= linking.THRESHOLD
    assert not collect_signals(got, None, db, Mapping(), {}).entities_ok


def test_a_northern_name_links_to_the_southern_one_of_the_data_and_back():
    """Public 06/11: "Lạc rang muối 200g" for the shop's "Đậu phộng rang muối 200g", "Đậu phụ rán giòn" for "Đậu hũ
    chiên giòn". With diacritics only: "lắc" is no "lạc", and an unaccented "lac" could be either."""
    cands = {"dau phong rang muoi 200 g": frozenset({"Đậu phộng rang muối 200g"}),
             "dau hu chien gion": frozenset({"Đậu hũ chiên giòn"}), "lac": frozenset({"Lạc"})}
    assert linking.link_value("product", "Lạc rang muối 200g", "", cands).value == "Đậu phộng rang muối 200g"
    assert linking.link_value("product", "Đậu phụ rán giòn", "", cands).value == "Đậu hũ chiên giòn"
    assert linking.link_value("product", "lac rang muoi 200g", "", cands).value is None
    assert linking.dialects("khoai tây lắc") == [] and linking.dialects("Đậu phộng") == ["lạc"]
