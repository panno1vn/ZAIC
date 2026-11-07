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

## Bộ nộp tiếp theo: lượt chính run11 + khoanh vùng 12 câu sai còn lại
Trong `outputs/public_ablation12/`, so với **S27 = 0,744** (cùng file gốc `outputs/replay/run10_s27m`). Sai của nhóm = (số câu − (0,744 − điểm) × 1000) / 2.

| # | File | Nhóm (số câu) |
|---|---|---|
| 0 | `outputs/replay/run11_s33/submission.jsonl` | **lượt chính mới** (07/11 phiên 9): run11 (lượt LLM đủ, N75) đọc lại bằng code cuối, 821 câu trả lời. So với S27: **21 câu mới** (9 câu ca N73, 8 câu lô / hạn dùng / hết hàng N74, 4 câu run11 đọc đúng hơn) và **2 câu thành trống** (LLM của run11 đọc lệch, cổng chặn). Nếu 2 câu đó vốn đúng: điểm − 0,744 = (đúng − sai của 21 câu) − 0,002. Bản ghép không LLM tương ứng: `outputs/replay/run10_s32m` (819 câu) |
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
`python tools/ablate.py outputs/public_run8 --out ... --function ... --metric ...` (lệnh ở `BAN_GIAO_PHIEN_6.md`).

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
