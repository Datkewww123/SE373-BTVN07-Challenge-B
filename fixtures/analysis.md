# Analysis – Stage 02: Skills (refund-policy)

## 1. Những gì đã làm

- Thêm tool `list_files(path)` vào `tools/files.py`, export trong `tools/__init__.py`, đăng ký trong `agent.py` (`TOOLS = [read_file, write_file, list_files]`).
- Thêm skill `workspace/skills/refund-policy/` (`SKILL.md` + `references/answer-template.md`).
- Hai tài liệu chính sách trong `workspace/data/policies/`:
  - `abc.md`: "Chính sách hoàn tiền trước tháng 10", áp dụng cho ngày mua trước 2026-10-01, hạn **7 ngày**, phí **10%**.
  - `xyz.md`: "Chính sách hoàn tiền từ tháng 10", áp dụng cho ngày mua từ 2026-10-01, hạn **14 ngày**, **không phí**.
  - Cả hai đều không hoàn tiền nếu sản phẩm đã kích hoạt.
- Tên file ban đầu mang nghĩa (`policy-before-oct.md`, `policy-from-oct.md`), sau đó đổi thành `abc.md`, `xyz.md` để kiểm tra agent có chọn policy theo nội dung chứ không đoán theo tên.

## 2. Kết quả kiểm tra tool `list_files`

Viết thêm `tests/test_list_files.py` (bộ test cũ chưa có test nào cho `list_files`). Kết quả: **11/11 pass**.

| Kiểm tra | Kết quả |
|---|---|
| Liệt kê `data/policies` trả đúng `name`, `path`, `type`, sắp xếp theo tên | pass |
| Không đệ quy (`data` chỉ trả `note.md` và thư mục `policies`) | pass |
| Liệt kê thư mục gốc `.` | pass |
| Thư mục không tồn tại → `DIRECTORY_NOT_FOUND` | pass |
| Truyền vào file → `NOT_A_DIRECTORY` | pass |
| `../` và `data/../../` → `PATH_OUTSIDE_WORKSPACE` | pass |
| Đường dẫn tuyệt đối `/etc` → `PATH_OUTSIDE_WORKSPACE` | pass |
| Path rỗng → `INVALID_PATH` | pass |
| Symlink trỏ ra ngoài workspace → `PATH_OUTSIDE_WORKSPACE` | pass |
| Tool trả JSON hợp lệ khi chạy với workspace của project | pass |

Toàn bộ bộ test: **48 pass, 4 fail**. Cả 4 fail là assertion cũ của stage gốc, không phải lỗi logic:

- `test_agent.py::test_registered_tools` và `test_read_then_write_with_parallel_calls_and_missing_file`: còn kỳ vọng `TOOLS == [read_file, write_file]`.
- `test_project.py::test_project_has_only_its_own_modules`: còn kỳ vọng `workspace/skills` chỉ có `weekly-report`.
- `test_app.py::test_renders_title_and_state_inspector`: còn kỳ vọng nhãn `Tools được cấp (2)` và `Skills trong catalog (1)`; hiện là 3 tool và 2 skill.

Cách sửa: cập nhật danh sách tool/skill kỳ vọng trong 4 test này. (Chạy bằng Python 3.12 trong môi trường kiểm tra, không phải 3.11 của project.)

## 3. Kết quả từng trường hợp

Ngày tính theo `ngày yêu cầu hoàn − ngày mua`. Chính sách chọn theo **ngày mua**.

| | Trường hợp A | Trường hợp B (sau đổi tên) | Thiếu thông tin |
|---|---|---|---|
| Input | Mua 28/09/2026, hoàn 06/10/2026, chưa kích hoạt | Mua 02/10/2026, hoàn 12/10/2026, chưa kích hoạt | Mua 02/10/2026, muốn hoàn 12/10/2026 (không nói kích hoạt) |
| Trace | `20261007-200816_30174f1d_turn01_1827cb62.jsonl` | `20261007-201435_d06c3958_turn01_27edd4ba.jsonl` | `20261007-201606_a6f402c7_turn01_8ce3c2af.jsonl` |
| Policy đúng | Trước tháng 10 (H = 7) | Từ tháng 10 (H = 14) | Chưa chọn policy |
| Số ngày đã qua N | 8 | 10 | – |
| Còn lại H − N | −1 | 4 | – |
| Kết quả đúng | **Không đủ điều kiện** (quá hạn), phí Không áp dụng | **Đủ điều kiện**, không có phí | **Hỏi lại trạng thái kích hoạt, chưa kết luận** |
| Số tool call | 4 | 4 | 2 |
| `answer_chars` | 322 | 560 | 185 |

Trace A ở thời điểm đó dùng tên file `policy-before-oct.md`. Trace A sau khi đổi tên là `20261007-201101_7fd4487e_turn01_e0fd6171.jsonl` (đọc `abc.md` và `xyz.md`, 540 ký tự), dùng làm đối chiếu.

> **Câu trả lời cuối của từng trường hợp:** trace chỉ lưu `answer_chars`, không lưu nội dung. Dán câu trả lời từ UI (hoặc ảnh chụp) vào đây trước khi nộp.
>
> - A: _[dán]_
> - B: _[dán]_
> - Thiếu thông tin: _[dán]_

## 4. Vị trí bằng chứng trong trace

`sequence` là số thứ tự event trong file `.jsonl`.

**Skill được nạp theo yêu cầu (cả 3 trace, ví dụ trace B):**

| Bằng chứng | Vị trí |
|---|---|
| Call #1 chỉ có catalog: system prompt có `refund-policy`, không có nội dung "Quy trình bắt buộc"; `message_count = 1`; tools gồm `read_file, write_file, list_files` | `sequence 2` (`model_request`, `snapshot.system_prompt`, `snapshot.tools`) |
| Model chủ động đọc `skills/refund-policy/SKILL.md` | `sequence 4–5` |
| Body SKILL.md xuất hiện trong context ở call #2 (`message_count = 3`) | `sequence 6` (`snapshot.messages`) |

**Tool tìm file:**

| Trace | Bằng chứng | Vị trí |
|---|---|---|
| B | `list_files("data/policies")` trả `['abc.md', 'xyz.md']` | `sequence 8–9` |
| A | `list_files` trả `['policy-before-oct.md', 'policy-from-oct.md']` | `sequence 8–9` |
| Thiếu thông tin | `list_files` trả `['abc.md', 'xyz.md']` | `sequence 8–9` |

**Chọn policy:**

| Trace | Hành vi | Vị trí |
|---|---|---|
| A (tên cũ) | Chỉ đọc `policy-before-oct.md`, rồi đọc `answer-template.md` | `sequence 12–13`, `16–17` |
| B (tên cũ, đối chứng, `20261007-200936_...`) | Chỉ đọc `policy-from-oct.md`, rồi đọc `answer-template.md` | `sequence 12–13`, `16–17` |
| B (sau đổi tên) | Đọc **cả** `xyz.md` và `abc.md` (hai call song song). Tên file không còn gợi ý, nên agent phải mở nội dung để thấy dòng "Áp dụng cho ngày mua…" | `sequence 12–15` (tool_finished: `14` = `xyz.md`, `15` = `abc.md`) |

**Kết thúc:**

| Trace | Vị trí |
|---|---|
| A | `sequence 20` (`run_completed`, `answer_chars = 322`) |
| B | `sequence 17` (model response không còn tool call), `sequence 18` (`run_completed`, `answer_chars = 560`) |
| Thiếu thông tin | `sequence 11` (model response không tool call) → `sequence 12` (`run_completed`, `answer_chars = 185`). Không có `read_file` nào đọc `abc.md`/`xyz.md`, nên chưa kết luận trước khi đủ thông tin |

## 5. Điểm chưa hoàn hảo (ghi nhận trung thực)

1. **Trace B (sau đổi tên) không đọc `answer-template.md`.** SKILL.md Bước 5 yêu cầu đọc template trước khi trả lời, và các trace A/B với tên cũ đều làm đúng (`sequence 16–17`). Ở trace B sau đổi tên, agent đọc hai policy rồi trả lời luôn (`sequence 16–17` là model call #4, không còn tool call). Khả năng cao câu trả lời không theo đúng 5 mục của template. Trace A sau đổi tên (`201101`) và B chạy lại (`201238`) cũng không đọc template. Nên xem lại câu trả lời trên UI.
2. **Trace thiếu thông tin gọi `list_files` trước khi hỏi** (`sequence 8`), trong khi SKILL.md chỉ cho tìm policy "sau khi có đủ thông tin". Hậu quả nhẹ: không đọc policy, không kết luận, nhưng thứ tự chưa đúng Bước 1 → Bước 2.
3. **Từng chọn sai policy trong quá trình lặp.** Các trace khoảng 20:04–20:06 (`200454`, `200537`, `200652`) đọc policy tháng 10 cho ngày mua 28/09. Từ trace `200816` agent đọc đúng policy; thời điểm này sát với lúc `SKILL.md` được chỉnh (mtime 20:06), nhiều khả năng là nhờ chỉnh sửa đó.
4. `fixtures/` chưa chứa skill `refund-policy` và hai policy, nên `reset_workspace.py` sẽ xóa chúng. Cần copy vào `fixtures/skills/` và `fixtures/data/policies/` nếu muốn giữ sau reset.

## 6. Trả lời câu hỏi cuối bài

### Vì sao cần tool để tìm file và skill để hướng dẫn chọn chính sách?

Hai thứ giải quyết hai vấn đề khác nhau.

**Tool là khả năng: agent *làm được* gì.** Trước khi có `list_files`, agent chỉ có `read_file(path)`, tức là phải biết sẵn đường dẫn chính xác. `list_files` cho agent nhìn thấy trạng thái thật của workspace tại thời điểm chạy. Trace B cho thấy điều này: sau khi đổi tên, `list_files` trả `abc.md`, `xyz.md` (`sequence 9`) và agent mở đúng các file đó.

**Skill là quy trình: agent *nên làm thế nào*.** Có tool vẫn chưa đủ, vì còn các quyết định nghiệp vụ mà tool không biết:

- Chọn policy theo **ngày mua**, không theo ngày yêu cầu hoàn. Ví dụ trường hợp A: mua 28/09, hoàn 06/10. Nếu chọn theo ngày hoàn, agent lấy policy tháng 10 (14 ngày), thấy 8 ≤ 14 và kết luận "đủ điều kiện", trong khi đáp án đúng là quá hạn (8 > 7).
- Kiểm tra đủ 3 thông tin (ngày mua, ngày hoàn, trạng thái kích hoạt) trước khi kết luận, và hỏi lại nếu thiếu thay vì đoán.
- Tính H − N, kết luận khớp con số, và trả lời theo template 5 mục.

Skill còn có lợi về context: nội dung chỉ vào context khi cần. Call #1 chỉ có mô tả ngắn trong catalog (`sequence 2`), body SKILL.md chỉ xuất hiện từ call #2 (`sequence 6`). Ngược lại, skill không có tool thì chỉ là lời khuyên: SKILL.md bảo "dùng `list_files`" nhưng nếu tool không tồn tại, agent không thể làm.

### Nếu agent chưa có tool tìm file, sửa prompt có giải quyết được yêu cầu đổi tên file không?

**Không.** Prompt thay đổi cách agent hành xử, không tạo ra khả năng mới.

1. Với chỉ `read_file`, agent phải tự đưa ra đường dẫn. Khi tên là `abc.md` và `xyz.md`, không có gì để suy ra, nên agent chỉ có thể đoán. Chính system prompt của project cấm điều này: nếu không có tool phù hợp thì phải nói rõ giới hạn, không được đoán.
2. Có thể ghi cứng `data/policies/abc.md` và `xyz.md` vào prompt, và lần này sẽ chạy. Nhưng đây chỉ là cách tránh vấn đề, không phải giải pháp. Đổi tên lần nữa hoặc thêm policy mới (ví dụ tháng 11) là prompt sai ngay, trong khi skill yêu cầu "luôn dùng file policy hiện tại trong workspace". Nguồn sự thật lúc đó là prompt, không phải workspace.
3. Nếu "yêu cầu đổi tên file" nghĩa là *người dùng nhờ agent thực hiện việc đổi tên*, thì cần thêm một tool rename/move. `write_file` chỉ ghi dưới `output/` và không xóa được file, nên cả `list_files` lẫn prompt đều không đủ.

**Kết luận:** prompt chỉ giúp agent dùng đúng cái đã có (hỏi lại, từ chối đúng cách), còn việc tìm file cần tool. Việc chọn đúng policy sau khi tìm thấy cần skill.