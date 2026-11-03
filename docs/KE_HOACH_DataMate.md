# Kế hoạch DataMate — dựng xương sống trước, chia vai sau

*Cập nhật: 02/11/2026 · Kiến trúc tham chiếu: [architecture/DataMate_kien_truc_v2.png](architecture/DataMate_kien_truc_v2.png) (bản sửa được: [.drawio](architecture/DataMate_kien_truc_v2.drawio))*

## 0. Ràng buộc chính

| Mục | Nội dung |
|---|---|
| Hạn đóng băng | **T2 16/11/2026, 23:59** — nộp Docker qua link Google Drive + checksum, tối đa 2 lần, BTC chỉ chấm lần cuối |
| Private test | Phát 9:00 T6 20/11, nộp kết quả trước 23:59 T2 23/11. Điểm cuối = BTC chạy lại Docker, lệch ≤ 0,03 PA |
| Chấm điểm | Đúng +1, sai −1, bỏ trống 0. Khớp tuyệt đối. Trả lời câu unanswerable = sai |
| Model | Tổng mọi model ≤ 15 tỉ tham số, weights công bố trước 01/10/2026, giấy phép Apache/MIT |
| Lúc chạy | Offline, `/data` chỉ đọc, không logic theo id cửa hàng/câu hỏi, không train trên dữ liệu test |
| Máy chấm | 2× RTX 5090 (32GB), RAM 512GB, ≤ 6 giờ cho cả private test kể cả load model |

Cách làm: **4 ngày đầu (02/11–05/11) leader tự dựng xương sống**, các thành viên làm việc không phụ thuộc vai trò. **Tối T5 05/11 chia vai**, giao từng gói việc đến hạn đóng băng.

## 1. Xương sống là gì

Xương sống là phần **nối các khối với nhau**:
- **Hợp đồng dữ liệu**: input/output của từng khối.
- **Pipeline** chạy từ đầu đến cuối.
- **Scorer** chấm điểm và công cụ đánh giá.
- **Ghi file nộp và log.**
- **Một bản giữ chỗ (stub) cho mỗi khối**: nhận đúng input, trả đúng output theo hợp đồng, chưa làm gì thật, mặc định bỏ trống câu hỏi.

Nhờ vậy, **ngay từ ngày đầu pipeline đã chạy hết dữ liệu và ra file nộp hợp lệ**. Sau đó mỗi thành viên chỉ thay stub của khối mình bằng code thật, không đụng vào phần người khác.

Nguyên tắc:
1. Stub luôn an toàn: không chắc thì bỏ trống. Pipeline chưa xong vẫn không bao giờ bị điểm âm.
2. Một câu hỏi lỗi thì chỉ câu đó bỏ trống, cả pipeline không dừng.
3. Sau T5 05/11, hợp đồng bị khóa; muốn đổi phải qua leader.
4. Khối nào cũng có test và ví dụ input/output đi kèm.

## 2. Cấu trúc repo

```
datamate/
├── configs/default.json   # đường dẫn, ngân sách thời gian, ngưỡng, tên model
├── datamate/
│   ├── contracts/   # hợp đồng (Pydantic) + xuất JSON schema       ← leader
│   ├── loader/      # [A] [A2]
│   ├── mapping/     # [B]
│   ├── nlu/         # [C] [C3]
│   ├── temporal/    # [C2]
│   ├── metrics/     # [D1] registry + các hàm tính
│   ├── codegen/     # [D2]
│   ├── rules/       # [R] đọc rulebook, so sánh luật               ← leader
│   ├── verify/      # [V]                                          ← leader
│   ├── decide/      # [E]                                          ← leader
│   ├── formatter/   # [F]
│   ├── llm/         # client chung: bản giả lập + bản chạy model thật ← leader (khung)
│   ├── output/      # ghi submission, log, đồng hồ chặn            ← leader
│   ├── pipeline.py  # nối mọi khối                                 ← leader
│   └── predict.py   # lệnh chạy chính
├── eval/            # scorer, chạy đánh giá, bảng cửa hàng → ngành  ← leader
├── assets/          # thứ sinh từ train: ví dụ mẫu, từ điển, ngưỡng
├── tests/  notebooks/  docs/  docker/ (để trống, chờ guideline)
```

## 3. Hợp đồng cần viết (phác thảo)

```python
class QueryPlan(BaseModel):        # [C] → [C2] → [C3] → [D]
    intent: Literal["metric", "growth", "diff", "share", "top_k", "argmax_period", "trend", ...]
    measures: list[Measure]        # chỉ số + bộ lọc, giữ đúng thứ tự câu hỏi nêu
    period: PeriodExpr             # dạng ký hiệu: month 2026-02, this_month, last_n_days 7…
    compare: PeriodExpr | None
    rank: RankSpec | None          # đối tượng, tiêu chí, k
    answer_type: AnswerType

class ResolvedPlan(QueryPlan): start: date; end: date; ...   # sau [C2]
class ExecResult(BaseModel): value: Any; used_fields: list[str]; source: Literal["D1", "D2"]; notes: list[str]
class Signals(BaseModel): intent_known: bool; entities_ok: bool; mapping_ok: bool; period_in_data: bool; sane: bool; rules_unchanged: bool; agree: bool | None
class Decision(BaseModel): kind: Literal["answer", "unanswerable", "abstain"]; confidence: float; reason: str
```

Thêm:
- **Schema chuẩn**: các bảng `orders`, `lines`, `products`, `payments`, `returns`, `purchases`, `inventory`, `price_history`, `lots`, `expenses` với tên cột và kiểu dữ liệu cố định; trạng thái đơn ∈ {hoàn thành, huỷ, trả hàng, đang giao}.
- **Mapping JSON**: cột thô nào ứng với cột chuẩn nào.
- **Mô tả bảng (TableProfile).**
- **20 kế hoạch truy vấn mẫu cho câu train**: dùng làm test và ví dụ mẫu đầu tiên cho LLM.

## 4. Lịch dựng xương sống của leader (T2 02/11 → T5 05/11)

| Ngày | Việc | Xong khi |
|---|---|---|
| **T2 02/11** | Tạo repo private, môi trường, `.gitignore` cho dữ liệu, CONTRIBUTING (quy trình git, checklist review gồm "không có logic theo id"). Viết **scorer** theo §9 và lệnh chạy đánh giá. Lập bảng cửa hàng train → ngành (đọc README) | Chấm đáp án train với chính nó được 3000/3000. Báo cáo điểm theo kiểu đáp án, cửa hàng, ngành |
| **T3 03/11** | **Hợp đồng:** schema chuẩn, kế hoạch truy vấn, mapping, kết quả, tín hiệu, quyết định. Xuất JSON schema. 20 kế hoạch mẫu. Stub cho mọi khối | Kiểm tra kiểu dữ liệu qua hết; 20 kế hoạch mẫu hợp lệ theo schema |
| **T4 04/11** | **Pipeline:** chạy từng cửa hàng (có cache) rồi từng câu. Ghi submission từng dòng, cuối cùng điền abstain cho câu còn thiếu. Log mỗi câu một file. Đồng hồ chặn. Client LLM có bản giả lập. Registry hàm tính, mỗi hàm gắn dòng luật nó dựa vào. [R] đọc rulebook và so sánh luật. [E] bản đầu bằng cổng điều kiện | Lệnh `predict` chạy hết train và public, ra file hợp lệ (toàn abstain, điểm 0). Đặt ngân sách 10 giây thì phần còn lại tự abstain |
| **T5 05/11** | **Bộ khung chạy thật trên biz_101:** đọc csv, mapping viết tay, regex cho 3 loại câu, tính kỳ "tháng M/Y", 3 hàm tính, format number và list. Viết README từng khối kèm phiếu việc. **Tối: họp chia vai** | biz_101 có điểm dương. Mỗi khối có phiếu việc sẵn để giao |

Ngày T5 giúp leader tự tay viết bản đơn giản nhất của mọi khối, nên hiểu toàn bộ kiến trúc trước khi giao việc.

### Các thành viên làm gì trong lúc này (không phụ thuộc vai trò)
- **T2:** cả nhóm đọc rulebook bản public và tài liệu đề; cài Python, git; học pandas ([Kaggle Learn Pandas](https://www.kaggle.com/learn/pandas)).
- **T3–T5:** chia 30 cửa hàng train cho 4 người (mỗi người 7–8 cửa hàng). Với mỗi cửa hàng:
  - Viết data card.
  - Tự tính tay khoảng 10 câu bằng notebook pandas.
  - Ghi luật ngầm phát hiện được vào `docs/rules_notes.md`.

  Câu tính tay khớp đáp án sẽ thành test cho [D1]; data card là bước chuẩn bị cho mapping tay. Ai nhận vai gì sau này cũng dùng được.
- **Người có kinh nghiệm nhất** (nhiều khả năng phụ trách LLM): thuê GPU, chạy thử Qwen3-8B và Qwen3-14B.

**Lưu ý luật thi:** mapping tay, data card, ví dụ mẫu chỉ làm cho **cửa hàng train**, không làm cho cửa hàng public test.

## 5. Các gói việc để chia vai (tối T5 05/11)
*Không còn áp dụng từ 02/11: leader làm một mình, xem mục 9.*

| Gói | Khối | Độ khó | Hợp với | Việc đầu tiên | Thế nào là xong |
|---|---|---|---|---|---|
| G1 | [A] [A2] Đọc + làm sạch, profiling | Vừa | Junior | Hàm parse tiền, ngày, số lượng + test | Đọc được 44 cửa hàng, test đều qua |
| G2 | [B] Mapping tự động | Khó | Senior | Luật đồng nghĩa tên cột + LLM, kiểm tra chéo | Khớp mapping tay của các cửa hàng train |
| G3 | [C] Hiểu câu hỏi, [D2] (nếu kịp) | Khó | Senior | Parse câu hỏi ra JSON theo schema, chọn ví dụ mẫu bằng BM25 | Đúng trên 20 kế hoạch mẫu, rồi trên kho ví dụ đã kiểm chứng |
| G4 | [C2] Tính ngày, [F] Format | Vừa | Junior | Test theo từng dòng §2 và §9 | Mọi test qua |
| G5 | [D1] Thư viện hàm | Vừa | 1–2 junior | Nhóm doanh thu và đếm (v1) | Khớp đáp án train |
| G6 | [C3] Nối thực thể | Vừa | Junior hoặc senior | So khớp RapidFuzz không dấu với data card | Đúng trên các câu có tên hàng, khách |
| G7 | Docker và vận hành | Vừa | Junior của G1, từ T3 10/11 | Chờ guideline | Chạy hết public, không mạng |

Leader giữ: hợp đồng, pipeline, [R], [V], [E], scorer, tích hợp, review.

**Gợi ý chia nếu chưa có ý khác:**
- Senior: G2 và G3.
- Junior A: G1, sau đó G7.
- Junior B: G4, sau đó phụ G5.
- Junior C: G5 và G6.

### Mẫu phiếu việc
```
Việc:     Viết parse_money(s) -> int | None
Ví dụ:    "25k" -> 25000; "30.500đ" -> 30500; "22,000" -> 22000; "-30.500đ" -> -30500
Xong khi: tests/test_parse_money.py qua hết; đã chạy trên 44 cửa hàng và liệt kê các giá trị chưa parse được
Đọc thêm: rulebook §8, README các cửa hàng
```

## 6. Sau khi chia vai (T6 06/11 → T2 16/11)
*Không còn áp dụng từ 02/11: leader làm một mình, xem mục 9.*

| Thời gian | Mục tiêu | Leader làm |
|---|---|---|
| T6 06/11 – T2 09/11 | Thay stub bằng bản v1 của từng khối. **Nộp public lần đầu (có điểm thật) vào T2 09/11** | Merge mỗi ngày, chạy đánh giá trên train, review |
| T3 10/11 – T5 12/11 | Loại câu v2 (công nợ, tồn kho, nhập hàng, lãi…), mapping chắc hơn, sinh code nếu kịp, chọn ngưỡng tin cậy, Docker (chờ guideline) | Phân tích lỗi vào T3 và T5, đánh giá theo từng ngành, nộp public mỗi ngày |
| T6 13/11 | Khóa tính năng, chạy toàn bộ test, chạy 2 lần đo độ lệch | Quyết định bản 1 |
| T7 14/11 | **Nộp Docker lần 1** | README (khai báo model, giấy phép, cách chạy), tài liệu phương pháp |
| CN 15/11 – T2 16/11 | Chỉ sửa an toàn; lần 2 chỉ nộp nếu tốt hơn rõ ràng và đã chạy thử trên RTX 5090 | Chốt bản cuối, upload trước 18:00 |

**Sau đóng băng:**
- 17–19/11: tải lại đúng image đã nộp, kiểm checksum, chạy thử trên RTX 5090; giữ sẵn máy.
- T6 20/11, 9:00: tải private test, chạy ngay, giữ log, nộp kết quả trước 23:59 T2 23/11.

### Nhịp làm việc
- Hằng ngày: mỗi người nhắn 3 dòng: hôm qua làm gì, hôm nay làm gì, đang vướng gì.
- T2: lập kế hoạch tuần (30 phút). T3 và T5: phân tích lỗi (45 phút). Cuối mỗi giai đoạn: demo.
- Leader cập nhật mỗi ngày: PA trên train theo từng ngành, tỉ lệ câu có trả lời, độ chính xác trên câu đã trả lời, điểm public, số test đang qua.

## 7. Checklist "xương sống xong" (tối T5 05/11)
*Kiểm lại ngày 02/11: đạt hết. Train 3000 và public 1000 câu đều ra đủ dòng, file qua `eval.validate`; ngân sách 0,0001 giờ thì toàn bộ 1000 câu tự bỏ trống.*

- [x] `predict` chạy hết bộ train và bộ public, mỗi câu đúng một dòng, file qua bước kiểm tra format.
- [x] Scorer đúng §9, có test; báo cáo điểm theo kiểu đáp án, cửa hàng, ngành.
- [x] Hợp đồng (v1.1 sau K2), JSON schema và 24 kế hoạch mẫu sẵn sàng khóa; **khóa chính thức ở buổi họp chia vai**.
- [x] Log mỗi câu; đồng hồ chặn đã test; một câu lỗi không làm dừng pipeline.
- [x] Client LLM có bản giả lập để test không cần GPU.
- [x] Có test tự động grep để chặn logic theo `biz_`, `dev_`, `q_` trong code chạy thật.
- [x] biz_101 có điểm dương bằng bộ khung đơn giản.
- [x] Mỗi khối có README và phiếu việc.

## 8. Docker
*(Để trống — bổ sung khi BTC công bố Docker guideline.)*

## 9. Kế hoạch làm một mình, 14 giờ/ngày (từ T3 03/11)

*Quyết định 02/11: leader tự làm toàn bộ, mỗi ngày 14 giờ. Mục 5 và 6 (chia vai) không còn áp dụng; các phiếu việc G1–G7 vẫn dùng làm danh sách việc và tiêu chí "xong".*

### Nguyên tắc xếp lịch
1. **Việc chưa chắc làm được thì làm trước:**
   - LLM hiểu câu hỏi có đủ tốt không (K3);
   - mapping tự động cho cửa hàng chưa từng thấy (G2);
   - Docker chạy được trong giới hạn của BTC.

   Việc chắc làm được (tính ngày, thư viện hàm, format) xếp xen vào giữa.
2. **Làm theo chiều sâu.** Đi hết một đường từ đầu đến cuối cho nhóm câu bán hàng (~60% câu train) rồi mới mở rộng loại câu. Từ 09/11 phải nộp public được mỗi ngày.
3. **Mỗi ngày 3 khối:**
   - *Sáng, 5 giờ:* việc khó hoặc chưa chắc làm được.
   - *Chiều, 5 giờ:* việc chắc làm được, kèm test.
   - *Tối, 4 giờ:* chạy đánh giá trên train, phân tích lỗi, cập nhật `HAN_CHE`, `TIEN_DO`, commit.
4. **Không bao giờ để train có câu sai mà không biết vì sao.** Mỗi câu sai phải có lý do ghi trong file hạn chế, hoặc đã có cổng chặn.

### Lịch
| Ngày | Sáng: việc khó | Chiều: việc chắc làm được | Xong khi |
|---|---|---|---|
| **T3 03/11** | **G1 loader:** đọc xlsx (mọi sheet, engine nhanh `calamine`), dò header 1–2 dòng và dòng tiêu đề, `year_hint` từ tên sheet / file | Bỏ dòng "Cộng" (H18), kiểu tiền mới (`409tr663`), giới hạn thời gian đọc mỗi cửa hàng (H12 phần đọc file), profiling: kiểu cột, min/max | Đọc 44 cửa hàng không lỗi, không thiếu sheet; header đúng ở biz_105, biz_117, dev_004, dev_013; đọc hết train dưới 2 phút |
| **T4 04/11** | **K3:** chạy Qwen3-8B 4-bit trên laptop (llama.cpp server, ép output theo schema v1.1), prompt = schema + data card + 6 ví dụ BM25; chọn engine cho Docker | **G2 phần 1:** cài 8 biến đổi trong `TRANSFORMS`, điền ô trống cùng đơn (§8) *trước* bước bỏ dòng trùng; mapping tay cho 3 cửa hàng khác kiểu | K3: tỉ lệ JSON hợp lệ và tỉ lệ plan đúng trên 99 plan K2 + 24 plan mẫu. 4 cửa hàng có mapping tay qua đủ 6 bước kiểm tra |
| **T5 05/11** | **G2 phần 2:** mapping tay cho thêm 5 cửa hàng (đủ 8, có biz_123 sqlite, biz_124 nhiều nguồn); **H17** kiểm tra theo nghĩa, ngưỡng đo trên 8 mapping | **G4:** mọi kiểu kỳ và kỳ so (§2), `STOCK_METRICS`, Tết; mỗi dòng §2 một test | 8 mapping tay qua kiểm tra; mapping hỏng cố ý (đổi cột tiền, cột ngày) bị bắt; test §2 qua hết |
| **T6 06/11** | **G6 nối thực thể:** RapidFuzz không dấu trên tên hàng, nhóm, kênh, khách, nhân viên; ngưỡng + chặn khi hai ứng viên gần bằng nhau | **G5 nhóm bán hàng:** bộ lọc, tăng trưởng / chênh lệch, tỉ trọng, huỷ, trung bình đơn, số lượng theo đơn vị, xếp hạng khách / ngày / tháng, đếm theo ngưỡng | `oracle --all` trên 8 cửa hàng: **0 câu sai**; ghi tỉ lệ trả lời |
| **T7 07/11** | **G3:** nối LLM thật vào `parse_question`, đối chiếu với baseline, timeout mỗi lời gọi (H12); thuê GPU 1 buổi để so Qwen3-8B và Qwen3-14B | Data card ([B] `build_card`) đủ cho prompt; chọn ví dụ bằng BM25 trên kho đã kiểm chứng (K1) | Chạy hết 8 cửa hàng với LLM + mapping tay: PA không thấp hơn khi dùng baseline; chốt model |
| **CN 08/11** | **G2 phần 3: `map_business` tự động.** Luật đồng nghĩa tên cột (rút từ 8 mapping tay) trước, LLM điền phần còn thiếu, chạy kiểm tra, sai thì cho LLM sửa 1 lần | Chấm mapping tự động so với mapping tay; bảng lỗi theo cửa hàng | Trên 8 cửa hàng: mapping tự động **ra cùng điểm** với mapping tay, hoặc bị chặn ở bước kiểm tra (không câu sai thêm) |
| **T2 09/11** | **Tích hợp cả 30 cửa hàng train** (mapping tự động + LLM); phân tích lỗi theo ngành | **Nộp public lần đầu**; `eval.validate` trước khi nộp | Có PA train (30 cửa hàng) và điểm public; mọi câu sai có lý do |
| **T3 10/11** | **Docker:** image theo guideline BTC (nếu chưa có thì theo mặc định CUDA 12.8), model weights, `predict.sh`, chép `assets/` (H14); chạy `--network none`, `/data:ro` | H12 đầy đủ (hạn chót truyền xuống từng khối); đo thời gian hết bộ public, nhân 1,5 | Container chạy hết public không mạng, ra file hợp lệ, dưới 1 giờ cho 1000 câu |
| **T4 11/11** | **Loại câu v2:** công nợ (§4), nhập hàng, tồn kho, lô / hạn dùng (§5) | Giá bán ngày D, hiệu ứng tăng giá, lãi gộp / lãi ròng; test từng luật | 0 câu sai trên train ở nhóm mới |
| **T5 12/11** | **Luật theo ngành §6** (cà phê size, nhà thuốc, vật liệu xây dựng, và 3 ngành mới của rulebook public: chỉ theo luật, không có dữ liệu train để thử) | **Bật unanswerable:** nhóm A (kỳ ngoài dữ liệu) và B (thiếu bảng/cột, khi mapping chắc chắn); đo trên 70 câu unanswerable của train | Unanswerable đúng ≥ 95% trên train, không làm sai câu trả lời được |
| **T6 13/11** | **N4:** chạy train 2 lần (laptop và GPU thuê), so từng câu; chỉnh ngưỡng các cổng | **Khóa tính năng.** Chạy toàn bộ test; rà luật thi (không logic theo id, không mạng, giấy phép) | Lệch giữa 2 lần ≤ 0,01 PA; checklist luật thi đạt |
| **T7 14/11** | **Nộp Docker lần 1:** build, `docker save`, nén, `sha256sum`, upload Google Drive, form "Solution Submission" | README (model, giấy phép, cách chạy), tài liệu phương pháp | Đã nộp lần 1; tải lại đúng file đã nộp và chạy thử được |
| **CN 15/11** | Dự phòng: chỉ sửa lỗi an toàn (bỏ trống thêm, không mở tính năng) | Nộp public mỗi ngày, so với bản đã nộp Docker | |
| **T2 16/11** | Lần 2 chỉ nộp nếu tốt hơn rõ ràng **và** đã chạy thử trên GPU giống máy chấm | Upload trước **18:00** | Đóng băng 23:59 |

Sau đóng băng: 17–19/11 tải lại image đã nộp, kiểm checksum, chạy thử; 20/11 lúc 9:00 chạy private test, giữ log, nộp trước 23:59 ngày 23/11.

### Khi bị chậm thì bỏ gì (theo thứ tự)
1. [D2] sinh code: không làm (H13).
2. Luật 3 ngành mới của rulebook public: chỉ làm phần dùng lại được hàm chung.
3. Loại câu v2 hiếm: lãi ròng, trả góp, bảo hành.
4. Unanswerable nhóm B. Giữ nhóm A, vì quyết định bằng code nên chắc chắn.

**Không bao giờ bỏ:** cổng kiểm tra mapping, 0 câu sai trên train, Docker nộp trước 14/11.

### Mốc phải dừng lại xem xét
- **Tối 04/11 (sau K3):** nếu Qwen3-8B cho dưới 70% plan đúng thì tăng ví dụ mẫu hoặc đơn giản hoá schema trước khi đi tiếp.
- **Tối 08/11:** nếu mapping tự động sai mà không bị chặn ở dù chỉ 1 cửa hàng, thì 09/11 dành để sửa kiểm tra (H17) trước khi tích hợp.
- **Tối 09/11:** nếu PA train ≤ 0 thì dừng mở rộng, chỉ làm cho các cổng chặt hơn.

### Ràng buộc mạng (04/11)
Leader dùng 4G, nên **không tải hay upload file nặng từ laptop** (H20). Mọi việc nặng làm trên máy GPU thuê:
- tải model;
- chạy K3 và so 8B với 14B;
- đo độ ổn định khi chạy lại (N4);
- build Docker và upload image lên Google Drive bằng `rclone`.

Vì vậy K3 (04/11) dời sang ngày thuê GPU đầu tiên. Nên thuê sớm hơn 07/11 nếu được, vì K3 là mốc dừng để xem xét. *(Cập nhật 05/11: có wifi, K3 đã chạy xong trên laptop, plan đúng 83,7%.)*

### Việc ngoài code
- Hỏi lại BTC mỗi ngày về Docker guideline cho tới khi có (tin nhắn đã soạn ở phiên 1).
- Thuê GPU: 1 buổi ngày 07/11 (so 8B và 14B), 1 buổi ngày 13/11 (đo độ ổn định), 1 buổi ngày 14/11 (chạy thử image).

## 10. Kế hoạch chi tiết các việc lớn tiếp theo (viết cuối phiên 2)

*Căn cứ của thứ tự ưu tiên (đo trên train, xem [BAN_GIAO_PHIEN_2.md](BAN_GIAO_PHIEN_2.md)):*
- Câu hỏi sinh theo mẫu: sau khi che số, 90% câu có câu giống ≥ 90% ở một cửa hàng khác.
- 16/30 cửa hàng có "anh em" dùng gần cùng bộ tên cột.
- K3: Qwen3-8B đọc đúng 83,7% plan.
- Bảng xếp hạng public: đội tốt nhất khoảng 0,9.

Vì vậy, điểm tới từ ba thứ: **phủ đủ các mẫu câu bằng hàm tính đúng**, **kho ví dụ đã kiểm chứng phủ mọi mẫu**, và **mapping tự động vững với các họ khuôn file**.

**Thứ tự và phụ thuộc:**
- T1 → T3: T1 cho danh sách mẫu câu theo tần suất, T3 làm theo danh sách đó.
- T2 + T3 → T4: cần hàm tính để kiểm chứng plan bằng đáp án.
- T5 độc lập, nhưng cần LLM.
- Tất cả → tích hợp 30 cửa hàng và nộp public (mục 9, ngày 09/11).
- T6 chạy song song qua đêm.

| Việc | Ngày | Thời gian | Cần llama-server |
|---|---|---|---|
| T1 Gom cụm mẫu câu | 06/11 sáng | ~1,5 giờ | có (gắn plan cho cụm) |
| T2 G6 nối tên | 06/11 | ~3 giờ | không |
| T3 G5 thư viện hàm + nối LLM | 06–07/11 | ~8–10 giờ | có (đo cuối) |
| T4 Kho ví dụ + cổng "câu anh em" | đêm 06/11 + 07/11 | 1,5 giờ chạy + ~3–4 giờ | có |
| T5 Mapping tự động | 07–08/11 | ~6–8 giờ | có |
| T6 Thử Qwen3-14B | qua đêm | tải 9 GB + K3 | có |

### T1. Gom cụm mẫu câu (06/11 sáng, ~1,5 giờ)
- **Mục tiêu:** biến 3000 câu train thành danh sách mẫu câu kèm số câu mỗi mẫu. Đây là danh sách việc của T3, xếp theo điểm đem lại, và là thước đo độ phủ.
- **Đầu vào → đầu ra:** `data/train/questions.jsonl`, 123 plan viết tay → `tools/research/templates.py`, `docs/research/templates.md` (bảng các cụm), `assets/plans/templates_train.json` (cụm → danh sách id câu). Chỉ dùng train.
- **Các bước:**
  1. Chuẩn hoá câu: bỏ dấu, che số và ngày bằng `#`, nở viết tắt chắc chắn (`dthu`, `hnay`, `hqua`, `trc`).
  2. Che tên riêng. Với 8 cửa hàng có mapping thì so khớp với tên hàng / khách trong dữ liệu; còn lại thì che các cụm khớp tên hàng của bất kỳ cửa hàng train nào (danh sách tên lấy bằng loader).
  3. Gom cụm theo kiểu "câu đại diện": `rapidfuzz.token_set_ratio ≥ 90` so với đại diện thì vào cụm đó. Ghi lại ngưỡng đã dùng.
  4. Gắn mỗi cụm với loại câu / chỉ số / kiểu kỳ, lấy từ plan viết tay nếu cụm có, không có thì từ plan LLM của câu đại diện.
  5. Gắn trạng thái hàm tính: đã có trong `metrics/` / chưa có / thuộc nhóm v2 (công nợ, kho, lãi…).
- **Thế nào là xong:**
  - ≥ 95% câu nằm trong cụm có ≥ 2 câu.
  - Có bảng 60 cụm lớn nhất: số câu, ví dụ, plan, hàm cần, trạng thái.
  - Có con số "tỉ lệ câu train nằm trong cụm đã có hàm".
- **Rủi ro:** ngưỡng 90 gộp nhầm hai mẫu khác nghĩa (ví dụ "số đơn" với "số đơn huỷ"). Cách chặn: trong một cụm, các plan phải cùng loại câu và cùng chỉ số; cụm lẫn thì tách ra.

### T2. G6: nối tên trong câu với giá trị trong dữ liệu (06/11, ~3 giờ)
- **Mục tiêu:** điền `ResolvedPlan.linked`. Ví dụ "coca" → "Coca Cola 330ml" (hoặc mã), "tại quầy" → `store`, "ck" → `transfer`. Câu có bộ lọc chỉ được trả lời khi mọi tên đã nối.
- **File:** `datamate/nlu/linking.py` (mới), `nlu.link_entities` gọi vào đó; `tests/test_linking.py`.
- **Ứng viên theo trường lọc:**

  | Trường lọc | Lấy từ |
  |---|---|
  | product | `lines.product_name`, `products.product_name`, mã `product_key`; nhiều tên cùng một mã (biz_120: 162 tên cho 80 mã) thì nối về **mã** |
  | product_group | `lines.product_group`, `products.product_group` |
  | channel, payment_method, customer_group, employee | cột tương ứng của `orders` |
  | customer | `customers` / `orders.customer_name` + mã |
  | active_ingredient, brand, category, supplier, vehicle_model, plate, service | cột tương ứng |

- **Thuật toán:**
  1. Bỏ dấu, chữ thường.
  2. Khớp tuyệt đối → điểm 100.
  3. Không thì `rapidfuzz.WRatio` / `token_set_ratio`, **ngưỡng ≥ 90**.
  4. **Hai ứng viên đầu cách nhau < 5 điểm thì không nối.**
  5. Nhận cả mã (SP0001, NV002, KH0040).
- **Từ đồng nghĩa cho kênh và hình thức thanh toán:** lấy từ giá trị thật của train (biz_120, biz_123, biz_124), viết trong `assets/` chứ không viết trong code.
  - Kênh: "tại quầy" / "trực tiếp" → `store`, "điện thoại" → `phone`, "zalo" → `zalo_oa`.
  - Thanh toán: "tiền mặt" → `cash` / "Tiền mặt", "chuyển khoản" / "ck" → `transfer` / "Chuyển khoản", "ví điện tử" → `ewallet`, "cod" → `cod`, "ghi nợ" → `debt`.
- **Thế nào là xong:**
  - Có test cho khớp tuyệt đối, gõ sai, viết tắt, hai ứng viên ngang nhau, mã.
  - Trên câu train có bộ lọc của 8 cửa hàng, ghi tỉ lệ nối được. Sau T3, câu đã nối mà trả lời sai phải là 0.
- **Rủi ro:** nối nhầm sang mặt hàng tên gần giống ("Bia Tiger lon" với "Bia Tiger Bạc lon"). Cách chặn: ngưỡng cao, luật ngang điểm thì không nối, log `link_scores` để phân tích.

### T3. G5: thư viện hàm nhóm bán hàng + nối LLM vào pipeline (06–07/11, ~8–10 giờ, việc lớn nhất)
- **Mục tiêu:** mỗi mẫu câu phổ biến (theo T1) có một hàm tính đúng tuyệt đối theo rulebook.
- **Nguyên tắc cho mỗi hàm:** khai báo `requires`, `rules` (id trong `assets/rules/reference_rules.json`), `filters`, `entity` (registry R17).
  - Tiền làm tròn bằng `formatter.money` (nửa lên); phần trăm làm tròn 2 chữ số.
  - Bằng nhau thì xếp theo mã tăng dần (§9).
  - Không chắc thì trả `None`.
- **Các nhóm hàm, theo thứ tự làm** (file `datamate/metrics/sales.py`, tách file nếu dài):

  | Nhóm | Nội dung | Luật |
  |---|---|---|
  | A. Doanh thu và đơn | `revenue` và `order_count` có bộ lọc; `cancel_count`; `cancel_rate` (mẫu số là mọi đơn đặt trong kỳ, mọi trạng thái); `avg_order_value` (doanh thu / số đơn, làm tròn về đồng); `customer_count` ("khách đã mua" có ≥ 1 đơn hợp lệ, khách lẻ không tính) | §1, §3 |
  | B. So sánh và tỉ trọng | `compare` dạng `pct_change` ((a − b) / b × 100; b = 0 thì `None`), `diff` (a − b), `which_more`; so giữa hai bộ lọc (ca chiều so với ca sáng, mốc là ca sáng); `share` (mẫu số là doanh thu cả cửa hàng cùng kỳ, kể cả đơn vãng lai, hoặc `share_of`) | §1, §2 |
  | C. Số lượng | quy về đơn vị cơ bản; "bán được bao nhiêu <đơn vị>" chỉ cộng mặt hàng có đơn vị cơ bản là đơn vị đó; size M / L theo đuôi tên "(M)" / "(L)", không phân biệt hoa thường | §3, §6 |
  | D. Xếp hạng | mặt hàng theo số lượng / doanh thu / lãi gộp (giá vốn ghi trên dòng bán); khách theo doanh thu / số đơn (không tính khách lẻ); ngày / tháng theo doanh thu / số đơn (ra `YYYY-MM-DD` / `YYYY-MM`); giờ; nhân viên theo doanh thu | §3, §5, §9 |
  | E. Đếm theo ngưỡng, chuỗi | đơn theo doanh thu ≥ X; khách theo số đơn ≥ N (kể cả dạng phần trăm); mặt hàng có mặt trong ≥ N đơn; `trend` (tăng liên tục, ra boolean); `series` (list theo tháng) | §2 "quá N" không gồm N |
  | F. Hàng ế | `list_items unsold_in_period` với `count`: đã từng bán trước kỳ mà trong kỳ không bán | §5 |

- **Bộ lọc dùng chung**, một hàm áp bộ lọc cho mọi chỉ số: product, product_group (qua `products` nếu dòng không có), channel, payment_method, customer_group (đơn vãng lai không thuộc nhóm nào), customer, employee, shift (cần `has_time`; sáng 06:00–13:59, chiều 14:00–21:59), weekday, size, prescription, active_ingredient (ghi đúng như vậy; thuốc phối hợp là loại riêng).
- **Nối LLM vào pipeline:**
  - `predict` và `eval.oracle` thêm `--llm-url` (mặc định không dùng).
  - Mapping không đạt thì **không gọi LLM**, để tiết kiệm thời gian.
  - Log ghi plan đến từ LLM hay baseline.
- **Test:** `tests/test_metrics_sales.py`, mỗi luật một cửa hàng tí hon tự dựng có đáp án tính tay.
- **Thế nào là xong:**
  - `python -m datamate.eval.oracle --all --llm-url http://127.0.0.1:8091` trên 8 cửa hàng: **0 câu sai**.
  - Ghi tỉ lệ trả lời trước và sau.
  - Mỗi câu sai trong quá trình làm phải có lý do ghi vào file hạn chế, rồi được sửa hoặc có cổng chặn.

### T4. Kho ví dụ đã kiểm chứng + cổng "câu anh em" (chạy qua đêm 06→07/11 + ~3–4 giờ)
- **Mục tiêu:** đẩy độ chính xác trên câu đã trả lời lên ≥ 95% mà không mất nhiều câu trả lời.
- **Kho ví dụ** (`python -m datamate.eval.build_bank`, mới; ra `assets/plans/verified_train.jsonl`):
  1. Cho LLM đọc cả 3000 câu train, mỗi câu dùng kho ví dụ **không chứa câu của cùng cửa hàng**. Khoảng 3000 × 1,8 giây ≈ 1,5 giờ.
  2. Với 8 cửa hàng có mapping: chạy plan → so đáp án → `verified_by = "answer"`.
  3. Với 22 cửa hàng còn lại: plan có cùng dạng (loại câu, chỉ số, kiểu kỳ, kiểu so sánh, các trường lọc, đối tượng / tiêu chí / k của xếp hạng) với plan đã kiểm chứng của câu cùng cụm T1 → `verified_by = "template"`.
- **Cổng "câu anh em"** ([V]/[E], đổi `Signals` trong `contracts/results.py`):
  - Câu mới có câu đã kiểm chứng giống ≥ ngưỡng (ở cửa hàng khác) **và** plan cùng dạng → tin cậy cao.
  - Không có thì cần baseline đồng ý, hoặc bỏ trống.
- **Đo theo kiểu bỏ ra một cửa hàng:** với từng cửa hàng trong 8, loại câu của cửa hàng đó khỏi kho rồi đo độ chính xác và tỉ lệ trả lời ở ngưỡng 85 / 90 / 95. Chọn ngưỡng cho độ chính xác ≥ 95% với tỉ lệ trả lời cao nhất.
- **Thế nào là xong:** có bảng ngưỡng → (độ chính xác, tỉ lệ trả lời); ngưỡng đã chốt ghi vào `configs/`.

### T5. G2 phần 3: mapping tự động `map_business` (07–08/11, ~6–8 giờ)
- **Mục tiêu:** cửa hàng chưa từng thấy → mapping qua đủ 10 bước kiểm tra, hoặc bị chặn. Không bao giờ sai mà lọt.
- **Các bước:**
  1. `datamate/mapping/synonyms.py`: rút từ `assets/mappings/train/*.json`:
     - cột chuẩn → các tên cột thô (bỏ dấu);
     - từ vựng trạng thái (giá trị thô → mã chuẩn; đã gặp hơn 25 cách ghi);
     - các cách ghi khách lẻ.
  2. Nhận vai trò bảng (đơn, dòng hàng, sản phẩm, khách, thanh toán, nhập, tồn, lô…) theo độ trùng tên cột với từ điển và cột mã dùng chung giữa các bảng.
  3. Luật điền trước phần chắc chắn. LLM điền phần còn thiếu, ép theo JSON schema của `Mapping` (làm schema sinh output như của plan). Prompt gồm profile (cột, kiểu, 5 mẫu), README, và 1–2 mapping tay của cửa hàng "anh em" gần nhất (đo bằng độ trùng chữ trong tên cột).
  4. Chạy 10 bước kiểm tra. Hỏng thì đưa `detail` của bước hỏng cho LLM sửa **một lần**. Vẫn hỏng thì cửa hàng bỏ trống.
- **Đo:**
  - Trên 8 cửa hàng, theo kiểu bỏ ra một cửa hàng (bỏ mapping tay của chính nó khỏi từ điển và ví dụ): mapping tự động phải ra **cùng điểm** với mapping tay, hoặc bị chặn.
  - Trên 22 cửa hàng còn lại: chạy cả chuỗi, câu sai = 0, ghi tỉ lệ trả lời.
- **Rủi ro:**
  - LLM chọn nhầm cột giống nhau. Có kiểm tra theo nghĩa (H17) chặn.
  - Cửa hàng có kiểu bảng chưa gặp (trả góp, sổ sửa xe…) thì đưa vào `extra_tables` và bỏ trống loại câu đó.

### T6. (Song song, tuỳ chọn) Thử Qwen3-14B
- Tải `Qwen/Qwen3-14B-GGUF` bản Q4_K_M (~9 GB) bằng wifi, đối chiếu sha256 với Hugging Face.
- Chạy llama-server với `-ngl` một phần (laptop 8 GB VRAM), cho K3 chạy qua đêm.
- Nếu hơn 8B rõ rệt (≥ 3 điểm plan đúng) thì dùng 14B cho Docker; trên RTX 5090 32 GB chạy được bản Q8.
- Tổng tham số vẫn ≤ 15B nếu chỉ dùng một model.
