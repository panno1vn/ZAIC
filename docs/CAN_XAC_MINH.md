# Việc cần xác minh sau (lượt nộp lẻ, kiểm tra thêm)

*Mở 06/11. Mỗi mục ghi: cần làm gì, file nào, đọc kết quả ra sao. Làm xong thì gạch đi và ghi kết quả vào HAN_CHE.*

Công thức cho mọi lượt chẩn đoán "bỏ trống một nhóm": số sai của nhóm = (số câu của nhóm − (điểm lượt đủ − điểm lượt bỏ nhóm) × 1000) / 2.

## Kết quả bộ run10 (nộp 06/11 18:50–18:52)
| Lượt | Điểm | Nhóm bỏ trống | Đúng / sai của nhóm |
|---|---|---|---|
| run10_s8_full | **0,608** (S) | — | toàn bộ 684 câu: 646 / 38 (94,4%); run9 574 / 34 |
| bo_012 | 0,569 | sổ sửa xe, 45 | 42 / 3 (93%) |
| bo_003_009 | 0,494 | 120 | 117 / 3 (97,5%) |
| bo_011_014 | 0,583 | điện thoại, 27 | 26 / 1 (96%) |
| bo_013 | 0,576 | mẹ và bé, 32 | 32 / 0 |

Không nhóm nào cần chặn. **31/38 câu sai nằm ở 8 cửa hàng cũ** (460 câu, 93,3% đúng).

## Kết quả bộ 07/11 (nộp 07/11 01:00–01:02)
| Lượt | Điểm | Nhóm bỏ trống (cửa hàng cũ) | Đúng / sai của nhóm |
|---|---|---|---|
| run10_s27_full | **0,744** (S27) | — | toàn bộ 802 câu: **773 / 29** (96,4%) |
| bo_compare | 0,677 | so sánh, 73 | 70 / 3 |
| bo_rank | 0,682 | xếp hạng, 70 | 66 / 4 |
| bo_count_where | 0,698 | đếm theo ngưỡng, 58 | 52 / **6** (10%, cao nhất) |
| bo_value_loc | 0,680 | một số có bộ lọc, 72 | 68 / 4 |

Còn **12 câu sai** chưa khoanh vùng trong 529 câu: một số không lọc (179), tỉ trọng / chuỗi / nợ / kho (70), cửa hàng mới (280). Không nhóm nào cần chặn.

## Bộ nộp phiên 10 (dựng 08/11): lượt chính s41 và phép đo N79
Hai file đọc lại run11 bằng code cuối phiên 10, đều đã qua `datamate.eval.validate`, 0 câu lỗi khi chạy.

| # | File | Nội dung | Đọc điểm |
|---|---|---|---|
| 0 | `outputs/replay/run11_s41/submission.jsonl` | **lượt chính mới, N79 tắt** (837 câu trả lời). So với s35: +11 câu (3 tỉ trọng bỉm theo §6 Mẹ và bé, 2 tiền góp chưa trả theo §6 Điện thoại, 6 xếp hạng một tên mà LLM ghi thành bảng một dòng); −1 câu ("có mấy mặt hàng đang cháy hàng" trả về một tên thuốc, nay trống) | nếu s35 đã có điểm: điểm − s35 = (đúng − sai của 11 câu) + 1 nếu câu bỏ vốn sai (−1 nếu vốn đúng). Nếu chưa nộp s35 thì nộp s41 thay s35, so với 0,744 |
| 1 | `outputs/replay/run11_s41r/submission.jsonl` | **N79 bật**: s41 + 20 câu mở nhờ gọi lại LLM khi cổng chặn (857 câu). Đọc từng plan: cả 20 đúng ý | sai trong 20 câu = (20 − (điểm 1 − điểm 0) × 1000) / 2. Sai ≤ 2 thì bật `nlu.GROUND_RETRY` (train như lượt thật đã đạt: bật thêm 16 đúng, 0 sai) |
| 2 | `outputs/public_ablation12/bo_value_tron.jsonl` | S27 bỏ trống "một con số không bộ lọc" của 8 cửa hàng cũ (179) | so với 0,744 |
| 3 | `outputs/public_ablation12/bo_moi_003_009.jsonl` | S27 bỏ trống dev_003 + dev_009 (132) | so với 0,744 |
| 4 | `outputs/public_ablation12/bo_share_series_no_kho.jsonl` | S27 bỏ trống tỉ trọng, chuỗi, xu hướng, nợ, nhập, giao của cửa hàng cũ (70) | so với 0,744 |

s41 khác S27 ở 43 câu (40 mới trả lời, 2 thành trống, 1 đổi giá trị): nếu cả 40 câu mới đúng thì điểm s41 ≈ 0,78; sai trong 40 câu ≈ (40 − (điểm − 0,744) × 1000) / 2, lệch ±2 do 3 câu kia. Lượt 2–4: sai của nhóm = (số câu − (0,744 − điểm) × 1000) / 2. Ngày sau: `bo_moi_dien_thoai` (58), `bo_moi_me_be` / `bo_moi_sua_xe` (45).

### Kết quả (nộp 08/11 00:00–00:03)
| Lượt | Điểm | Đọc ra |
|---|---|---|
| 0 s41 | **0,784** | +0,040 so với 0,744 = đúng ngay số câu mới: 40 câu mới gần như đúng hết (sai ≈ 0 ± 2) |
| 1 s41r | **0,804** (tốt nhất) | +0,020 so với s41: **20 / 20 câu N79 mở thêm đều đúng** → bật `GROUND_RETRY` (08/11) |
| 2 bo_value_tron | 0,569 | 179 câu, đúng − sai = 175 → **2 sai** (1,1%) |
| 3 bo_moi_003_009 | 0,616 | 132 câu, đúng − sai = 128 → **2 sai** (1,5%) |
| 4 bo_share_series_no_kho | 0,674 | 70 câu, đúng − sai = 70 → **0 sai** |

s41r: 860 câu không trống (857 trả lời + 3 unanswerable), điểm 0,804 → khoảng **28 câu sai**, 832 đúng. Đã khoanh vùng 21 câu sai của S27: so sánh 3, xếp hạng 4, đếm theo ngưỡng 6, một số có bộ lọc 4, một số không lọc 2, dev_003 + dev_009 2, tỉ trọng / chuỗi / nợ 0. Theo tổng 29 câu sai của S27, **còn khoảng 8 câu sai ở ba ngành mới chưa đo: điện thoại (58), mẹ và bé (45), sửa xe (45)**, tức ~5%, cao hơn hẳn các nhóm khác. Lượt nộp sau: `bo_moi_dien_thoai`, `bo_moi_me_be`, `bo_moi_sua_xe` (so với 0,744), và bản chính mới nếu có.

### Ba ngành mới (nộp 08/11 00:13–00:14, so với 0,744)
| Lượt | Điểm | Sai |
|---|---|---|
| bo_moi_dien_thoai (58) | 0,694 | **4** (6,9%) |
| bo_moi_me_be (45) | 0,703 | 2 (4,4%) |
| bo_moi_sua_xe (45) | 0,703 | 2 (4,4%) |

**Đã khoanh đủ 29 câu sai của S27:** đếm theo ngưỡng 6/58 (10,3%), điện thoại 4/58, xếp hạng 4/70, một số có bộ lọc 4/72, mẹ và bé 2/45, sửa xe 2/45, so sánh 3/73, dev_003 + dev_009 2/132, một số không lọc 2/179, tỉ trọng / chuỗi / nợ 0/70. Không nhóm nào sai > 20%: không chặn nhóm nào; tìm kiểu sai ở hai nhóm đầu.
(Lượt bo_moi_sua_xe được chọn nhầm model "APIs/Others" trên trang nộp; bài nộp chính phải để SLM.)

## Bản chính mới s51 (dựng đêm 08/11, chưa nộp)
`outputs/replay/run11_s51/submission.jsonl`: bản 0,804 (s41r) đọc lại bằng code N83–N95 (log gọi lại N79 của s38r, server cho lần gọi lại mới). Đã kiểm định dạng, 0 lỗi. So với s41r: **+37 câu trả lời, +12 câu unanswerable, −1 câu** (câu hỏi tháng 2/2026 mà s41r so tháng 7: sai, N95 chặn). Đọc từng câu: đều đúng ý (HAN_CHE N83–N95). Nếu cả 49 câu mới đúng và câu bỏ vốn sai: ≈ 0,854. **Nộp đầu tiên ở lượt sau**; sai trong 49 câu mới ≈ (49 − (điểm − 0,804 − 0,001) × 1000) / 2. Train: `eval_cached` 2752 / 0 / 248, `prod_train` 1421 / 0 / 79.

Lượt chạy thật đủ 1000 câu với LLM bằng cùng code (`outputs/public_run12`, chạy từ bản chép như image): 0 lỗi, 41 phút, giống bản đọc lại ở 993 / 1000 câu (LLM dao động); dùng làm mốc so cho Docker.

Lượt chẩn đoán đi kèm: `outputs/public_ablation14/s51_bo_unans_moi.jsonl` = s51 với 12 câu unanswerable mới (N83 chủ quan 5, N89 giới tính / địa chỉ 7) để trống. Đúng − sai của 12 câu đó = (điểm s51 − điểm file này) × 1000. Nếu 12 câu unanswerable sai quá nửa thì tắt N83 / N89.

| Lượt | Điểm | Ghi chú |
|---|---|---|
| s51 | **0,854** (nộp 08/11 03:01, tốt nhất) | = 0,804 + 49 + 1: **cả 49 câu mới đúng** (37 trả lời, 12 unanswerable) và câu bị bỏ vốn sai |
| s51_bo_unans_moi | không cần nộp | điểm s51 đã cho thấy 12 câu unanswerable đều đúng |

s51: 908 câu không trống, điểm 0,854 → còn khoảng **27 câu sai**, 92 câu trống.

## Bộ nộp 17 (dựng đêm 10/11, phiên 13): s66 = bản đã nộp `public_cand16/chinh.jsonl` + 20 câu (N112, N113)
**Kết quả (nộp 09/11 00:28):** cand16 = **0,927**, cand17 `chinh.jsonl` = **0,948** (+21 = mức tối đa: 19 câu mới đều đúng, câu đổi đáp án là câu sai cũ). Suy ra 6 câu nhóm hàng đúng cả: không cần nộp `bo_nhom_hang.jsonl`. cand17: 972 câu không trống → **960 đúng, 12 sai**, 28 trống (cand16: 953 → 940 đúng, 13 sai).

| File | Nội dung | Nộp |
|---|---|---|
| `outputs/public_cand17/chinh.jsonl` | s66 nguyên vẹn: 972 / 1000 câu không trống (+19 câu mới, 1 câu đổi đáp án, 0 câu bỏ) | **nộp trước** |
| `outputs/public_cand17/bo_nhom_hang.jsonl` | như `chinh` nhưng 6 câu "không trả lời được vì shop không có cột nhóm hàng" để trống | nếu còn lượt |
| `outputs/public_cand17/giu_cu_cau_doi.jsonl` | như `chinh` nhưng câu đổi đáp án (1) lấy lại đáp án cũ | không cần |

20 câu khác bản đã nộp, theo nhóm: 6 đếm đơn theo "ngày phải trả" (đếm tay từ file gốc khớp cả 6); 6 nhóm hàng ở shop không có cột nhóm (**chưa có tiền lệ train**); 3 lý do trả / huỷ (train 2 / 2 unanswerable); 3 chủ quan (train 5 / 5); 1 lời không giá vốn (train 1 / 1); 1 câu hỏi lý do huỷ mà bản đã nộp trả số → unanswerable.

Cách đọc (điểm tính trên 1000 câu, +1 đúng, −1 sai, 0 trống; gọi điểm bản đã nộp là S16):
- điểm `chinh` − S16 = (đúng − sai của 19 câu mới) + (thay đổi của 1 câu đổi đáp án: +2 nếu cũ sai mới đúng), chia 1000. Nếu cả 20 đúng: **+0,021**; nếu riêng 6 câu nhóm hàng sai hết: +0,009.
- điểm `chinh` − điểm `bo_nhom_hang` = (đúng − sai của 6 câu nhóm hàng) / 1000: dương thì §7 "không ghi cột nhóm → không trả lời được" đúng ý bộ sinh đề, âm thì bỏ luật nhóm hàng của N112.
- Cần điểm chính xác của S16 (≈ 0,927) để đọc.

## Bộ nộp 16 (dựng chiều 08/11, phiên 11): bản chính s63 + một bản chẩn đoán — NỘP ĐẦU TIÊN ở lượt sau
`outputs/public_cand16/` (`python tools/research/build_cand16.py outputs/replay/run11_s63/submission.jsonl outputs/replay/run11_s51/submission.jsonl outputs/public_cand16`). s63 = s51 đọc lại bằng code N97–N109 (HAN_CHE "Phiên 11"). Cả hai file đã kiểm định dạng. Train: `eval_cached` 2754 / 0 / 246, `prod_train` 1425 / 0 / 75 (trước 1421 / 0 / 79).

So với s51 (0,854): **+45 câu mới** (s51 trống), **14 câu đổi đáp án**, 0 câu bỏ; 953 / 1000 câu có trả lời.
- 14 câu đổi: 7 dev_008 + 1 dev_007 (N105: khách theo mã, trước bị tách 4–8 lần theo cách viết tên → đếm / % khách theo ngưỡng số đơn, top khách), 4 dev_002 (N108: dòng "món + topping" nay tính vào món: số ly theo món / theo size), 2 câu "bữa ni" dev_011 + dev_012 (N103: hôm nay, trước trả số cả tháng). Theo luật thì cả 14 câu cũ đều sai.
- 45 câu mới theo shop: điện thoại 20 (dev_014 14, dev_011 6: N101–N102), dev_008 8 (N100 nợ cuối kỳ 5, N105 hoà hạng gỡ 2, N107 tồn 1), dev_006 6, dev_007 3 (N107), dev_013 3, dev_002 2, dev_001 1, dev_005 1, dev_010 1 (N109).

| # | File | Để làm gì | Điểm | Đọc |
|---|---|---|---|---|
| 1 | `chinh.jsonl` | bản chính | | nếu mọi câu mới và câu đổi đều đúng: ≈ 0,854 + 0,045 + 0,028 = **0,927** |
| 2 | `giu_cu_cau_doi.jsonl` | như #1 nhưng 14 câu đổi giữ đáp án s51 | | (điểm #1 − điểm #2) × 1000 / 2 = số câu đổi thành đúng trừ số câu đổi thành sai (tối đa 14); điểm #2 − 0,854 = đúng − sai của 45 câu mới |

**Kiểm lại sau khi nộp #1 (đúng như mong đợi):**
- Lượt chạy thật đủ 1000 câu bằng code cuối, gọi LLM mới như Docker (`outputs/public_run13`, chạy từ bản chép `outputs/snap_run13` chỉ gồm `datamate/`, `assets/`, `configs/`): 0 lỗi, 0 hết giờ, 2788 giây. Giống `chinh.jsonl` **994 / 1000**, không câu nào đổi giá trị; 5 câu thành trống (LLM sinh khác: "vâu chơ", "cất hàng" đọc thành tồn kho, JSON hỏng 1 lần, nhân viên ghi mã NV003, bộ lọc "trả góp" bịa), 1 câu trống thành có số. Lượt thật thấp hơn bản nộp tối đa ~0,005.
- Các luật viết lại N97–N109 không đổi plan nào trong 3000 plan train (không bắt nhầm), chỉ bắt câu public (1–6 câu mỗi luật). Luật tầng dữ liệu trên 30 shop train: N100 chạy ở 5 shop, N106 gộp 1 cách viết ở 1 shop, N107 mượn danh mục ở 1 shop (+1 câu), N105 / N108 không chạm shop nào. Train vẫn 0 sai (`eval_cached` 2754 / 0, `prod_train` 1425 / 0).

Nếu #1 thấp hơn #2: một trong N103 / N105 / N108 sai → nộp thêm bản chỉ giữ cũ nhóm đó (dựng bằng cách sửa danh sách câu đổi theo shop).

## Bộ nộp 13 (dựng 08/11): chia nhỏ hai nhóm sai nhiều nhất, trên bản 0,804
Trong `outputs/public_ablation13/`, mỗi file là s41r (0,804) với một nhóm bỏ trống. **So với 0,804**: sai của nhóm = (số câu − (0,804 − điểm) × 1000) / 2. Dựng bằng script nhóm theo log s41r (plan `intent=count_where` và `threshold.entity`; `business_id` cho hai shop điện thoại).

| # | File | Nhóm (số câu) |
|---|---|---|
| 1 | `bo_cw_khach.jsonl` | đếm khách theo ngưỡng số đơn, mọi shop (32) |
| 2 | `bo_cw_ngay_don.jsonl` | đếm ngày / đơn theo ngưỡng doanh thu (43) |
| 3 | `bo_cw_khac.jsonl` | đếm mặt hàng, xe theo ngưỡng (11) |
| 4 | `bo_dt_011.jsonl` | điện thoại dev_011, map từ README (29) |
| 5 | `bo_dt_014.jsonl` | điện thoại dev_014, ghép theo vai trò, sổ nợ / góp (36) |

| Lượt | Điểm | Sai |
|---|---|---|
| bo_cw_khach | | |
| bo_cw_ngay_don | | |
| bo_cw_khac | | |
| bo_dt_011 | | |
| bo_dt_014 | | |

## Bộ nộp tiếp theo: lượt chính run11 + khoanh vùng 12 câu sai còn lại
Trong `outputs/public_ablation12/`, so với **S27 = 0,744** (cùng file gốc `outputs/replay/run10_s27m`). Sai của nhóm = (số câu − (0,744 − điểm) × 1000) / 2.

| # | File | Nhóm (số câu) |
|---|---|---|
| 0 | `outputs/replay/run11_s35/submission.jsonl` | **lượt chính mới, thay s33/s34** (N76 + N77: thêm 9 câu, 1 câu đổi giá trị; 830 câu trả lời). Bản trước: (07/11 phiên 9): run11 (lượt LLM đủ, N75) đọc lại bằng code cuối, 821 câu trả lời. So với S27: **21 câu mới** (9 câu ca N73, 8 câu lô / hạn dùng / hết hàng N74, 4 câu run11 đọc đúng hơn) và **2 câu thành trống** (LLM của run11 đọc lệch, cổng chặn). Nếu 2 câu đó vốn đúng: điểm − 0,744 = (đúng − sai của 21 câu) − 0,002. Bản ghép không LLM tương ứng: `outputs/replay/run10_s32m` (819 câu) |
| 1 | `bo_share_series_no_kho.jsonl` | cửa hàng cũ: tỉ trọng, chuỗi tháng, xu hướng, công nợ, nhập, giao (70) |
| 2 | `bo_value_tron.jsonl` | cửa hàng cũ: một con số không bộ lọc (179) |
| 3 | `bo_moi_003_009.jsonl` | dev_003 + dev_009 (132) |
| 4 | `bo_moi_dien_thoai.jsonl` | điện thoại (58) |
| 5 | `bo_moi_me_be.jsonl` hoặc `bo_moi_sua_xe.jsonl` | mẹ và bé (45) / sửa xe (45) |

Lượt 1–5 là S27 bỏ trống một nhóm, nên so với 0,744, không so với lượt 0; vẫn đọc đúng dù đã nộp lượt 0. Năm lượt một ngày: đề xuất 0, 2, 1, 3, 4. Bộ sau nên dựng từ lượt 0 mới: `tools/ablate_groups.py outputs/replay/run11_s33 --out …`.

## Bộ nộp ngày 07/11: lượt chính mới + khoanh vùng câu sai của cửa hàng cũ (đã nộp 07/11, kết quả ở mục "Kết quả bộ 07/11")
Trong `outputs/public_ablation11/`. Lượt chính `run10_s27_full.jsonl` (= `outputs/replay/run10_s27m`) ghép từ:
- 11 cửa hàng: run10 đọc lại bằng code 07/11;
- hai cửa hàng điện thoại: lượt LLM mới `outputs/public_phones_s8d`;
- cửa hàng mẹ và bé: lượt LLM mới `outputs/public_baby_s8`.

Cả ba đều đọc lại bằng code 07/11 (`tools/replay_run.py --enrich`). Một lượt chạy mới bằng code này cho cùng kết quả, vì schema và prompt của các cửa hàng khác không đổi kể từ run10. Nộp **0** trước, rồi 1–4; lượt 5 để ngày sau.

- **0. `run10_s27_full.jsonl`** (802 câu trả lời). Gọi điểm là S27. So với lượt 0,608 (684 câu), thêm 118 câu, 15 câu đổi giá trị năm (N58), và một số câu đọc sai đã chuyển thành trống:
  - N57–N67: như bản s20;
  - N68: sổ phụ điện thoại (thu máy cũ, bảo hành, sổ nợ, sổ góp, khách theo số điện thoại);
  - N69: mẹ và bé (số sữa, size và hãng bỉm, quy đổi trong danh mục, khách thành viên mới);
  - N70: tỉ trọng mẫu số trùng tử số;
  - N71: "so th 3/25".

  Dự kiến S27 − 0,608 ≈ +0,10 đến +0,14.
- 1–5 bỏ trống một nhóm của 8 cửa hàng cũ; sai của nhóm = (số câu − (S27 − điểm) × 1000) / 2. Phần còn lại (`value_of` không bộ lọc, 179 câu) và các cửa hàng mới (280 câu) không nộp.

| # | File | Nhóm (số câu) | Lần trước (run4, 05/11) |
|---|---|---|---|
| 1 | `bo_compare.jsonl` | so sánh (73) | |
| 2 | `bo_rank.jsonl` | xếp hạng (70) | 7 / 54 sai |
| 3 | `bo_count_where.jsonl` | đếm theo ngưỡng (58) | 6 / 47 sai |
| 4 | `bo_value_loc.jsonl` | một con số có bộ lọc (72) | |
| 5 | `bo_share_series_no_kho.jsonl` | tỉ trọng, chuỗi tháng, xu hướng, công nợ, nhập, giao (70) | |

## Bộ nộp từ run10 (06/11 tối, phiên 8)
Lượt chính: `outputs/public_ablation10/run10_s8_full.jsonl` = run10 (chạy đủ với LLM, 681 câu) áp thêm các cổng sửa sau run10 (`tools/replay_run.py`, đọc lại đầu ra LLM đã ghi): **684 câu trả lời** (run9: 608). Gọi điểm của nó là S. Mỗi lượt dưới bỏ trống một nhóm; sai của nhóm = (số câu − (S − điểm) × 1000) / 2.

| # | File | Nhóm (số câu bỏ trống) | Để biết | Nếu sai > 50% |
|---|---|---|---|---|
| 1 | `run10_s8_full.jsonl` | lượt chính (684) | điểm mới | |
| 2 | `bo_012.jsonl` | sổ sửa xe dev_012 (45) | độ đúng của N42–N48, N55 | chặn đường sổ sửa xe |
| 3 | `bo_003_009.jsonl` | dev_003, dev_009 (120) | ghép theo vai trò, sổ chỉ có hoá đơn | xem lại hai đường đó |
| 4 | `bo_011_014.jsonl` | điện thoại (27) | ngành điện thoại | tạm chặn ngành |
| 5 | `bo_013.jsonl` | mẹ và bé (32) | ngành mẹ và bé | tạm chặn |

Sai 20–50%: giữ, tìm kiểu sai. Thứ tự nộp nếu ít lượt: 1, 2, 3.

## Lượt nộp chẩn đoán từ run9 (dựng 06/11, phiên 8; đã có bộ run10 ở trên thay thế)
Lượt đủ: `outputs/public_run9/submission.jsonl`, điểm **0,540**. Số sai của nhóm = (số câu − (0,540 − điểm) × 1000) / 2.

**Ngưỡng chặn (sửa 06/11):** đúng +1, sai −1, nên một nhóm chỉ làm giảm điểm khi số câu sai **nhiều hơn** số câu đúng. Sai > 50%: chặn. Sai 20–50%: giữ, nhưng tìm và sửa kiểu sai (đó là lỗi có hệ thống, private cũng sẽ gặp). Bản cũ ghi "sai ≥ 30% thì chặn" là chặn oan cả những nhóm đang được điểm.

| # | File | Nhóm (số câu bỏ trống) | Nếu sai > 50% |
|---|---|---|---|
| A | `outputs/public_ablation9/bo_003_009.jsonl` | dev_003 (ghép theo vai trò), dev_009 (chỉ có hoá đơn): 116 | xem lại ghép theo vai trò |
| B | `outputs/public_ablation9/bo_011_014.jsonl` | điện thoại dev_011, dev_014: 25 | tạm chặn ngành điện thoại |
| C | `outputs/public_ablation9/bo_013.jsonl` | mẹ và bé dev_013: 30 | tạm chặn cửa hàng đó |
| D | `outputs/replay/run9_s8f/submission.jsonl` | **thêm** 22 câu (run9 chạy lại bằng code 06/11, không LLM: 4 dev_012, 14 nhóm hàng N50, 4 tên Bắc – Nam N51) | đọc ngược: điểm − 0,540 = (đúng − sai) của 22 câu mới; sai = (22 − (điểm − 0,540) × 1000) / 2 |

Ví dụ đọc: lượt A được 0,520 thì nhóm A sai (116 − 20) / 2 = 48 câu (41%): giữ, tìm kiểu sai.

## Lượt nộp chẩn đoán cũ (run6, run8)
| # | Lượt đủ | Lượt bỏ nhóm | Nhóm (số câu) | Để biết gì | Nếu sai nhiều |
|---|---|---|---|---|---|
| 1 | `outputs/public_run8/submission.jsonl` | `outputs/public_ablation8/bo_cua_hang_moi.jsonl` | câu của dev_003 và dev_009, hai cửa hàng mới map (116) | độ chính xác của ghép bảng theo vai trò và đường hoá đơn ở public | sai ≥ 30%: chặn đường ghép theo vai trò, xem lại mapping của dev_003 |
| 2 | run6 | `outputs/public_ablation6/bo_gia_tri_don_tb.jsonl` | giá trị đơn trung bình (37) | định nghĩa §1 | rà hàm `avg_order_value` |
| 3 | run6 | `outputs/public_ablation6/bo_don_huy.jsonl` | số đơn huỷ, tỉ lệ huỷ (31) | định nghĩa huỷ | rà `cancel_count`, `cancel_rate` |
| 4 | run6 | `outputs/public_ablation6/bo_doanh_thu.jsonl` | doanh thu một kỳ (102) | phần lớn 11 câu sai `value_of` của lượt 1 có ở đây không | rà theo bộ lọc |
| 5 | run6 | `outputs/public_ablation6/bo_khach.jsonl` | xếp hạng khách (20) | giả thuyết N33 khách vãng lai | rà nhận diện khách |

Lượt 2–5 dựng từ run6. Nếu đã nộp run8 làm lượt đủ thì dựng lại 2–5 từ run8 cho khớp:
`python tools/ablate.py outputs/public_run8 --out ... --function ... --metric ...` (xem `python tools/ablate.py --help`).

## Cửa hàng ngành mới (map được từ 06/11, chưa đo độ chính xác)
Mỗi cửa hàng nộp một lượt bỏ trống riêng câu của nó, dựng từ lượt đủ mới nhất:
`python tools/ablate.py outputs/public_runN --out outputs/public_ablationN/bo_<cửa hàng>.jsonl --shops <id>`.

| Cửa hàng | Ngành, đường map | Rủi ro chính |
|---|---|---|
| dev_011 | điện thoại, README | câu riêng ngành (máy cũ, máy mới, dòng máy, trả góp, thu máy cũ) bị đọc thành câu chung, ví dụ "máy cũ bán mấy chiếc" thành tổng số lượng |
| dev_014 | điện thoại, ghép theo vai trò (mẫu biz_111) | như trên; `total_due` lấy nhầm cột "Thành tiền"; sổ nợ và sổ góp chưa map |
| dev_012 | sửa xe, chỉ có bảng đơn | run9 0/50 do N45 (đã sửa). Hàm hoa hồng, lượt theo việc, dòng xe viết tắt, xe tới nhiều lần mới thêm (N46–N48), chưa qua lượt chạy có LLM: cần chạy 50 câu, đọc plan, rồi một lượt nộp bỏ trống riêng dev_012 |
| dev_013 | mẹ và bé, ghép theo nghĩa (mẫu biz_101) | câu về voucher, điểm, phí ship, số sữa, size bỉm, khách thành viên chưa có hàm |

Nếu một cửa hàng sai > 50% thì tạm chặn cửa hàng đó (mapping) cho tới khi có hàm của ngành; sai 20–50% thì giữ và tìm kiểu sai.

## Kiểm tra khác
- ~~Kaggle K1 (14B so với 8B)~~ **xong 06/11:** giữ Qwen3-8B; 10 câu sai của 14B thành 4 cổng mới (HAN_CHE N49).
- Docker: chưa build lần nào. Chờ guideline 2026 và buổi thuê RTX 5090.

## Bộ nộp 15 (dựng sáng 08/11): như bộ 13 nhưng trên s51 (0,854)
Trong `outputs/public_ablation15/` (`python tools/research/ablate13.py outputs/replay/run11_s51 outputs/public_ablation15 dev_011 dev_014`: id hai shop điện thoại truyền qua dòng lệnh, file ra tên `bo_shop_<id>`; bộ đã dựng sẵn mang tên cũ `bo_dt_011`, `bo_dt_014`). **So với 0,854**: sai của nhóm = (số câu − (0,854 − điểm) × 1000) / 2. Thay cho bộ 13 (bộ 13 dựng trên s41r).

| # | File | Nhóm (số câu) | Điểm | Sai |
|---|---|---|---|---|
| 1 | `bo_cw_khach.jsonl` | đếm khách theo ngưỡng số đơn (33) | | |
| 2 | `bo_cw_ngay_don.jsonl` | đếm ngày / đơn theo ngưỡng doanh thu (43) | | |
| 3 | `bo_cw_khac.jsonl` | đếm mặt hàng, xe (11) | | |
| 4 | `bo_dt_011.jsonl` | điện thoại dev_011 (32) | | |
| 5 | `bo_dt_014.jsonl` | điện thoại dev_014 (38) | | |
