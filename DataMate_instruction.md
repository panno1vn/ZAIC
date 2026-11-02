# Business Data Question Answering: Task Instructions

Build an agent that answers natural-language questions (Vietnamese, often informal and without diacritics) about the data of small Vietnamese businesses, and submits answers in a typed JSON Lines format.

---

## 1. Business Types

The data covers a wide range of Vietnamese small businesses:

- grocery stores
- coffee and bubble-tea shops
- restaurants
- pharmacies
- building-material stores
- motorbike repair shops
- mother-and-baby stores
- and more

> **The private test includes business types that do not appear in the training or public test data.**

Each business covers **12-30 months** of activity with seasonality (Tết, Mid-Autumn, public holidays, paydays, weekends) and ranges from **a few hundred to about 300,000 rows**.

---

## 2. Package Structure

```
<split>/
├── data/<business_id>/
│   ├── *.csv | *.xlsx | *.sqlite        # one or more data files
│   └── README.md                        # business description and notes
├── rulebook.md                          # default rules and vocabulary
├── calendar.csv                         # solar-lunar calendar (Tết)
├── questions.jsonl                      # one question per line
└── answers.jsonl                        # training only
```

### Files

| File | Description |
|---|---|
| `data/<business_id>/*.csv\|xlsx\|sqlite` | One or more data files per business |
| `data/<business_id>/README.md` | Business description and notes. **Quality varies**: some have a full data dictionary, others a few informal notes, some almost nothing |
| `rulebook.md` | Default rules and vocabulary for the split |
| `calendar.csv` | Solar-lunar calendar (used for Tết) |
| `questions.jsonl` | One question per line |
| `answers.jsonl` | Reference answers, training only |

### Sample record in `questions.jsonl`

```json
{"id": "q_01234", "business_id": "biz_017", "question": "thang nay hang nao ban cham nhat, ton nhieu ma ban ko dc", "as_of_date": "2026-08-27"}
```

### `answers.jsonl` (training only)

Training businesses come with `answers.jsonl`, containing the reference answer for every training question, linked by `id`.

- Each line follows the submission format, **plus an `alias` field** listing other accepted forms of a name answer (alternative spellings found in the data, and the item code).
- Unanswerable questions have `"answer": null`.
- Submissions do **not** need to include the `alias` field.

Sample record (the reference answer of the example question above):

```json
{"id": "q_06de33fa21cc", "type": "string", "answer": "Xi măng Hà Tiên PCB40 bao 50kg", "alias": ["SP0001"]}
```

---

## 3. Splits

*(The source text has a "Splits" heading with no content, so nothing is specified here. Check the competition page or the data package README.)*

---

## 4. Business Rules (Default Interpretations)

Each split ships its own `rulebook.md`, which fixes the default meaning of common terms whenever the question does not say otherwise.

> **The rulebook may differ between splits.** Your agent must read and apply the rulebook of the split it is answering, not a copy of the training rulebook.

Typical rules:

| Term | Default meaning |
|---|---|
| Revenue | Sum of line amounts **after line-level discounts** (order-level vouchers are **not** deducted), excluding VAT and delivery fees, excluding cancelled orders and orders with any returned item |
| "bán chạy" (best-selling) | Ranked by **quantity** |
| Week | Monday to Sunday |
| "tháng này" (this month) | The month containing the as-of date, **up to and including** that date |
| Default cost | Weighted-average purchase cost by lot |
| Tết window | 23 tháng Chạp to mùng 10 (lunar calendar) |

---

## 5. Submission Format

In both rounds you upload a `submission.jsonl` file, one JSON object per line.

| `type` | `answer` | Example |
|---|---|---|
| `string` | text | `{"id": "q_01234", "type": "string", "answer": "Sting dâu 330ml"}` |
| `number` | number | `{"id": "q_01235", "type": "number", "answer": 48250000}` |
| `percent` | number (percent value) | `{"id": "q_01236", "type": "percent", "answer": -12.45}` |
| `date` | ISO date string | `{"id": "q_01237", "type": "date", "answer": "2026-08-15"}` |
| `boolean` | true / false | `{"id": "q_01238", "type": "boolean", "answer": true}` |
| `list` | array | `{"id": "q_01239", "type": "list", "answer": ["Cà phê sữa", "Bạc xỉu", "Trà đào"]}` |
| `table` | `{columns, rows}` | `{"id": "q_01240", "type": "table", "answer": {"columns": ["khach_hang", "so_tien_no"], "rows": [["Chị Lan", 3200000], ["Anh Tú", 1500000]]}}` |
| `unanswerable` | none (optional `reason`) | `{"id": "q_01241", "type": "unanswerable", "reason": "Dữ liệu không có giá vốn nên không tính được lợi nhuận"}` |
| `abstain` | none | `{"id": "q_01242", "type": "abstain"}` |

Full example file:

```jsonl
{"id": "q_01234", "type": "string",  "answer": "Sting dâu 330ml"}
{"id": "q_01235", "type": "number",  "answer": 48250000}
{"id": "q_01236", "type": "percent", "answer": -12.45}
{"id": "q_01237", "type": "date",    "answer": "2026-08-15"}
{"id": "q_01238", "type": "boolean", "answer": true}
{"id": "q_01239", "type": "list",    "answer": ["Cà phê sữa", "Bạc xỉu", "Trà đào"]}
{"id": "q_01240", "type": "table",   "answer": {"columns": ["khach_hang", "so_tien_no"], "rows": [["Chị Lan", 3200000], ["Anh Tú", 1500000]]}}
{"id": "q_01241", "type": "unanswerable", "reason": "Dữ liệu không có giá vốn nên không tính được lợi nhuận"}
{"id": "q_01242", "type": "abstain"}
```

Notes:

- **Questions missing from the file are scored as `abstain`.**
- The `reason` field is optional.
- The number of submissions per day follows the general regulations.

---

## 6. Docker Image

The image (see *Competition rounds* in the Rule section) must contain:

- the **source code** (training and inference)
- the **model weights**
- a **`predict.sh`** that reads the test set from `/data` and writes `/result/submission.jsonl`
- a **README**

It should also write a **per-question log** to `/result/logs/`, in any format, containing at least:

- the question `id`
- the final answer
- the elapsed time
- plus anything else that shows how the answer was reached (e.g. generated code, execution output)

The organizers use these logs to resolve differences between your uploaded result and their re-run (Rule 8).

---

## 7. Quick Checklist

- [ ] Read the split's own `rulebook.md` and apply it; do not reuse the training rulebook.
- [ ] Read each business's `README.md`, but do not rely on it being complete.
- [ ] Use `calendar.csv` for Tết and other lunar-date windows.
- [ ] Interpret "this month", "this week" and similar terms relative to `as_of_date`.
- [ ] Handle informal Vietnamese, including missing diacritics and abbreviations.
- [ ] Support all answer types (`string`, `number`, `percent`, `date`, `boolean`, `list`, `table`).
- [ ] Return `unanswerable` when the data cannot support the question, and `abstain` when unsure.
- [ ] Make the solution generalize to **unseen business types** in the private test.
- [ ] Docker: provide `predict.sh` (reads `/data`, writes `/result/submission.jsonl`), a README, and logs in `/result/logs/`.
