"""Classify train questions into intents and time expressions (rule-based, for the research docs)."""
import collections
import json
import re
import sys
import unicodedata

sys.stdout.reconfigure(encoding="utf-8")
ROOT = sys.argv[1]
SHOW = int(sys.argv[2]) if len(sys.argv) > 2 else 3


def fold(s):
    t = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.split())


ABBR = [(r"\bdthu\b|\bdt\b|\brevenue\b", "doanh thu"), (r"\bbnhiu\b|\bbn\b|\bbnhieu\b|\bbao nhiu\b|\bnhieu\b(?= z\b)", "bao nhieu"),
        (r"\bnhiu\b", "nhieu"), (r"\bko\b|\bhok\b|\bk\b", "khong"), (r"\bdc\b|\bđc\b", "duoc"), (r"\btrc\b", "truoc"),
        (r"\bhnay\b|\bbua nay\b|\bhom ni\b", "hom nay"), (r"\bbua qua\b|\bhqua\b", "hom qua"), (r"\bsp\b", "san pham"),
        (r"\bkh\b", "khach"), (r"\bvs\b", "voi"), (r"\btm\b", "tien mat"), (r"\bck\b", "chuyen khoan")]


def norm(q):
    t = fold(q)
    t = re.sub(r"(\w)(\1)(?=[a-z])", r"\1", t)  # light typo smoothing (doubled letters)
    for pat, rep in ABBR:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\b(?:th|t)\s*(\d{1,2})\s*/", r"thang \1/", t)
    return t


INTENTS = [  # (name, pattern) — first match wins, order matters
    ("price_effect", r"tang gia|len gia"),
    ("trend_bool", r"tang lien tuc|luon cao hon|giam lien tuc"),
    ("debt", r"\bno\b|cong no|tra no|thu no|tra gop|\bgop\b|tuoi no"),
    ("inventory", r"\bton\b|het hang|het han|\blo\b|han dung"),
    ("purchase", r"nhap|nha cung cap|\bncc\b|phieu nhap"),
    ("profit", r"\blai\b|\bloi\b|gia von|\bvon\b|chi phi"),
    ("delivery", r"dot giao|chuyen giao|cho giao|giao hang"),
    ("price_on_day", r"gia ban .* (?:vao )?ngay|gia ban mot"),
    ("cancel", r"\bhuy\b|doi y"),
    ("share_pct", r"ti trong|ty trong|chiem bao nhieu|chiem may|bao nhieu phan tram (?:tong )?doanh thu|% (?:tong )?doanh thu|phan cua"),
    ("growth_pct", r"(?:tang|giam|thay doi|hon hay kem|chenh).*(?:%|phan tram)|(?:%|phan tram).*(?:so voi|so vs|cung ky)"),
    ("diff", r"chenh lech|hon hay kem|hon kem|tang hay giam|tang bao nhieu|giam bao nhieu"),
    ("argmax_period", r"ngay nao|thang nao|hom nao|tuan nao|gio nao|khung gio|gio cao diem|ngay dat khach"),
    ("top_employee", r"nhan vien|\btho\b"),
    ("top_customer", r"khach (?:nao|mua nhieu|chi tieu|hang nao)|ai la khach|top \d+ khach|\d+ khach (?:mua|chi)|khach .*nhat|khach sop|trung thanh"),
    ("count_threshold", r"(?:it nhat|tu \d+ .*tro len|tren \d+|hon \d+|qua \d+|duoi \d+|>=|≥|≤|>|<) ?\d*.*(?:don|lan)|co mat (?:trong|o)"),
    ("customer_count", r"bao nhieu khach|may khach|so khach|khach moi|thanh vien moi"),
    ("top_product", r"ban chay|chay nhat|ban nhieu nhat|hot nhat|ua chuong|ban cham|khong ban duoc|\be\b|mat hang nao|hang nao|mon nao|san pham nao|top \d+"),
    ("avg_order", r"trung binh|binh quan"),
    ("quantity", r"bao nhieu (?:ly|chai|lon|goi|hop|thung|kg|cay|bao|vien|vi|bich|cai|phan|may|ca|tuyp|lo|chiec|xe|luot|phieu)|may (?:ly|chai|lon|goi|hop|thung|kg|cay|bao|vien|bich|cai|phan|may|xe|luot|phieu)|so (?:ly|chai|lon|goi|hop|thung|kg|vien|bich|luot|phieu)|so luong"),
    ("order_count", r"\bdon\b|hoa don|\bbill\b"),
    ("revenue", r"doanh thu|tien|ban duoc|thu ve|ban ra"),
]

PERIODS = [
    ("thang M/YYYY", r"thang\s*0?\d{1,2}\s*[/\-]\s*\d{4}|thang\s*\d{1,2} nam \d{4}|\b\d{1,2}[/\-]\d{4}\b"),
    ("ngay D/M/YYYY", r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
    ("quy Q/YYYY", r"quy\s*\d\s*(?:/|nam)\s*\d{4}"),
    ("quy Q (không năm)", r"quy\s*\d(?!\s*(?:/|nam)\s*\d)"),
    ("thang M (không năm)", r"thang\s*\d{1,2}(?!\d)(?!\s*(?:/|nam|-)\s*\d)"),
    ("nam YYYY", r"nam \d{4}"),
    ("hom nay", r"hom nay|toi nay|sang nay"),
    ("hom qua", r"hom qua"),
    ("tuan nay", r"tuan nay"),
    ("tuan truoc", r"tuan truoc|tuan roi"),
    ("thang nay", r"thang nay"),
    ("thang truoc", r"thang truoc|thang roi"),
    ("N ngay gan nhat", r"\d+ ngay gan (?:nhat|day)|\d+ ngay qua"),
    ("N thang gan nhat / lien nhau", r"\d+ thang (?:gan nhat|lien|qua)"),
    ("tu dau nam", r"tu dau nam|dau nam (?:toi|den) nay"),
    ("tu X den Y", r"\btu\b.*\bden\b|\btu\b.*\bqua\b.*thang"),
    ("den het ngay X (tình trạng)", r"den het ngay|tinh den|den cuoi ngay|den nay"),
    ("cung ky", r"cung ky"),
    ("so voi thang/ky truoc", r"so voi (?:thang|ky|tuan) truoc|so (?:voi )?th(?:ang)? truoc|hon hay kem .* truoc"),
    ("N ngay ke tu D (tăng giá)", r"\d+ ngay ke tu|\d+ ngay (?:ngay )?truoc"),
    ("tet", r"\btet\b"),
    ("ca sang / ca chieu", r"ca sang|ca chieu"),
    ("ngay thu X trong tuan", r"(?<!doanh )\bthu (?:hai|ba|tu|nam|sau|bay|[2-7])\b(?! \d)|chu nhat"),
    ("N ngay toi (hạn dùng)", r"\d+ ngay toi"),
]


def main():
    qs = [json.loads(l) for l in open(f"{ROOT}/train/questions.jsonl", encoding="utf-8")]
    ans = {json.loads(l)["id"]: json.loads(l) for l in open(f"{ROOT}/train/answers.jsonl", encoding="utf-8")}
    intent_of, cnt, types, ex = {}, collections.Counter(), collections.defaultdict(collections.Counter), collections.defaultdict(list)
    for q in qs:
        t = norm(q["question"])
        name = next((n for n, p in INTENTS if re.search(p, t)), "other")
        intent_of[q["id"]] = name
        cnt[name] += 1
        types[name][ans[q["id"]]["type"]] += 1
        ex[name].append(q["question"])
    print("== INTENTS")
    for name, n in cnt.most_common():
        print(f"{name:16s} {n:5d}  {dict(types[name].most_common())}")
        for e in ex[name][:SHOW]:
            print("     ·", e)
    pc, pex = collections.Counter(), collections.defaultdict(list)
    none = []
    for q in qs:
        t = norm(q["question"])
        hit = [n for n, p in PERIODS if re.search(p, t)]
        for h in hit:
            pc[h] += 1
            pex[h].append(q["question"])
        if not hit:
            none.append(q["question"])
    print("\n== PERIODS (a question can have several)")
    for name, n in pc.most_common():
        print(f"{name:32s} {n:5d}   e.g. {pex[name][0][:90]}")
    print(f"no period found: {len(none)}")
    for e in none[:SHOW * 4]:
        print("     ·", e)
    json.dump(intent_of, open(sys.argv[3], "w", encoding="utf-8")) if len(sys.argv) > 3 else None


main()
