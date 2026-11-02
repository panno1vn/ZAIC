# Data card và tính tay đáp án (T3 03/11 – T5 05/11)

Mỗi thành viên nhận 7–8 cửa hàng **train**, trộn đủ các ngành. Với mỗi cửa hàng:

1. Viết data card `docs/data_cards/<biz>.md` theo mẫu bên dưới.
2. Tính tay khoảng 10 câu hỏi của cửa hàng đó bằng notebook pandas (`notebooks/<biz>.ipynb`), cho tới khi khớp `answers.jsonl`.
3. Mỗi lần lệch đáp án mà tìm ra nguyên nhân, ghi vào [../rules_notes.md](../rules_notes.md).

Chỉ làm với cửa hàng train. **Không** viết data card hay tính tay cho cửa hàng public test (thể lệ §4.2).

## Chia cửa hàng

Vai trò chưa chia nên tạm gọi A, B, C, D; leader điền tên khi kickoff.

| Thành viên | Cửa hàng |
|---|---|
| A | biz_101, biz_106, biz_108, biz_114, biz_118, biz_122, biz_126, biz_130 |
| B | biz_102, biz_109, biz_110, biz_111, biz_115, biz_119, biz_123, biz_127 |
| C | biz_103, biz_104, biz_112, biz_116, biz_120, biz_124, biz_128 |
| D | biz_105, biz_107, biz_113, biz_117, biz_121, biz_125, biz_129 |

Ngành của từng cửa hàng: [datamate/eval/industries_train.json](../../datamate/eval/industries_train.json). biz_123 (POS sqlite 17 bảng) và biz_124 (nhiều nguồn) khó nhất, đã chia cho hai người khác nhau.

## Mẫu data card

```markdown
# biz_xxx — <ngành>, <kiểu file: csv phẳng / Excel xuất phần mềm / sổ ghi tay / sqlite / nhiều nguồn>

Khoảng dữ liệu: <ngày đầu> → <ngày cuối>   (README ghi: ...)
File và bảng: <file / sheet>: <mỗi dòng là gì>, <số dòng>
Khóa nối: <mã đơn, mã hàng, mã khách...>; có mã khách không?

Cột → nghĩa:
- <tên cột thô>: <nghĩa> (ví dụ giá trị)

Trạng thái đơn: <các giá trị thô> → hoàn thành / huỷ / trả hàng / đang giao
Đơn vị và quy đổi: <ở đâu, ví dụ>
Cạm bẫy: <định dạng tiền, ngày, ô trống, dòng đặc biệt, ghi tắt...>

Câu đã tính tay: <số câu khớp> / <số câu thử>; câu lệch: <id> — <vì sao>
```
