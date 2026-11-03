# Bàn giao phiên 2 → phiên 3

*Viết cuối phiên 2 với Claude. Ngày hệ thống: 03/11/2026. Lịch thật đi trước kế hoạch: các ngày 03/11–05/11 ghi trong tài liệu là ngày theo kế hoạch.*

## Bắt đầu phiên mới thế nào
Dán vào phiên chat mới:

> Đọc `docs/BAN_GIAO_PHIEN_2.md`, rồi `docs/TIEN_DO.md` và mục 9–10 của `docs/KE_HOACH_DataMate.md`. Kiểm `git status` và `python -m pytest`. Sau đó làm việc T1 trong mục 10 của kế hoạch.

Trước khi chạy việc cần LLM (T1 bước 4, T3, T4, T5), leader mở llama-server trong một cửa sổ riêng:
```powershell
cd E:\llm\llama-b12064
.\llama-server.exe -m E:\llm\models\Qwen3-8B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --parallel 1 --host 127.0.0.1 --port 8091
```
Kiểm tra: `curl http://127.0.0.1:8091/health` trả `{"status":"ok"}`. Cổng 8080 từng không bind được trên laptop, nên luôn dùng 8091.

## Bối cảnh rất ngắn
- **Cuộc thi:** Zalo AI Challenge 2026, đề **DataMate**: trả lời câu hỏi tiếng Việt (không dấu, viết tắt) trên dữ liệu bán hàng của cửa hàng nhỏ (csv / xlsx / sqlite), mỗi câu một dòng JSON có kiểu.
- **Chấm:** đúng +1, sai −1, bỏ trống 0. Khớp tuyệt đối.
- **Luật quan trọng:**
  - mọi model cộng lại ≤ 15B tham số, giấy phép OSI;
  - chạy offline, tối đa 6 giờ;
  - không logic theo id, không làm tay trên dữ liệu test;
  - BTC chạy lại Docker, phải lệch ≤ 0,03 PA.
- **Mốc:** đóng băng **23:59 T2 16/11/2026** (nộp Docker qua Google Drive, tối đa 2 lần). Private phát 20/11, nộp trước 23/11.
- **Dữ liệu:** train 3000 câu / 30 cửa hàng (có đáp án); public 1000 câu / 14 cửa hàng. Bộ private có ngành mới.
- **Bảng xếp hạng public:** đội tốt nhất khoảng **0,9** (leader cho biết, phiên 2).

## Người dùng và cách làm việc
- Leader nhóm 5 người, nhưng **từ 02/11 tự làm toàn bộ, 14 giờ/ngày**. Lịch ở mục 9 của kế hoạch.
- Trả lời bằng tiếng Việt, giải thích căn cứ của từng quyết định (dòng rulebook, số đo, luật thi).
- Lỗi nghi ngờ phải chạy thử để xác nhận, rồi mới sửa. Mỗi lỗi sửa có test hồi quy và được ghi vào `docs/HAN_CHE_VA_CAI_THIEN.md`.
- **Không commit:** đưa lệnh `git` để leader tự commit.
- **Mạng:** laptop có lúc chỉ có 4G. Hỏi trước khi tải file trên ~50 MB. Upload image Docker (10–20 GB) phải làm trên máy GPU thuê, đẩy thẳng lên Google Drive bằng `rclone` (mục H20).
- **Quyền:** máy chấm quyền chặn Claude tự tải và chạy file `.exe`. llama.cpp do leader tự tải và tự chạy server.

## Phiên 2 đã làm gì (theo thứ tự)
1. **Review lần 2** (R15–R21):
   - kiểu numpy làm dừng cả lượt chạy;
   - NaN lọt vào file nộp;
   - registry ghi đè im lặng → khoá có `entity`, hàm khai báo `filters`;
   - ô bắt buộc trống vẫn qua kiểm tra;
   - sqlite NULL thành `"None"`;
   - baseline đọc nhầm câu "nào / nhất";
   - **trường lạ bị bỏ âm thầm** → `extra="forbid"`.
2. **K2** (thử sức hợp đồng trên 99 câu) → **hợp đồng v1.1**: mã cho bộ lọc ca / thứ / trạng thái / kê đơn, `list_spec.count`, `count_where` không cần `measures`, khoảng hạn dùng ghi bằng ngày, Tết không ghi năm, `STOCK_METRICS`.
3. **Lịch làm một mình**, mục 9 của kế hoạch.
4. **G1 loader** (03/11): đọc mọi sheet xlsx bằng `python-calamine`, dò header 1–2 dòng, bỏ dòng tiêu đề / dòng tổng / dòng chú thích cuối sheet, `year_hint`, kiểu tiền lạ (R22), đoán kiểu cột. 44/44 cửa hàng đọc không lỗi.
5. **G2 phần 1** (04/11): đủ 8 phép biến đổi, `sources` dạng glob, cột phụ `_source` / `_row` / `_year`, điền xuống theo §8 trước khi bỏ dòng trùng, `base_qty` tự suy từ bảng quy đổi, ngày đơn = dòng sớm nhất (R24), hằng số được parse.
6. **Mapping tay 8 cửa hàng train**, chọn theo độ phủ kiểu dữ liệu: 8 cửa hàng phủ 29/30 kiểu tìm thấy ở 30 cửa hàng train.
   - biz_101: csv phẳng.
   - biz_103: xlsx theo tháng, dòng nối tiếp để trống.
   - biz_105: sổ ghi tay, header 2 dòng, trả hàng số âm.
   - biz_117: ngày ghi 4 kiểu, giao nhiều đợt.
   - biz_120: nhà thuốc xuất từ phần mềm, 10 file.
   - biz_123: sqlite POS 17 bảng.
   - biz_124: 3 nguồn, sổ tay dùng tên hàng.
   - biz_126: không mã đơn, dòng phí phục vụ.

   Kết quả `oracle --all`: **113 đúng / 0 sai / 677 bỏ trống** trên 790 câu.
7. **H17: kiểm tra mapping theo nghĩa** (nay 10 bước): thành tiền ≈ số lượng × đơn giá − giảm giá, trạng thái hợp lý, ngày cuối khớp README, số âm chỉ ở đơn trả.
   - Ngưỡng đo trên 8 mapping đúng.
   - Phá có chủ đích 8 kiểu thì bị chặn cả 8; không chặn oan mapping đúng nào.
8. **R23** (dòng chú thích, "Tổng tháng") và **R25** (`41,785tr` bị đọc gấp 1000 lần). Loader chuẩn hoá Unicode NFC.
9. **G4 bộ tính ngày:** mọi kiểu kỳ và kiểu so sánh của §2, Tết tra `calendar.csv` (Tết 2025, 2026, 2027 đều dài 17 ngày); 122/123 plan viết tay tính được kỳ. Còn thiếu `anchor_price` (cần mặt hàng đã nối).
10. **K3: LLM thật.** Qwen3-8B Q4_K_M + llama.cpp b12064 trên RTX 4060 laptop.

    | Lần | Thay đổi | Plan khớp hoàn toàn |
    |---|---|---|
    | 1 | schema của hợp đồng | 69,9% |
    | 2 | schema sinh output tách theo loại câu, trường bắt buộc theo thứ tự, `filters` bắt buộc | **83,7%** |
    | 3 | thêm `grounding.py`: bộ lọc phải có căn cứ trong câu | **83,7%** |

    1,8 giây/câu. **Chạy 2 lần cho plan giống hệt nhau** trên cùng máy.
11. **Đo mức "sinh theo mẫu" của đề** (chỉ dùng train):
    - Sau khi che số, 3000 câu còn 1913 dạng.
    - **90% câu có câu giống ≥ 90% ở một cửa hàng khác**; 97% có câu giống ≥ 85%.
    - Về khuôn file: 16/30 cửa hàng có "anh em" giống ≥ 0,6 về chữ trong tên cột. biz_102, biz_103, biz_104 trùng 100%.
12. Artifact giải thích chi tiết cho leader: **"Nhật ký dựng DataMate"**, https://claude.ai/artifact/DpoKmLBRVag4NVhQ9z61hh (riêng tư).

## Các quyết định và phát hiện cần nhớ
- **Mục tiêu:** độ chính xác **≥ 95% trên câu đã trả lời**, đo trên cửa hàng train không nằm trong kho ví dụ; với điều kiện đó thì trả lời được càng nhiều càng tốt.
- **Vì sao đội khác đạt 0,9 (giả thuyết):** đề sinh theo mẫu, nên làm đủ hàm cho mọi mẫu câu cộng mapping vững là đạt được. Cũng có thể có đội dùng model lớn cho bảng public, vì giới hạn 15B chỉ bị kiểm khi BTC chạy lại Docker. **Mình không làm việc đó.**
- **Hướng đi tiếp:** tận dụng việc đề sinh theo mẫu (T1, T4), làm hàm tính theo tần suất mẫu câu (T3), mapping tự động dùng từ điển rút từ mapping tay cộng LLM (T5). Chi tiết ở mục 10 của kế hoạch.
- **Cách hiểu trạng thái đã kiểm bằng dữ liệu:**
  - "Đang giao dịch" (biz_103), "Đang xử lý" (biz_120), "shipping" (biz_123) là **đang giao**: chỉ xuất hiện ở 3 ngày cuối dữ liệu.
  - "Không giao được" (biz_124) là **huỷ**: tỉ lệ huỷ tính theo cách này khớp đáp án train (0,93%).
- **Mapping tay chỉ làm cho cửa hàng train** (thể lệ §4.2), và không vào Docker. Muốn thử kiểu dữ liệu chỉ có ở public / private thì tự tổng hợp biến thể từ cửa hàng train.
- **[D2] sinh code: đề xuất hoãn** (H13, chờ leader). Phương án "chỉ trả lời khi khớp [D1]" thực chất là tắt [D2].
- **Viết tắt:** không thay máy móc. `k` (không / nghìn), `ck`, `tt`, `dt`, `bn` có nhiều nghĩa. Từ điển chỉ lấy từ train; viết tắt nào thêm vào phải dựa trên lỗi đo được.

## Trạng thái hiện tại
- **Git:** commit cuối là `dae00dd` (review 2 + K2 + G1). **Việc ngày 04–05/11 chưa commit** (33 file). Lệnh cho leader:
  ```
  git add assets datamate docs tests tools
  git commit -m "04-05/11: G2 phần 1 + 8 mapping tay, H17 (10 bước kiểm tra), G4 bộ tính ngày, K3 83.7% (schema sinh output theo loại câu, kiểm tra bộ lọc có căn cứ), R23-R25"
  ```
- **Test:** 247 qua (`python -m pytest`), thêm 1 test chậm (`python -m pytest -m slow`, chạy cả split public, khoảng 1 phút).
- **Chạy thật:** khi chạy bình thường mọi câu vẫn bỏ trống, vì `map_business` (T5) chưa có. Chạy với mapping tay: 113 đúng / 0 sai trên 8 cửa hàng.
- **Chưa có:** G6 nối tên, G5 phần lớn thư viện hàm (mới có doanh thu, số đơn, mặt hàng bán chạy nhất, ngày doanh thu cao nhất), mapping tự động, LLM chưa nối vào `predict`, unanswerable chưa bật, Docker chưa có.
- **Môi trường:** Windows 11, Python 3.10 `.venv`, RTX 4060 laptop 8 GB.
  - Model: `E:\llm\models\Qwen3-8B-Q4_K_M.gguf` (sha256 `d98cdcbd…5785`).
  - llama.cpp: `E:\llm\llama-b12064\`.
  - Kết quả K3: `outputs/k3/`.

## Việc tiếp theo (chi tiết ở mục 10 của kế hoạch)
- **T1 (06/11 sáng):** gom 3000 câu train thành cụm mẫu câu → danh sách việc của G5 theo tần suất.
- **T2:** G6 nối tên. RapidFuzz không dấu, ngưỡng 90, ngang điểm thì không nối, từ đồng nghĩa cho kênh / hình thức thanh toán lấy từ train.
- **T3 (việc lớn nhất):** G5 thư viện hàm nhóm bán hàng (nhóm A–F) + nối LLM vào `predict` / `oracle` bằng `--llm-url`. Xong khi `oracle --all` với LLM ra 0 câu sai.
- **T4:** chạy LLM qua đêm trên 3000 câu, kiểm chứng bằng đáp án → kho ví dụ; cổng "câu anh em"; chọn ngưỡng theo kiểu bỏ ra một cửa hàng để độ chính xác ≥ 95%.
- **T5:** mapping tự động. Từ điển rút từ 8 mapping tay + LLM + 10 bước kiểm tra + sửa một lần. Đo theo kiểu bỏ ra một cửa hàng trên 8, và chạy cả chuỗi trên 22 cửa hàng còn lại.
- **T6 (tuỳ chọn, qua đêm):** tải Qwen3-14B Q4_K_M (~9 GB) bằng wifi, chạy K3 để so với 8B.
- **09/11:** tích hợp 30 cửa hàng, **nộp public lần đầu**.

## Việc chờ leader
1. Commit việc của ngày 04–05/11 (lệnh ở trên).
2. Quyết H13 ([D2] sinh code): đề xuất hoãn.
3. Chốt ngày thuê GPU (H20): build Docker, upload image, đo độ ổn định trên RTX 5090.
4. Đồng ý tải Qwen3-14B (~9 GB) khi có wifi (T6).
5. Theo dõi bảng xếp hạng public, và hỏi BTC về Docker guideline.

## Lệnh hay dùng
| Việc | Lệnh |
|---|---|
| Chạy test | `python -m pytest` · `python -m pytest -m slow` |
| Chạy với mapping tay và chấm | `python -m datamate.eval.oracle --all --out outputs/oracle_all` |
| Chấm K3 (cần llama-server) | `python -m datamate.eval.k3 --base-url http://127.0.0.1:8091 --out outputs/k3/x.jsonl` |
| Xem dữ liệu một cửa hàng train | `python tools/show_business.py data/train/data/biz_120` |
| Chạy agent trên một split | `python -m datamate.predict --data data/public_test --out outputs/run_public` |
| Kiểm định dạng file nộp | `python -m datamate.eval.validate --pred <file> --split public_test` |
| Sinh lại JSON schema sau khi sửa hợp đồng | `python -m datamate.contracts.export_schema` |

## File quan trọng
- `docs/TIEN_DO.md`: tiến độ theo ngày. `docs/HAN_CHE_VA_CAI_THIEN.md`: mọi lỗi R1–R25, lỗ hổng H / N / K. `docs/KE_HOACH_DataMate.md`: mục 9 (lịch), mục 10 (kế hoạch chi tiết). `docs/contracts.md`: hợp đồng v1.1.
- `datamate/contracts/`: hợp đồng (Pydantic). `datamate/loader/` (G1), `datamate/mapping/build.py` (G2, 10 bước kiểm tra), `datamate/temporal/` (G4), `datamate/metrics/` (G5), `datamate/nlu/` (baseline, `prompt.py`, `grounding.py`), `datamate/llm/` (`LlamaServerLLM`), `datamate/verify/`, `datamate/decide/`, `datamate/pipeline.py`.
- `assets/mappings/train/*.json`: 8 mapping tay. `assets/plans/`: 24 plan mẫu + 99 plan K2. `assets/rules/reference_rules.json`: luật tham chiếu cho [R].
- `datamate/eval/`: scorer §9, `run`, `validate`, `oracle`, `k3`.
