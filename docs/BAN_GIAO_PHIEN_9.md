# Bàn giao phiên 9 (07/11) → phiên 10

*Viết 07/11/2026. Docker nộp lần 1 ngày 14/11; đóng băng 16/11 23:59.*

- Chi tiết từng bản sửa: [HAN_CHE_VA_CAI_THIEN.md](HAN_CHE_VA_CAI_THIEN.md), mục "Phiên 9 (07/11)", N72–N75.
- Lượt nộp và cách đọc điểm: [CAN_XAC_MINH.md](CAN_XAC_MINH.md), mục "Bộ nộp tiếp theo".
- Bàn giao trước: [BAN_GIAO_PHIEN_8.md](BAN_GIAO_PHIEN_8.md) (luật dữ liệu, lệnh hay dùng, quy tắc khi sửa: vẫn giữ nguyên).

## Bắt đầu phiên mới
Dán vào phiên chat mới:

> Đọc `docs/BAN_GIAO_PHIEN_9.md`, rồi `docs/CAN_XAC_MINH.md`. Kiểm `git status` và test (`.venv\Scripts\python.exe -m pytest -q`). Làm tiếp mục "Việc tiếp theo".

- Python, llama-server, luật dữ liệu: như [BAN_GIAO_PHIEN_8.md](BAN_GIAO_PHIEN_8.md). Lệnh server:
  ```powershell
  cd E:\llm\llama-b12064
  .\llama-server.exe -m E:\llm\models\Qwen3-8B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --parallel 1 --host 127.0.0.1 --port 8091
  ```

## Tình hình
| Thước đo | Giá trị |
|---|---|
| Điểm public mới nhất | **0,744** (lượt `run10_s27m`, nộp 07/11). Chưa nộp gì trong phiên 9 |
| Ứng viên nộp | **`outputs/replay/run11_s33/submission.jsonl`**: 821 câu trả lời (818 + 3 unanswerable). So với 0,744: 21 câu mới, 2 câu thành trống, không câu nào đổi giá trị |
| run11 (lượt LLM đủ, code cuối) | 1000 câu, **0 lỗi, 0 hết giờ, 38,7 phút** trên laptop. 992/1000 giống bản ghép không LLM |
| Train | **2731 đúng / 0 sai / 269 bỏ trống, PA +0,910** (`outputs/eval_cached_s9c.log`, CACHE MISSES 0) |
| Test | **466 qua** |

## Phiên 9 đã làm
| Mục | Việc | Kết quả |
|---|---|---|
| N72 | log ghi lý do có plan mà không ra kết quả (`no_result`); `datamate/diagnose.py` dò dòng `return None` khi đọc lại; `run_stats` đếm theo lý do | 93 câu được phân loại: 42 bộ lọc không áp được (phần lớn chặn đúng), 19 chưa có hàm, 6 xếp hạng tăng dần, 13 nợ / nhập, 13 lẻ |
| N73 | giờ đặt đơn từ cột README gọi là "thời điểm đặt đơn" (`from_readme.with_order_hour`) | dev_007, dev_008: +9 câu lọc theo ca |
| N74 | `metrics/lots.py`: lô gần hết hạn, tiền vốn lô hết hạn trong khoảng, danh sách hết hạn, hết hàng cuối ngày | công thức tồn theo lô = thẻ kho 80/80 mặt hàng; đúng mọi câu train kiểm được; dev_006 +8 câu; train +1 |
| N75 | run11 từ bản chép code như trong image; 2 quy tắc mới (`rate_as_value`, chuỗi tháng vắt qua năm) | +2 câu; Docker sẽ dao động khoảng 8/1000 câu so với lượt trước |

Việc 3 và 5 của phiên 8 đã xem, **không sửa**:
- đếm theo ngưỡng: 9 câu có hình plan train không có, đọc lại đều đúng ý câu;
- cổng chặn: phần lớn chặn đúng; 3 câu chặn oan do lỗi gõ ngẫu nhiên ("đơng", "tiềng báng"), nới cổng sẽ để lọt plan sai.

## Bài học của phiên 9
1. **Log phải nói vì sao không có số.** Có lý do theo dòng code thì 93 câu trống hiện rõ thành vài nhóm, và hai nhóm sửa được ngay (N73, N74). Đọc lại bằng `replay_run` để có chuỗi `return None`.
2. **Mẫu mapping nhỏ thắng mẫu đủ bảng.** `sibling_files` xếp mẫu theo tỉ lệ bảng **của mẫu** ghép được, nên mẫu một file (biz_101) thắng mẫu ghép được cả sổ nhập. Cửa hàng mất sổ nhập, danh mục và giờ đặt đơn. `enrich` bù được giờ (N73); sổ nhập thì chưa.
3. **Kiểm công thức bằng một nguồn khác trong chính dữ liệu**: tồn theo lô cộng lại phải bằng thẻ kho. Cách này chọn được cách tính hàng trả (theo ngày trả, không theo ngày đặt) trước khi có đáp án.
4. **Sinh tham lam vẫn không lặp lại y hệt giữa hai lượt**: 8/1000 câu đổi cách đọc, hai chiều bằng nhau. Đừng coi một câu đổi là lỗi code trước khi so `reading.llm_raw`.

## Việc tiếp theo
1. **Nộp** (5 lượt một ngày):
   - lượt 0 là `run11_s33`;
   - rồi chẩn đoán `outputs/public_ablation12/`: `bo_value_tron`, `bo_share_series_no_kho`, `bo_moi_003_009`, `bo_moi_dien_thoai`.
   - Cách đọc ở CAN_XAC_MINH. Ghi kết quả vào CAN_XAC_MINH và HAN_CHE.
2. **Docker (10–12/11)** trên RTX 5090 thuê.
   - Build theo `docker/Dockerfile` (code đã chạy được từ bản chép chỉ có `datamate/`, `assets/`, `configs/`).
   - Chạy public trong container không mạng, đo thời gian.
   - So từng câu với `outputs/public_run11` bằng `tools/compare_runs.py`. Kỳ vọng khác khoảng 1%, do LLM.
3. Nếu còn thời gian trước Docker, các nhóm trống còn lại theo N72, xếp theo lợi / rủi ro:
   - `sibling_files` xếp mẫu theo số file **của cửa hàng** được dùng (dev_007 / dev_008: sổ nhập, danh mục). Phải có server và đo lại cả train, vì mapping của hai cửa hàng đang trả lời tốt sẽ đổi;
   - `stock_value` không có khoảng hạn dùng (§5 "giá trị hàng tồn kho" theo giá vốn danh mục): có câu train (biz_124) để kiểm;
   - `nearest_expiry` khi LLM đọc thành `rank` (biz_123 train);
   - trả góp: `amount_due_total` của "còn bao nhiêu tiền chưa góp" → nợ; cần kiểm trên sổ góp trước.
4. Cho private (như phiên 8): đọc tham số từ rulebook thay vì chặn khi luật đổi; unanswerable đúng chỗ; dữ liệu tổng hợp ngành mới.

## Công cụ mới
| Công cụ | Dùng để |
|---|---|
| `tools/replay_run.py` | như trước, giờ thêm `no_result.at` (chuỗi dòng `return None`) vào log mỗi câu không ra số |
| `tools/run_stats.py <lượt>` | thêm phần "hàm không ra kết quả, theo lý do / theo dòng return None" |
| `outputs/snap_run11/` | bản chép code chạy run11; chạy predict từ thư mục này: `cd outputs\snap_run11; ..\..\.venv\Scripts\python.exe -m datamate.predict --data ..\..\data\public_test --out …` |
| `tools/compare_runs.py <lượt mới> <submission tham chiếu>` | so hai lượt từng câu, đếm theo cửa hàng, kiểu đổi và hàm (chỉ in số đếm). Dùng để so lượt Docker với `outputs/public_run11` |

## Git
Chưa commit từ `70c3dc4`. File mới của phiên 9: `datamate/diagnose.py`, `datamate/metrics/lots.py`, `tools/compare_runs.py`, `tests/test_diagnose.py`, `tests/test_order_hour.py`, `tests/test_lots.py`, `docs/BAN_GIAO_PHIEN_9.md`. Lệnh cho trưởng nhóm:
```powershell
cd E:\ZAIC
git add .gitignore .dockerignore assets configs datamate docker docs kaggle tests tools
git commit -m "Phiên 5-9: N27, N33-N75: ngành mới, sổ phụ, năm hai chữ số, lô và hạn dùng, giờ đặt đơn, log lý do không có số; run11 đủ 1000 câu; train 2731/0"
git push origin main
```
