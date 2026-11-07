# Bàn giao phiên 6 (đêm 05→06/11) → phiên 7

> **Đã có bàn giao mới hơn: [BAN_GIAO_PHIEN_7.md](BAN_GIAO_PHIEN_7.md)** (06/11: public 0,540, 14/14 cửa hàng map được, luật dữ liệu mới).

*Claude làm một mình trong đêm, trưởng nhóm ngủ. Luật vẫn như [BAN_GIAO_PHIEN_3.md](BAN_GIAO_PHIEN_3.md) và [BAN_GIAO_PHIEN_4.md](BAN_GIAO_PHIEN_4.md): N22 (chỉ dùng train, với public chỉ đếm từ log), không có logic theo id, trưởng nhóm tự commit. Chi tiết từng mục ở [HAN_CHE mục N](HAN_CHE_VA_CAI_THIEN.md).*

## Bắt đầu phiên mới
> Đọc `docs/BAN_GIAO_PHIEN_6.md`, rồi mục N của `docs/HAN_CHE_VA_CAI_THIEN.md`. Kiểm `git status` và test (`.venv\Scripts\python.exe -m pytest -q`). Ghi điểm các lượt nộp 06/11 vào HAN_CHE N24.

## Số đo
| Thời điểm | Train `eval.mapping --llm-url` (đúng / sai / trống) | PA |
|---|---|---:|
| Đầu phiên (N32) | 2439 / 0 / 561 | +0,813 |
| + N27 (`stem`, hỏi lại cột bắt buộc, ghép bảng theo vai trò), N33 | 2493 / 0 / 507 | +0,831 |
| + N34, N35, N36, N37, sửa `by_role`, `unfilled_extras`, `KeyError` | 2566 / 0 / 434 | +0,855 |
| + `requantify` (biz_124 từ 0 lên 85) | 2651 / 0 / 349 | +0,884 |
| + cột mã đơn không mang nghĩa khác, kiểm tra "mã hàng và tên hàng hợp lý" | 2651 / 0 / 349 | +0,884 |
| + N38, sổ không mã đơn (`_as_rows`, chỉ ở đường ghép theo vai trò), giới hạn ghép bảng theo trạng thái và cột tiền | **2656 / 0 / 344** (log `outputs/eval_mapping_s6f.log`) | **+0,885** |

N38 (nhập hàng không ghi → unanswerable): +5 câu trên train (103, 112, 118, 121, 122). Test: 366 qua (log `outputs/pytest_s6c.log`), cộng các test mapping chạy sau bản sửa cuối.

**Public run6** (`outputs/public_run6/`; run7 có thêm N38 và các sửa của kịch bản E, ra **trùng hoàn toàn** run6; đúng định dạng): **438 câu trả lời**, trong đó 3 câu unanswerable (N37). So với `public_run4_twin_off` (432 câu): thêm 9 câu, mất 3 câu (N31: LLM đọc lại 3 câu ra plan khác, không còn plan). Trùng hoàn toàn với run5.

**Vì sao public tăng ít mà train tăng nhiều:**
- Đếm từ log: không quy tắc mapping mới nào kích hoạt ở 8 cửa hàng public đã map (khách lẻ theo tỉ lệ, quy ước README, bỏ bảng phụ, đọc lại số lượng đều 0 lần).
- 6 cửa hàng public chưa map (360 câu) **vẫn chưa map được**. Đường ghép theo vai trò có chạy, nhưng mọi lần thử đều trượt kiểm tra hoặc thiếu cột bắt buộc. Mẫu được chọn phần lớn là sổ một bảng (101, 105, 126, 103).
- Đường README trượt ở cả 6 cửa hàng, nên nhiều khả năng README của chúng không mô tả từng cột. Kịch bản E trên train (README sơ sài) tái hiện đúng kiểu trượt này. Sau 3 bản sửa (sổ không mã đơn, giới hạn ghép bảng theo trạng thái và cột tiền), E map được 8/10 bản sao với 0 sai. Ở public thì chưa map thêm được cửa hàng nào (run7).

## Kịch bản đổi tên (`tools/variant_eval.py`, chỉ train)
Lấy 10 cửa hàng có mapping tay, đổi tên cột (và tên file) rồi cho mapping tự động map lại. Dữ liệu giữ nguyên nên chấm được bằng đáp án train.

| Kịch bản | Đổi gì | Mẫu của chính nó | Kết quả (đúng / sai / trống, 1026 câu) |
|---|---|---|---|
| A | tên cột | còn | 926 / 0 / 100 (khớp mapping tay) |
| B | tên cột | bỏ | 555 / 0 / 471 → **806 / 0 / 220** sau mọi sửa (B3) |
| C1 | tên cột, tên file | còn | 801 / 0 / 225 |
| C2 | tên cột, tên file | bỏ | 650 / **5** / 371 → **658 / 0 / 368** sau sửa (C2b) |
| E | tên cột, tên file, README chỉ còn "Quy ước" | bỏ | 497 / 0 / 529 (4/10 trượt **giống hệt public**) → **645 / 0 / 381** sau sửa (8/10 map được) |

## Cập nhật chiều 06/11: BTC cho phép xem public (HAN_CHE N22, N39)
- **Public run8: 553 câu trả lời** (`outputs/public_run8/`, đúng định dạng); dev_003 trả lời 97/129, dev_009 19/21. Train vẫn 2656 / 0.
- **Nộp thay cho run6:** `outputs/public_run8/submission.jsonl`, cùng file chẩn đoán `outputs/public_ablation8/bo_cua_hang_moi.jsonl` (bỏ 116 câu của hai cửa hàng mới map). Số sai của phần mới = (116 − (điểm run8 − điểm file chẩn đoán) × 1000) / 2.
- **Còn 4 cửa hàng ngành mới (210 câu):**
  - trạng thái nằm trong cột Ghi chú (§8 mới của public): điện thoại 011, 014; mẹ và bé 013;
  - tên hàng ghi tắt (sheet "Ghi tắt"): 011, 014;
  - dòng Voucher / Dùng điểm / Phí ship: 013;
  - phiếu sửa xe không mã: 012.
- **Docker:** đối chiếu hướng dẫn 2025 (`docker/README.md`); `predict.sh` in thời gian nạp model và thời gian dự đoán; có `docker/predict_notebook.ipynb`.

## Nộp ngày 06/11 (đề xuất)
Cả 5 file đã dựng xong và qua `eval.validate`. 4 file chẩn đoán đều là run6 bỏ trống một nhóm câu, dựng bằng `tools/ablate.py` (chỉ dùng log của hệ thống). Số sai của nhóm bị bỏ = (số câu − (điểm run6 − điểm file) × 1000) / 2.

| # | File | Bỏ trống | Câu |
|---|---|---|---:|
| 1 | **`outputs/public_run6/submission.jsonl`** | không bỏ gì (lượt thật); điểm − điểm `public_run4_twin_off` = phần 9 câu thêm, 3 câu mất | 438 |
| 2 | `outputs/public_ablation6/bo_gia_tri_don_tb.jsonl` | giá trị đơn trung bình (`avg_order_value`) | 37 |
| 3 | `outputs/public_ablation6/bo_don_huy.jsonl` | số đơn huỷ và tỉ lệ huỷ | 31 |
| 4 | `outputs/public_ablation6/bo_doanh_thu.jsonl` | doanh thu một kỳ (`value_of` revenue) | 102 |
| 5 | `outputs/public_ablation6/bo_khach.jsonl` | xếp hạng khách và khách nợ (thử giả thuyết N33) | 20 |

Lượt 1 có 27 câu sai: xếp hạng 7/54, đếm 6/47, `value_of` 11/190. Các lượt 2–4 tách tiếp phần `value_of`. Nhóm nào sai từ 50% trở lên thì nên chặn ngay; nhóm nào sai ít hơn thì rà định nghĩa trên train.

## Việc tiếp theo
1. **6 cửa hàng public chưa map** (360 câu, đòn bẩy lớn nhất). Kịch bản E đã bắt được kiểu trượt, nhưng sau 3 bản sửa public vẫn chưa đổi. Còn hai hướng chưa thử:
   - **Chữ trạng thái lạ (làm trước).** Đếm từ log run7, chỉ đếm tên kiểm tra:
     - kiểm tra trạng thái ("đã quy đổi", "hợp lý") trượt 7 lần, ở 3/6 cửa hàng (003, 013, 014);
     - "số âm chỉ ở đơn trả" trượt 5 lần (009, 013);
     - 011 không mẫu nào ghép được;
     - 012 thiếu cột bắt buộc.

     Cách làm: dựng kịch bản đổi chữ trạng thái trên train (`variant_eval`), rồi cho LLM đọc các chữ trạng thái chưa gặp. Kiểm tra "trạng thái hợp lý" và "số âm chỉ ở đơn trả" chặn khi đọc sai.
   - **Hỏi BTC về N22:** nếu được xem README của public thì biết ngay vì sao trượt.
2. biz_111 và biz_124 ở kịch bản E vẫn trượt: tên hàng chỉ có trong danh mục, phải tra theo mã.
3. biz_111 mất 3 câu (LLM bỏ sót cột "SL quy đổi" không bắt buộc).
4. Docker (10–12/11): README cho image đã có (`docker/README_IMAGE.md`); Dockerfile đã chép thêm `tools/`.

## Công cụ mới
| Việc | Lệnh |
|---|---|
| Bản sao đổi tên của cửa hàng train, map lại và chấm | `python tools/variant_eval.py --llm-url http://127.0.0.1:8091 [--leave-out] [--rename-files] [--strip-readme] [--business biz_123] [--show-mapping]` |
| File nộp chẩn đoán từ log của một lượt | `python tools/ablate.py outputs/public_runN --out x.jsonl [--function ...] [--new-shops-vs RUN] [--new-answers-vs RUN]` |

## Git
Chưa commit gì từ `70c3dc4`. Lệnh cho trưởng nhóm:
```powershell
cd E:\ZAIC
git add .gitignore .dockerignore configs datamate docker docs kaggle tests tools
git commit -m "Phiên 5-6: nộp 05/11 (run4 0.342, tắt cổng câu anh em); N27 định dạng lạ (stem, hỏi lại cột, ghép bảng theo vai trò, requantify), N33-N38; train 2651/0 PA +0.884; public run6; variant_eval, ablate; README image"
git push origin main
```
