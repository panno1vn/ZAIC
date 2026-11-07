# Bàn giao phiên 4 → phiên 5

> **Đã có bàn giao mới hơn: [BAN_GIAO_PHIEN_6.md](BAN_GIAO_PHIEN_6.md)** (đêm 05→06/11: train 2651/0, PA +0,884; public run6).

*Viết tối 04/11/2026 (ngày hệ thống). Đóng băng 16/11 23:59. Phiên 4 làm tiếp từ [BAN_GIAO_PHIEN_3.md](BAN_GIAO_PHIEN_3.md); các mục luật, lệnh và câu hỏi BTC ở file đó vẫn giữ nguyên.*

## Bắt đầu phiên mới thế nào
Dán vào phiên chat mới:

> Đọc `docs/BAN_GIAO_PHIEN_4.md`, rồi `docs/TIEN_DO.md` và mục M của `docs/HAN_CHE_VA_CAI_THIEN.md`. Kiểm `git status` và test. Nếu đã có điểm các lượt nộp 05/11 thì ghi vào HAN_CHE N24 và làm theo mục "Đọc kết quả".

- **Python:** `.venv\Scripts\python.exe` (python hệ thống không có pytest). Test: `.venv\Scripts\python.exe -m pytest -q`, đếm dấu chấm.
- **LLM:** trưởng nhóm tự mở llama-server, cổng 8091 (lệnh ở BAN_GIAO_PHIEN_3). `eval.mapping` phải chạy **có** `--llm-url` thì mới so được với các số bên dưới.

## Tình hình
| Thời điểm | Train `eval.mapping --llm-url` (đúng / sai / trống) | PA |
|---|---|---:|
| Cuối phiên 3 | 2294 / 0 / 706 | +0,765 |
| + N25 cổng hoà hạng, N26 cửa hàng chỉ có đơn | 2331 / 0 / 669 | +0,777 |
| + N28 unanswerable nhóm A | 2347 / 0 / 653 | +0,782 |
| + N29 bổ sung thuộc tính theo README (phần 1) | 2407 / 0 / 593 | +0,802 |
| + N29 phần 2 (thêm danh mục) + N30 (đọc lại câu bị cổng căn cứ bỏ oan) | **2433 / 0 / 567** | **+0,811** |

Public: lượt 1 được 0,316 (343 đúng / 27 sai / 630 trống). Vẫn 8/14 cửa hàng map được; dev_009 chưa map được dù đã có N26.

Các lượt public đã chạy, chưa nộp (đều qua `eval.validate`):
- `outputs/public_run2/`: code có N25, N26, R46. Khớp tuyệt đối với bản chạy lại lượt 1 (LLM tất định); khác lượt 1 đúng 3 câu bị cổng hoà hạng chặn. 367 câu trả lời. Thêm N28 vào (`outputs/public_run2b/`) không đổi câu nào.
- **`outputs/public_run3/`: code cuối phiên 4. 392 câu trả lời.** So với run2: 363 câu giữ nguyên, **+29 câu** (10 nhờ N30 có plan mới, 19 nhờ N29 có cột thuộc tính), **−4 câu**. 4 câu này mất vì N29 thêm cột vào mapping làm thẻ dữ liệu trong prompt đổi, LLM đọc lại ra plan khác (3 câu không còn plan). Cổng câu anh em chặn 38 câu (run2: 28), vì một số plan mới chưa có câu anh em đã kiểm chứng.

## Phiên 4 đã làm (chi tiết ở HAN_CHE mục M)
| Việc | Căn cứ | Kết quả |
|---|---|---|
| **N25 cổng hoà hạng** | train: 0/281 câu xếp hạng có hoà, trong khi xếp khách theo số đơn của một tháng hoà ở hạng 1 tới 39%, nên bộ sinh đề bỏ câu hoà | train không mất câu nào; public lượt 1 chặn 3 câu `sales.rank` |
| **N26 cửa hàng chỉ có bảng đơn** | README "tiền hàng của đơn" = doanh thu §1; 4 cửa hàng có cả hai thì khớp 100% | biz_110 từ 0 lên 37 đúng / 0 sai; thêm kiểm tra nghĩa "tiền hàng khớp tổng dòng" |
| **N28 unanswerable nhóm A** | train: 16/16 câu có kỳ nằm hoàn toàn ngoài dữ liệu là unanswerable | +16 câu; public lượt này 0 câu dính |
| **N29 bổ sung thuộc tính theo README** | 142 câu train bỏ trống vì mapping chuyển từ mẫu thiếu nhóm khách, hoạt chất, kê đơn, nhóm hàng, thanh toán, nhân viên | +60 câu (phần 1), cùng N30 thêm +26 |
| **N30 đọc lại câu** | 10/25 câu không có plan do LLM tự thêm "đơn hoàn thành"; public lượt 1 có 109 câu không plan | +28 câu train có plan |
| `tools/replay_run.py` | chạy lại một lượt từ log, không LLM, chỉ in số đếm (N22) | khớp 1000/1000 với lượt 1; dựng file nộp trong khoảng 1 phút |
| Đo §7 "kỳ phủ một phần" | train không câu nào bỏ trống chỉ vì lý do này | không sửa |

## Phiên 5 (sáng 05/11, Claude tự làm khi trưởng nhóm vắng)
- **N32, tự sửa plan sai schema** ở 3 dạng đã gặp trên train (HAN_CHE mục M): thêm 6 câu train có plan. Train `eval.mapping --llm-url`: **2439 đúng / 0 sai / 561 bỏ trống, PA +0,813** (log `outputs/eval_mapping_s5a.log`). 348 test qua.
- **Public run4** (`outputs/public_run4/`, code có N32): **394 câu trả lời**, qua `eval.validate`. So với run3: giữ nguyên 998 dòng, **+2 câu** mới (không mất câu nào). **Dùng run4 làm lượt nộp thật số 4.**
- Còn bỏ trống trên train (`python tools/train_blanks.py`, không LLM): hàm không ra kết quả nhiều nhất ở `value:revenue` 62, `stock_qty` 29, `share:revenue` 29, `quantity` 24, `debt_paid` 18, `compare:quantity` 13, `rank:quantity` 12, `debt_added` 12, `debt_total` 10. Công nợ phụ thuộc cách từng cửa hàng ghi tiền thu nợ (sổ thu riêng hay ghi trên đơn), cần dò theo định dạng.
- **Kaggle K1 sẵn sàng** (chưa chạy trên Kaggle):
  1. Đã đóng gói: `outputs/kaggle/zaic_code.zip` (0,5 MB) và `outputs/kaggle/zaic_train.zip` (128 MB). Nếu sửa code sau đó thì đóng gói lại: `python tools/kaggle_pack.py`.
  2. Kaggle → Datasets → New Dataset, chế độ **Private**: tải lên 2 file zip, đặt tên ví dụ `zaic-k1`.
  3. Kaggle → Code → New Notebook → File → Import Notebook: chọn `kaggle/k1_qwen14b.ipynb`. Settings: **Accelerator = GPU T4 x2**, **Internet = On** (cần xác minh số điện thoại). Add Input: dataset `zaic-k1`.
  4. **Save Version → Save & Run All.** Dự kiến 3–4 giờ: build llama.cpp, tải 8B và 14B, K3, 14B đọc 3000 câu, chấm.
  5. Xong thì tải `k1_results.zip` ở tab Output, đặt vào `outputs/kaggle/` rồi báo Claude. Dòng cần xem trong `outputs/kaggle_k1/steps.log`: K3 của 8B và 14B, "eval.mapping với plan 14B: …", và "ghép cột theo nghĩa phải gọi LLM mới: 0 lần".
  6. Xong việc thì xoá Dataset (dữ liệu thi).
- **Docker bản nháp:** `docker/Dockerfile`, `docker/predict.sh`, `.dockerignore`. Cách build và chạy thử trong buổi GPU: `docker/README.md`.

## Kết quả nộp 05/11 (chi tiết: HAN_CHE N24)
- Lượt 1–4: tắt cổng câu anh em **0,336**, bỏ xếp hạng **0,276**, bỏ cửa hàng ghép theo nghĩa **0,175**, **run4 0,342**.
- Suy ra:
  - 28 câu cổng câu anh em chặn: 24 đúng / 4 sai → **đã tắt cổng** (`configs/default.json` `twin_threshold: null`);
  - xếp hạng: 7/54 sai; đếm: 6/47 sai;
  - cửa hàng ghép theo nghĩa: 14/169 sai; các cửa hàng còn lại: 13/201 sai.
- **Lượt 5: `outputs/public_run4_twin_off/submission.jsonl`** (run4 + 38 câu cổng chặn, 432 câu trả lời, đã qua `eval.validate`). Ước đoán, nếu tỉ lệ đúng giống 28 câu của lượt 1: khoảng 0,365.
- Việc tiếp theo, theo thứ tự đòn bẩy:
  1. **N27** mapping cho định dạng mọi đường đều trượt: 6/14 cửa hàng public, 360 câu.
  2. Câu xếp hạng / đếm liên quan tới khách (13% sai).
  3. Hàm còn thiếu (công nợ, tồn kho, số lượng).

## Nộp ngày 05/11 (5 lượt), theo thứ tự
Công thức cho mỗi lượt chẩn đoán: số sai của nhóm bị bỏ trống = (số câu − (0,316 − điểm) × 1000) / 2.

| # | File | Đổi gì so với lượt 1 | Đọc kết quả |
|---|---|---|---|
| 1 | `outputs/public_ablation/tat_cong_cau_anh_em.jsonl` | trả lời thêm 28 câu cổng câu anh em chặn | điểm > 0,316 thì tắt cổng (N16) |
| 2 | `outputs/public_ablation/bo_xep_hang.jsonl` | bỏ trống 54 câu `sales.rank` | số sai của xếp hạng; 13 − số đó là của `count_where` |
| 3 | `outputs/public_ablation/bo_map_theo_nghia.jsonl` | bỏ trống 169 câu của 4 cửa hàng map theo nghĩa | số sai của đường theo nghĩa |
| 4 | **`outputs/public_run4/submission.jsonl`** | lượt thật bằng code mới nhất (phiên 4 + N32): −3 câu hoà hạng, −4 câu đổi plan, +31 câu mới so với lượt 1 | điểm − 0,316 = hiệu (đúng − sai)/1000 của phần thay đổi |
| 5 | để dành | | nếu lượt 1 dương (nên tắt cổng): `python tools/replay_run.py outputs/public_run4 --out outputs/public_run4_twin_off --twin-threshold -1`, kiểm `eval.validate` rồi nộp. Nếu không: nộp `outputs/public_run2/submission.jsonl` để tách riêng tác dụng cổng hoà hạng (run2 = lượt 1 trừ đúng 3 câu hoà) |

Ghi mọi điểm vào HAN_CHE N24 và TIEN_DO.

## Đọc kết quả, rồi làm gì
- **Xếp hạng nhiều sai** (lượt 2): rà hàm xếp hạng trên train theo nhóm con lớn nhất ở public (đếm từ log): khách theo số đơn k=1 (10 câu), mặt hàng theo số lượng (14), ngày theo doanh thu (12).
- **Đường theo nghĩa nhiều sai** (lượt 3): rà `transfer_by_meaning` và các chốt R37/R43 trên train. Có thể chặn đường này nếu tỉ lệ sai cao hơn 50%.
- **Cổng câu anh em chặn oan** (lượt 1 dương): đổi `twin_threshold` trong `configs/default.json` thành -1 hoặc bỏ hẳn cổng, đo lại train.

## Việc tiếp theo (sau khi đọc kết quả)
**Lịch đầy đủ 05–16/11, gồm phần dùng Kaggle T4 x2 và buổi thuê RTX 5090: [KE_HOACH_DataMate.md mục 11](KE_HOACH_DataMate.md).**

1. **N27, định dạng mọi đường đều trượt** (biz_123 sqlite POS, biz_124 3 nguồn; 236 câu train). Hướng: từ điển tên cột (tách CamelCase / gạch dưới, bỏ dấu) → cột chuẩn, rút từ mapping của 30 cửa hàng train, đo leave-one-out.
2. Còn khoảng 60 câu train không đọc được câu (plan; 4/25 câu dò là plan sai schema), và khoảng 180 câu "hàm không ra kết quả" ngoài nhóm N29: công nợ (`debt_paid` 19, `debt_added` 12, `debt_total` 10), tồn kho (`stock_qty` 29), số lượng (`quantity` 24 + 13 so sánh + 12 xếp hạng). Phân loại lại bằng `python tools/train_blanks.py` (không cần LLM).
2b. Dựng lại kho đã kiểm chứng (`eval.build_bank`) để các plan mới của N30 có câu anh em, đỡ bị cổng câu anh em chặn (public run3: 38 câu). Lưu ý: kho đổi thì ví dụ trong prompt đổi, phải chạy lại public.
3. Unanswerable nhóm B (cửa hàng không ghi loại thông tin): 44 câu train, chưa bật.
4. Docker (10–12/11, nộp lần 1 ngày 14/11), như BAN_GIAO_PHIEN_3.

## Luật và quyết định cần nhớ
Như BAN_GIAO_PHIEN_3: N22 chỉ dùng train; không logic theo id (`test_no_id_logic` bắt cả comment); nộp chọn loại "SLM / mã nguồn mở"; trưởng nhóm tự commit.

## Lệnh mới
| Việc | Lệnh |
|---|---|
| Chạy lại một lượt bằng code hiện tại, không LLM | `python tools/replay_run.py outputs/public_runN --out outputs/replay/x [--twin-threshold -1]` |
| Đếm lý do bỏ trống của một lượt | `python tools/run_stats.py outputs/public_runN` |

## Git
Commit cuối là `49d8ea7`. Chưa commit: toàn bộ phần R46 của phiên 3 và phiên 4. Lệnh cho trưởng nhóm:
```powershell
cd E:\ZAIC
git add datamate docs tests tools
git commit -m "Phiên 3-4: R46 cổng thuật ngữ, nộp public lần 1 (0.316) + chẩn đoán; N25 cổng hoà hạng, N26 cửa hàng chỉ có đơn, N28 unanswerable kỳ ngoài dữ liệu, N29 bổ sung thuộc tính theo README, tools/replay_run.py, run_stats.py"
git push origin main
```
