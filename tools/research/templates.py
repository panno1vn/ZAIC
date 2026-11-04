"""T1: group the 3000 train questions into templates, attach a plan shape and the metric function status to each.

    python tools/research/templates.py                       # hand plans only
    python tools/research/templates.py --llm-url http://127.0.0.1:8091   # + LLM plans for clusters without one

Steps (docs/KE_HOACH_DataMate.md §10, T1):
1. template text of each question (datamate/nlu/templates.py): folded, telex undone, numbers masked, filler dropped;
2. names masked with the names found in the question's own business (column roles guessed from header names, the
   same rule for all 30 businesses);
3. leader clustering: a question joins the most similar representative if the score reaches --threshold, else it
   becomes a new representative;
4. plan shape of each cluster from the hand-written plans (assets/plans) or the LLM plan of its representative; a
   cluster whose known plans disagree is split by plan shape;
5. status of the metric function: registered in datamate/metrics, missing (sales, T3), or v2 (debt, stock, …).

Writes assets/plans/templates_train.json (cluster -> question ids) and the generated part of
docs/research/templates.md. Train only: test questions are never read.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT =Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from rapidfuzz import fuzz, process  # noqa: E402

from datamate.contracts import DataCard, QueryPlan  # noqa: E402
from datamate.loader import load_business  # noqa: E402
from datamate.metrics import lookup, metric_entity, metric_name, plan_filter_fields  # noqa: E402
from datamate.nlu import baseline, prompt  # noqa: E402
from datamate.nlu.templates import NameIndex, fold, plan_shape, template_text  # noqa: E402

TRAIN = ROOT / "data" / "train"
CACHE = ROOT / "outputs" / "templates"
DOC = ROOT / "docs" / "research" / "templates.md"
OUT = ROOT / "assets" / "plans" / "templates_train.json"

# column role from the folded header name, first match wins; code columns (SP0001, KH0040) are skipped by value
ROLES = [
    ("skip", r"\bma\b|^ma[a-z]+$|\bid\b|\bdia ?chi|so luong|don vi|\bdv|trang thai|status|ngay|thoi gian|dia chi|addr|ghi chu|ly do"
             r"|nguyen nhan|chuc vu|phuong thuc|pttt|httt|tra bang|kenh|ban qua|nguon don|loai ban|khu vuc|phong"),
    ("nhom", r"nhom hang|loai ?(?:san pham|hang)|danh ?muc|phan loai"),
    ("nhomkh", r"nhom khach|loai ?khach|^nhom$"),
    ("hc", r"hoat chat|thanh ?phan"),
    ("ncc", r"cung cap"),
    ("nv", r"nhan ?vien|nguoi (?:cho|ban|giao)|\btho\b"),
    ("kh", r"khach|^kh$|ten ?kh|doi tac|ben mua"),
    ("sp", r"ten ?(?:hang|sp|san pham|mat hang|mon)|san pham|hang hoa|mat hang|hang ban|chi tiet hang|product"
           r"|noi dung|^mon$|^hang$|^ten_hang$"),
]
# a generic "name" column (biz_123 "TenGoi" in every table) takes its role from the table name
GENERIC = re.compile(r"^ten ?(?:goi)?$")
TABLE_ROLES = [("nv", r"nhan ?vien"), ("kh", r"khach"), ("ncc", r"cung ?cap"), ("sp", r"san ?pham|hang ?hoa|thuoc")]
_CODE = re.compile(r"^[A-Z]{1,4}\d{2,}$")
# walk-in customer spellings and product types ("Hàng hóa" / "Dịch vụ" in a "loại hàng" column): not names
NOT_NAMES = {"khach le", "le", "kl", "khach vang lai", "vang lai", "hang hoa", "dich vu"}

SALES = {"revenue", "order_count", "cancel_count", "cancel_rate", "avg_order_value", "quantity", "customer_count",
         "new_customer_count", "days_with_purchase", "order_presence", "work_days"}


def column_role(header: str, table: str = "") -> str | None:
    h = fold(header).replace("_", " ").strip()
    if GENERIC.match(h):
        t = fold(table).replace("_", " ")
        return next((role for role, pat in TABLE_ROLES if re.search(pat, t)), None)
    for role, pat in ROLES:
        if re.search(pat, h):
            return None if role == "skip" else role
    return None


def business_names(folder: Path) -> list[tuple[str, str]]:
    """(role, name) of every distinct text value of a name column in the business's files."""
    raw = load_business(folder)
    names = set()
    for t in raw.tables:
        for col in t.frame.columns:
            role = column_role(str(col), t.sheet or t.table_id)
            if role is None:
                continue
            values = {str(v).strip() for v in t.frame[col].dropna() if str(v).strip()}
            if not values or sum(bool(_CODE.match(v)) for v in values) > len(values) / 2:
                continue
            for v in values:
                v = re.split(r"\s+-\s+0\d|\s*\(0\d", v)[0]  # "Tên - 0328 548 455", "Tên (0913885954)"
                if fold(v).strip() not in NOT_NAMES and re.search(r"[^\W\d_]", v):
                    names.add((role, v))
    return sorted(names)


def all_names(refresh: bool) -> dict[str, list[tuple[str, str]]]:
    path = CACHE / "names.json"
    if path.exists() and not refresh:
        return {k: [tuple(x) for x in v] for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
    out = {d.name: business_names(d) for d in sorted((TRAIN / "data").iterdir()) if d.is_dir()}
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def leader_clusters(texts: list[str], threshold: float) -> tuple[list[int], list[str]]:
    """Cluster of each text and the representative texts. Distinct texts are taken most frequent first; each joins the
    closest representative scoring ≥ threshold, else becomes one."""
    freq = Counter(texts)
    reps: list[str] = []
    of: dict[str, int] = {}
    for t in sorted(freq, key=lambda t: (-freq[t], t)):
        hit = process.extractOne(t, reps, scorer=fuzz.token_sort_ratio, score_cutoff=threshold) if reps else None
        if hit is None:
            of[t] = len(reps)
            reps.append(t)
        else:
            of[t] = hit[2]
    return [of[t] for t in texts], reps


def hand_plans() -> dict[str, QueryPlan]:
    plans = {}
    for f in prompt.HAND_FILES:  # not the verified bank (T4): hand plans only
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                plans[e["id"]] = QueryPlan.model_validate(e["plan"])
    return plans


def llm_plans(questions: list[dict], url: str | None) -> dict[str, QueryPlan | None]:
    """LLM plans cached in outputs/templates/llm_plans.jsonl; with a url, the missing ones are asked for."""
    path = CACHE / "llm_plans.jsonl"
    cache: dict[str, QueryPlan | None] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            cache[e["id"]] = QueryPlan.model_validate(e["plan"]) if e["plan"] else None
    todo = [q for q in questions if q["id"] not in cache]
    if not todo or url is None:
        return cache
    from datamate.llm import LlamaServerLLM
    from datamate.nlu import llm_plan
    llm = LlamaServerLLM(url, timeout_s=60.0)
    if not llm.healthy():
        sys.exit(f"không gọi được {url}/health")
    CACHE.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for n, q in enumerate(todo, 1):
            plan = llm_plan(q["question"], date.fromisoformat(q["as_of_date"]), DataCard(), llm)
            cache[q["id"]] = plan
            f.write(json.dumps({"id": q["id"], "plan": plan.model_dump(mode="json", exclude_none=True) if plan else None},
                               ensure_ascii=False) + "\n")
            f.flush()
            if n % 50 == 0:
                print(f"  LLM {n}/{len(todo)}", flush=True)
    return cache


def function_status(plan: QueryPlan) -> str:
    """"có" when datamate/metrics registers a function for the plan's intent, metric and entity that takes all its
    filters (a registered function may still decline a variant, e.g. several measures); else "T3" for sales metrics,
    "v2" for the rest (debt, purchase, stock, profit, price, industry rules)."""
    if plan.intent == "out_of_scope":
        return "ngoài phạm vi"
    resolved = SimpleNamespace(plan=plan)
    name = metric_name(resolved)
    spec = lookup(plan.intent, name, metric_entity(resolved)) if name else None
    if spec is not None and plan_filter_fields(resolved) <= set(spec.filters) and len(plan.measures) <= 1:
        return "có"
    metrics = {m.metric for m in plan.measures} | ({plan.rank.by} if plan.rank else set()) \
        | ({plan.threshold.metric} if plan.threshold else set())
    if plan.list_spec and plan.list_spec.condition not in ("unsold_in_period", "sold_in_period"):
        return "v2"
    return "T3" if metrics <= SALES else "v2"


def split_by(members: list[int], label: dict[int, str], texts: list[str]) -> list[list[int]]:
    """Members split by label; a member without one follows its closest labelled member (whole group if none)."""
    if len(set(label.values())) <= 1:
        return [members]
    parts: dict[str, list[int]] = defaultdict(list)
    for i in members:
        j = i if i in label else max(label, key=lambda j: (fuzz.token_sort_ratio(texts[i], texts[j]), -j))
        parts[label[j]].append(i)
    return list(parts.values())


def text_clusters(questions: list[dict], names: dict, hand: dict[str, QueryPlan], answer_type: dict[str, str],
                  threshold: float) -> tuple[list[dict], list[str]]:
    """Clusters, largest first: members (indices), representative, and the members with a hand plan. A text cluster is
    split when its train answers differ in type (list vs string: "5 khách…" vs "khách nào…" differ only by a masked
    number; unanswerable is a fact of the data, not of the template, so it does not split) and then when its hand plans
    differ in shape (period kind aside)."""
    index = {b: NameIndex(ns) for b, ns in names.items()}
    texts = [template_text(q["question"], index.get(q["business_id"])) for q in questions]
    of, reps = leader_clusters(texts, threshold)
    groups: dict[int, list[int]] = defaultdict(list)
    for i, c in enumerate(of):
        groups[c].append(i)

    clusters = []
    for c, members in groups.items():
        types = {i: answer_type[questions[i]["id"]] for i in members
                 if answer_type.get(questions[i]["id"], "unanswerable") != "unanswerable"}
        parts = []
        for ms in split_by(members, types, texts):
            shapes = {i: plan_shape(hand[questions[i]["id"]], period=False) for i in ms if questions[i]["id"] in hand}
            parts += [(p, [i for i in p if i in shapes]) for p in split_by(ms, shapes, texts)]
        for ms, planned in parts:
            rep = next((i for i in ms if texts[i] == reps[c]), ms[0])
            clusters.append({"members": ms, "rep": rep, "text": texts[rep], "split": len(parts) > 1, "hand": planned})
    clusters.sort(key=lambda k: (-len(k["members"]), k["text"]))
    return clusters, texts


def llm_targets(clusters: list[dict], texts: list[str], per_cluster: int) -> list[int]:
    """Questions to ask the LLM for, in clusters without a hand plan: the representative, then the members least like
    it (where a mixed cluster would show)."""
    out = []
    for k in clusters:
        if k["hand"]:
            continue
        rest = sorted((i for i in k["members"] if i != k["rep"]),
                      key=lambda i: (fuzz.token_sort_ratio(texts[i], texts[k["rep"]]), i))
        out += [k["rep"]] + rest[:per_cluster - 1]
    return out


def attach_plans(clusters: list[dict], questions: list[dict], hand: dict[str, QueryPlan],
                 llm: dict[str, QueryPlan | None]) -> None:
    """Plan of each cluster: its first hand plan, else the LLM plan of its representative (else of another member),
    else the rule-based baseline's plan of a member. `llm_agree` is False when two LLM plans of the cluster differ in
    shape (period kind aside)."""
    for k in clusters:
        k["llm_agree"] = None
        if k["hand"]:
            k["plan"], k["source"] = hand[questions[k["hand"][0]]["id"]], "tay"
            continue
        order = list(dict.fromkeys([k["rep"]] + k["members"]))
        got = [(i, llm[questions[i]["id"]]) for i in order if llm.get(questions[i]["id"])]
        if got:
            k["plan"], k["source"] = got[0][1], "LLM"
            k["llm_agree"] = None if len(got) < 2 else len({plan_shape(p, period=False) for _, p in got}) == 1
            continue
        base = next((p for p in (baseline.parse(questions[i]["question"]) for i in order) if p is not None), None)
        k["plan"], k["source"] = (base, "baseline") if base else (None, "-")


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def report(clusters: list[dict], questions: list[dict], texts: list[str], threshold: float, top: int
           ) -> tuple[str, dict]:
    """Markdown of the generated part of docs/research/templates.md, and the JSON of assets/plans/templates_train.json."""
    n = len(questions)
    for no, k in enumerate(clusters, 1):
        k["id"] = f"T{no:03d}"
        k["shape"] = plan_shape(k["plan"], period=False) if k["plan"] else None
        k["status"] = function_status(k["plan"]) if k["plan"] else "chưa rõ"
        k["shops"] = len({questions[i]["business_id"] for i in k["members"]})
    size = lambda ks: sum(len(k["members"]) for k in ks)  # noqa: E731
    in_multi = size([k for k in clusters if len(k["members"]) >= 2])
    by_status = Counter()
    for k in clusters:
        by_status[k["status"]] += len(k["members"])
    llm_checked = [k for k in clusters if k["llm_agree"] is not None]

    md = [f"*Sinh bằng `python tools/research/templates.py` (ngưỡng {threshold:g}, `token_sort_ratio`). "
          "Phần giữa hai dấu mốc AUTO được ghi đè mỗi lần chạy.*", "",
          "| Chỉ số | Giá trị |", "|---|---:|",
          f"| Số câu train | {n} |",
          f"| Dạng câu sau chuẩn hoá (khác nhau từng chữ) | {len(set(texts))} |",
          f"| Số cụm mẫu câu | {len(clusters)} |",
          f"| Câu nằm trong cụm ≥ 2 câu | {in_multi} ({in_multi / n:.1%}) |",
          f"| Câu nằm trong cụm có mặt ở ≥ 2 cửa hàng | {size([k for k in clusters if k['shops'] >= 2]) / n:.1%} |",
          f"| Cụm tách ra vì kiểu đáp án hoặc plan viết tay khác nhau | {sum(k['split'] for k in clusters)} |",
          f"| Câu nằm trong cụm có plan viết tay | {size([k for k in clusters if k['source'] == 'tay']) / n:.1%} |",
          f"| Câu nằm trong cụm có plan LLM (không có plan tay) | {size([k for k in clusters if k['source'] == 'LLM']) / n:.1%} |",
          f"| Câu nằm trong cụm chỉ có plan baseline | {size([k for k in clusters if k['source'] == 'baseline']) / n:.1%} |",
          f"| Cụm có 2 plan LLM khác dạng | {sum(not k['llm_agree'] for k in llm_checked)} / {len(llm_checked)} |",
          "", "**Trạng thái hàm tính** (số câu train nằm trong cụm có trạng thái đó):", "",
          "| Trạng thái | Câu | Tỉ lệ |", "|---|---:|---:|"]
    labels = {"có": "đã có hàm trong `datamate/metrics`", "T3": "chưa có, nhóm bán hàng (T3)",
              "v2": "chưa có, nhóm v2 (công nợ, nhập, kho, lãi, giá, theo ngành)", "ngoài phạm vi": "ngoài phạm vi",
              "chưa rõ": "chưa rõ (cụm chưa có plan)"}
    for st in ("có", "T3", "v2", "ngoài phạm vi", "chưa rõ"):
        if by_status[st]:
            md.append(f"| {labels[st]} | {by_status[st]} | {by_status[st] / n:.1%} |")

    families: dict[str, list[dict]] = defaultdict(list)
    for k in clusters:
        families[k["shape"] or "(chưa có plan)"].append(k)
    fam = sorted(families.items(), key=lambda kv: (-size(kv[1]), kv[0]))
    md += ["", f"### Dạng plan (bỏ kiểu kỳ), xếp theo số câu: danh sách việc của T3 / v2", "",
           "| # | Dạng plan | Câu | Cụm | Cửa hàng | Trạng thái | Cộng dồn |", "|---:|---|---:|---:|---:|---|---:|"]
    acc = 0
    for no, (shape, ks) in enumerate(fam, 1):
        acc += size(ks)
        shops = len({questions[i]["business_id"] for k in ks for i in k["members"]})
        md.append(f"| {no} | `{_cell(shape)}` | {size(ks)} | {len(ks)} | {shops} | {ks[0]['status']} | {acc / n:.1%} |")

    md += ["", f"### {top} cụm lớn nhất", "",
           "| Cụm | Câu | Cửa hàng | Câu đại diện | Dạng plan | Nguồn plan | Hàm |", "|---|---:|---:|---|---|---|---|"]
    for k in clusters[:top]:
        q = questions[k["rep"]]["question"]
        md.append(f"| {k['id']} | {len(k['members'])} | {k['shops']} | {_cell(q)} | `{_cell(k['shape'] or '-')}` "
                  f"| {k['source']} | {k['status']} |")

    data = {"method": {"threshold": threshold, "scorer": "rapidfuzz.fuzz.token_sort_ratio",
                       "text": "datamate.nlu.templates.template_text", "shape": "datamate.nlu.templates.plan_shape(period=False)"},
            "clusters": [{"id": k["id"], "size": len(k["members"]), "shops": k["shops"], "text": k["text"],
                          "rep_id": questions[k["rep"]]["id"], "shape": k["shape"], "plan_source": k["source"],
                          "status": k["status"], "split": k["split"], "llm_agree": k["llm_agree"],
                          "ids": [questions[i]["id"] for i in k["members"]]} for k in clusters]}
    return "\n".join(md), data


BEGIN, END = "<!-- BEGIN AUTO -->", "<!-- END AUTO -->"


def write_doc(md: str) -> None:
    old = DOC.read_text(encoding="utf-8") if DOC.exists() else f"# Mẫu câu hỏi của train (T1)\n\n{BEGIN}\n{END}\n"
    head, _, rest = old.partition(BEGIN)
    _, _, tail = rest.partition(END)
    DOC.write_text(f"{head}{BEGIN}\n{md}\n{END}{tail}", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threshold", type=float, default=90.0)
    ap.add_argument("--llm-url", help="llama-server: hỏi plan cho cụm chưa có plan viết tay (kết quả lưu cache)")
    ap.add_argument("--llm-per-cluster", type=int, default=2, help="số câu mỗi cụm hỏi LLM (câu đại diện + câu xa nhất)")
    ap.add_argument("--refresh-names", action="store_true", help="đọc lại tên từ dữ liệu thay vì dùng cache")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--dry-run", action="store_true", help="chỉ in, không ghi assets/ và docs/")
    args = ap.parse_args(argv)

    questions = [json.loads(line) for line in (TRAIN / "questions.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    answer_type = {a["id"]: a["type"] for a in map(json.loads, (TRAIN / "answers.jsonl").read_text(
        encoding="utf-8").splitlines()) if a}
    names, hand = all_names(args.refresh_names), hand_plans()
    clusters, texts = text_clusters(questions, names, hand, answer_type, args.threshold)
    targets = [questions[i] for i in llm_targets(clusters, texts, args.llm_per_cluster)]
    llm = llm_plans(targets, args.llm_url)
    attach_plans(clusters, questions, hand, llm)
    md, data = report(clusters, questions, texts, args.threshold, args.top)
    print(md.split("### ")[0])
    if not args.dry_run:
        rows = ",\n".join(json.dumps(k, ensure_ascii=False) for k in data["clusters"])  # one cluster per line
        OUT.write_text(f'{{"method": {json.dumps(data["method"], ensure_ascii=False)},\n"clusters": [\n{rows}\n]}}\n',
                       encoding="utf-8")
        write_doc(md)
        print(f"Đã ghi {OUT.relative_to(ROOT)} và {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
