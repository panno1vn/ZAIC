# Bàn giao phiên 8 (06–07/11) → phiên 9

*Viết 07/11/2026. Docker nộp lần 1 ngày 14/11; đóng băng 16/11 23:59.*

- Chi tiết từng bản sửa: [HAN_CHE_VA_CAI_THIEN.md](HAN_CHE_VA_CAI_THIEN.md), mục "Phiên 8 (06/11)", N45–N71.
- Lượt nộp và kết quả chẩn đoán: [CAN_XAC_MINH.md](CAN_XAC_MINH.md).
- Bàn giao trước: [BAN_GIAO_PHIEN_7.md](BAN_GIAO_PHIEN_7.md).

## Bắt đầu phiên mới
Dán vào phiên chat mới:

> Đọc `docs/BAN_GIAO_PHIEN_8.md`, rồi `docs/CAN_XAC_MINH.md`. Kiểm `git status` và test (`.venv\Scripts\python.exe -m pytest -q`). Làm tiếp mục "Việc tiếp theo", bắt đầu từ việc 1 (run11).

- **Python:** `.venv\Scripts\python.exe`. Python hệ thống không có pytest. In tiếng Việt ra màn hình thì đặt `PYTHONIOENCODING=utf-8`.
- **LLM:** trưởng nhóm tự mở llama-server ở cổng 8091. Claude không chạy file `.exe`.
  ```powershell
  cd E:\llm\llama-b12064
  .\llama-server.exe -m E:\llm\models\Qwen3-8B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --parallel 1 --host 127.0.0.1 --port 8091
  ```
- **Trang tổng kết** (artifact, riêng tư): [Đường lên 0,9](https://claude.ai/artifact/ByVitABJohuFUt9UKUL3rM).

## Tình hình
| Thước đo | Giá trị |
|---|---|
| Điểm public mới nhất | **0,744**, nộp 07/11 với tên "run10_s27_full". File: `outputs/replay/run10_s27m/submission.jsonl` |
| Câu trả lời public | 802/1000: **773 đúng, 29 sai** (96,4%); 198 bỏ trống |
| Train | **2730 đúng / 0 sai / 270 bỏ trống, PA +0,910**. Log `outputs/eval_mapping_s8v.log`, đo bằng `tools/eval_cached.py`, CACHE MISSES 0 |
| Test | **449 qua** |
| Model | Qwen3-8B Q4_K_M. Đã so với Qwen3-14B trên Kaggle (N49); giữ 8B |

Điểm public qua các lượt:

| Lượt | Điểm |
|---|---|
| lượt 1 | 0,316 |
| run4 | 0,342 |
| run9 | 0,540 |
| run10_s8 | 0,608 |
| run10_s27 | **0,744** |

**Lượt 0,744 không phải một lượt LLM liền.** Nó ghép ba nguồn, cả ba đọc lại bằng code 07/11 (`tools/replay_run.py --enrich`):
- 11 cửa hàng: đầu ra LLM đã ghi của run10 (`outputs/replay/run10_s27`);
- hai cửa hàng điện thoại: lượt LLM mới `outputs/public_phones_s8d`, đọc lại thành `outputs/replay/phones_s27`;
- cửa hàng mẹ và bé: lượt LLM mới `outputs/public_baby_s8`, đọc lại thành `outputs/replay/baby_s27`.

Docker sẽ chạy LLM trực tiếp, không đọc lại từ log, nên phải xác nhận một lượt đủ (việc 1).

### Câu sai: kết quả chẩn đoán 07/11
| Nhóm bỏ trống (8 cửa hàng cũ) | Điểm | Đúng / sai |
|---|---|---|
| so sánh (73 câu) | 0,677 | 70 / 3 |
| xếp hạng (70 câu) | 0,682 | 66 / 4 |
| đếm theo ngưỡng (58 câu) | 0,698 | 52 / **6** (sai 10%, nhiều nhất) |
| một số có bộ lọc (72 câu) | 0,680 | 68 / 4 |
| **phần còn lại (529 câu)** | — | **12 sai, chưa khoanh vùng** |

Phần còn lại gồm: cửa hàng cũ, một số không lọc (179); cửa hàng cũ, tỉ trọng / chuỗi / nợ / kho (70); 6 cửa hàng mới (280). Không nhóm nào sai quá 50% (ngưỡng tạm chặn), nên chưa chặn nhóm nào. Bộ nộp để khoanh vùng 12 câu này đã dựng sẵn (việc 2).

### 198 câu bỏ trống, theo nguyên nhân
Đếm từ log đọc lại; mỗi cửa hàng lấy log từ đúng nguồn của nó:

| Nguyên nhân | Số câu | Ghi chú |
|---|---|---|
| **Có plan, hàm tính không ra kết quả** | **93** | Log không ghi vì sao. Theo hàm và chỉ số: value doanh thu 19, value tiền nhập 6, value số lượng 5, compare doanh thu 5, list_items 5, xếp hạng 11, tỉ trọng 5, count_where 5, nợ 7, kho / hạn dùng 6… |
| Cổng đọc loại plan của LLM | 76 | metric 21, payment_method 7, product 5, channel / is_warranty / category / asks 4 mỗi loại… Phần lớn chặn **đúng** (đã xem ở phiên 8) |
| JSON sai schema không sửa được | 11 | |
| Hoà hạng | 5 | Chặn đúng: bộ câu hỏi không hỏi hạng hoà (N25) |
| Cổng thuật ngữ | 4 | |
| Kỳ hỏi ngoài dữ liệu, unanswerable chưa bật | 3 | |
| Lỗi gọi LLM | 3 | |
| LLM và baseline đọc khác nhau | 3 | |

Bỏ trống nhiều nhất ở các cửa hàng: dev_014 33, dev_006 30, dev_008 24, dev_004 21, dev_003 18.

## Luật dữ liệu (không đổi từ phiên 7)
- Xem dữ liệu public chỉ để tìm **kiểu lỗi định dạng**. Mọi bản sửa là quy tắc chung.
- Không có id cửa hàng hay id câu hỏi trong code, kể cả comment. `test_no_id_logic` đã bắt hai lần, lần gần nhất ở phiên 8.
- Không viết mapping, plan hay đáp án tay cho cửa hàng public.
- Train phải 0 sai và **không giảm** câu đúng.
- Không gọi API khi dự đoán. Không gán nhãn câu public hay private. Không dò đáp án từng câu bằng lượt nộp: chỉ chẩn đoán theo nhóm lớn, và chỉ in số đếm.
- Model ≤ 15B tổng và công bố trước 26/10/2026. Dữ liệu tổng hợp chỉ dùng lúc phát triển.
- Khi nộp chọn loại "SLM". Trưởng nhóm tự commit. Hỏi trước khi tải file > 50 MB (mạng 4G).

## Phiên 8 đã làm (HAN_CHE N45–N71)
| Mục | Việc | Kết quả |
|---|---|---|
| N45 | `Mapping.ok`: cửa hàng chỉ có bảng đơn được phép có bảng phụ | sổ sửa xe 0 → có kết quả |
| N46–N48 | khái niệm mới của rulebook public: trung bình mỗi thứ X, thợ làm nhiều nhất, chăm chỉ, trung thành, xe khách quen; hoa hồng thợ; việc trong ô "Làm gì" (`nlu/jobs.py`); gộp cách viết dòng xe; gợi ý prompt chỉ bật khi cửa hàng có dữ liệu đó | |
| N49 | K1 trên Kaggle: 14B không hơn 8B rõ (K3 +0,6 điểm), chậm gấp đôi; 4 cổng mới từ lỗi của 14B | **giữ 8B** |
| N50–N52 | nhóm hàng lấy từ README; tên Bắc – Nam; khách sộp, khách hay đổi ý, mặt hàng được ưa chuộng, giờ cao điểm | train 2656 → 2681 |
| N53 | mã luật chỉ dẫn khi plan dùng tới phải nằm trong `rule_ids()` | bắt trước khi chạy |
| N54 | log ghi lý do không có plan (`reading`: đầu ra thô của LLM, cổng, schema) | |
| N55–N56 | sổ sửa xe với LLM 0 → 43/50; run10; `scale_money` ("10 củ"); cổng "cùng kỳ năm trước" | **0,608** |
| N57 | chữ chỉ public mới có: "đh", "o đờ", "doanhthu", "40tr" | +18 câu |
| N58 | **năm hai chữ số "th 6/25"** bị bỏ nên 14 câu lệch một năm | sửa lớn nhất của phiên |
| N59–N61 | sửa ba dạng JSON sai schema; "T5/2025" là tháng chứ không phải thứ Sáu; "từ hồi X lên giá Y" (`temporal.price_rise_day`); kênh "sàn TMĐT", "tại tiệm" | |
| N62 | nợ chia theo tuổi nợ | train +3 |
| N63 | danh mục thuốc khoá theo tên | **train +35** (2684 → 2719) |
| N64 | điện thoại: loại hàng, dòng máy, hãng; sổ không ghi đơn vị | |
| N65–N67 | quy đổi đơn vị ghi bằng lời trong README; đơn giao nhiều đợt; **sửa cột `base_qty` bị map làm `qty`**, lỗi cũ do N65 làm lộ ra | train 2730 / 0 |
| N68 | sổ phụ của cửa hàng điện thoại (`mapping/side_books.py`): thu máy cũ, bảo hành theo IMEI, nợ, trả góp, quá hạn | 40 → 58 câu |
| N69 | mẹ và bé: hãng, số sữa, size bỉm, "1 thùng = 4 bịch", khách thành viên mới | |
| N70–N71 | tỉ trọng có mẫu số chép y tử số; "th 3/26 so th 3/25" bị đọc là so với kỳ liền trước | |

### Công cụ mới
| Công cụ | Dùng để |
|---|---|
| `tools/eval_cached.py` | đo train **không cần llama-server**. Dùng cache mapping và plan đã lưu, khoảng 15 phút. CACHE MISSES 0 nghĩa là bằng đúng một lượt có server. Thêm `--plans outputs/bank/llm_plans.14b_kaggle.jsonl` để đo bằng plan của 14B |
| `tools/replay_run.py` | đọc lại đầu ra LLM đã ghi (`reading.llm_raw`, có từ run10) qua code hôm nay; ghi log từng câu. `--enrich` áp lại phần làm giàu từ README và sheet ghi tắt |
| `tools/run_shops.py` | chạy LLM cho vài cửa hàng public, khi gợi ý prompt hay hàm của cửa hàng đó đổi |
| `tools/ablate_groups.py` | dựng lượt chẩn đoán theo nhóm hàm từ log. `--only-shops` giới hạn theo cửa hàng; `--submission` chỉ file gốc |

## Bài học của phiên 8
1. **"0 sai trên train" thiên về 8B.** Các cổng được dựng từ lỗi của chính 8B trên 3000 câu train. Plan của một model khác (14B) lộ ngay 4 lỗ hổng cổng, nên là một bộ thử rẻ để tìm lỗ hổng.
2. **Đổi schema hay prompt là đổi cách LLM đọc một phần câu cũ**: run10 có 7 câu đổi chỉ vì schema thêm hai giá trị. Sau mỗi lượt LLM mới phải so từng câu với lượt trước.
3. **Public có định dạng train không có**: "M/YY", "M-YYYY", "T5/2025", "đh", "o đờ", "10 củ", "từ hồi X lên giá Y". Sửa lớn nhất phiên (N58) đến từ việc rà hình dạng ngày tháng. Gặp nhóm câu lạ thì xem hình dạng định dạng trước.
4. **Một bản sửa đúng có thể làm lộ lỗi cũ** đang bị một câu bỏ trống che (N65 làm lộ N67: 3 câu sai trên train). Phải chạy train đủ sau mọi thay đổi ở mapping hay metrics.
5. **Gợi ý prompt chỉ bật theo điều kiện** (cửa hàng có cột đó, hoặc câu có từ đó). Nhờ vậy prompt của 3000 câu train giữ nguyên từng byte và kho plan đã kiểm chứng vẫn dùng được. Gợi ý bật rộng sẽ lan sang câu khác: gợi ý trả góp từng làm LLM gắn bộ lọc trả góp vào câu không nói tới.
6. **Phần lớn việc không cần LLM**: đọc lại từ log mất vài phút, còn một lượt đủ mất 40 phút.

## Việc tiếp theo
Hiện 0,744 = 773 đúng − 29 sai. Mỗi câu sai chuyển thành bỏ trống được **+0,001**, chuyển thành đúng được +0,002. Mỗi câu bỏ trống trả lời đúng được +0,001.

1. **run11: một lượt LLM đủ 1000 câu bằng code cuối** (~40 phút; cần trưởng nhóm mở server).
   - Lệnh:
     ```powershell
     .venv\Scripts\python.exe -m datamate.predict --data data/public_test --out outputs/public_run11 --llm-url http://127.0.0.1:8091
     ```
   - So từng câu với `outputs/replay/run10_s27m/submission.jsonl`. Kỳ vọng gần như trùng, vì prompt của các cửa hàng khác không đổi từ run10.
   - Câu khác nhau là do LLM đọc khác (bài học 2): xem log, sửa theo quy tắc chung.
   - **Không tăng điểm, nhưng bắt buộc trước Docker**: Docker chạy đúng đường này, không đọc lại từ log.
2. **Nộp chẩn đoán `outputs/public_ablation12/`** (5 lượt một ngày, so với 0,744). Danh sách và công thức ở CAN_XAC_MINH mục "Bộ nộp tiếp theo".
   - Thứ tự đề xuất: `bo_value_tron` (179), `bo_share_series_no_kho` (70), `bo_moi_003_009` (132), `bo_moi_dien_thoai` (58), một trong `bo_moi_me_be` / `bo_moi_sua_xe` (45).
   - Bộ này chỉ đúng khi lượt chính vẫn là run10_s27m. Nếu đã nộp run11 làm lượt chính và nó khác, dựng lại bằng `tools/ablate_groups.py outputs/public_run11 --out …`.
   - Ước lượng: tìm và sửa được khoảng một nửa trong 29 câu sai thì **+0,01 đến +0,02**.
3. **Đếm theo ngưỡng: 6/58 sai.** Đây là nhóm sai nhiều nhất.
   - Xem các hình plan `count_where` của public: thực thể, phép so, ngưỡng, kỳ.
   - So với hình plan của train để tìm kiểu train không có.
   - Chỉ xem hình dạng; không tự tính đáp án để đối chiếu.
4. **93 câu có plan mà hàm không ra kết quả.** Đây là nhóm bỏ trống lớn nhất.
   - Trước hết làm như N54 cho phần tính: hàm trả `None` thì ghi lý do vào `result` của log. Ví dụ: thiếu cột, không nối được tên, bộ lọc hàm không hiểu, ngưỡng chỉ nhắm số 0.
   - Sau đó đếm theo lý do và sửa nhóm lớn nhất.
   - Ước lượng: mở được 30–40% thì **+0,03**.
5. **76 câu bị cổng đọc loại**, nhiều nhất `metric` (21). Xem lại câu bị chặn **oan**, như N57 đã làm. Phần lớn đang chặn đúng. Ước lượng +0,005 đến +0,01.
6. **Docker (10–12/11)** trên RTX 5090 thuê dạng VM.
   - Build, rồi chạy public trong container không mạng và đo thời gian.
   - Kết quả phải bằng run11.
   - Nộp lần 1 ngày 14/11. Bản nháp ở `docker/`, ghi chú ở `docker/README.md`.
7. **Cho private** (cửa hàng và luật lạ):
   - đọc tham số từ rulebook thay vì chặn khi luật đổi;
   - trả unanswerable đúng chỗ (3 câu "ngoài phạm vi dữ liệu" đang để trống);
   - dữ liệu tổng hợp của ngành mới (H7).
8. **Dự phòng nếu kẹt ở phần LLM đọc câu:** distillation hoặc pruning từ model lớn hơn xuống ≤ 15B. Xem KE_HOACH, mục "Phương án dự phòng nếu bị kẹt", trong §11. Chưa làm.

Lịch đề xuất:

| Ngày | Việc |
|---|---|
| 08/11 | run11 + nộp bộ chẩn đoán |
| 08–09/11 | việc 3–5 |
| 10–12/11 | Docker |
| 13/11 | dự phòng |
| 14/11 | nộp Docker |
| 15–16/11 | chỉ sửa nhỏ có test, rồi đóng băng |

Ước lượng điểm public đến 16/11: **0,77–0,80**. Căn cứ: +0,01–0,02 từ câu sai, +0,03 từ nhóm "có plan mà không có kết quả", +0,01 từ câu bị cổng chặn oan.

## Lệnh hay dùng
| Việc | Lệnh |
|---|---|
| Đo train, không cần server (so được với các số ở trên) | `.venv\Scripts\python.exe tools/eval_cached.py` |
| Đo train có server (khi prompt của câu train đổi) | `.venv\Scripts\python.exe -m datamate.eval.mapping --llm-url http://127.0.0.1:8091` |
| Chạy public đủ 1000 câu (~40 phút) | `.venv\Scripts\python.exe -m datamate.predict --data data/public_test --out outputs/public_runN --llm-url http://127.0.0.1:8091` |
| Chạy LLM cho vài cửa hàng | `.venv\Scripts\python.exe tools/run_shops.py outputs/public_x dev_011 dev_014` |
| Đọc lại một lượt bằng code hôm nay, không LLM | `.venv\Scripts\python.exe tools/replay_run.py outputs/public_run10 --out outputs/replay/x --enrich` |
| Dựng lượt chẩn đoán theo nhóm hàm | `.venv\Scripts\python.exe tools/ablate_groups.py <thư mục có logs> --out <thư mục> [--submission …] [--only-shops …]` |
| Lượt chẩn đoán theo cửa hàng / hàm / chỉ số | `.venv\Scripts\python.exe tools/ablate.py outputs/public_runN --out x.jsonl [--shops …] [--function …] [--metric …]` |
| Kiểm định dạng file nộp | `.venv\Scripts\python.exe -m datamate.eval.validate --pred <file> --split public_test` |
| Xuất lại schema sau khi đổi hợp đồng | `.venv\Scripts\python.exe -m datamate.contracts.export_schema` |

**Quy tắc khi sửa:**
- Mỗi bản sửa có test và một mục trong HAN_CHE.
- Sau mỗi thay đổi ở `datamate/mapping/`, `datamate/metrics/` hay `datamate/nlu/`, chạy `tools/eval_cached.py`. Train phải 0 sai, không giảm câu đúng, và CACHE MISSES 0.
- Đổi schema hay prompt của câu train thì cache không còn khớp: phải đo lại có server.

## Git
Chưa commit gì từ `70c3dc4` (khoảng 75 file đổi hoặc mới). `outputs/`, `data/`, `*.gguf`, `*.zip` đã nằm trong `.gitignore`; `docker/models/` chỉ có `.gitkeep`. Lệnh cho trưởng nhóm:
```powershell
cd E:\ZAIC
git add .gitignore .dockerignore assets configs datamate docker docs kaggle tests tools
git commit -m "Phiên 5-8: N27, N33-N71: ngành mới (điện thoại, sửa xe, mẹ và bé), sổ phụ, năm hai chữ số, K1 giữ 8B; train 2730/0 PA +0.910; public 0.744"
git push origin main
```
