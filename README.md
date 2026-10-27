# Stage 02: Skills

read_file, write_file, list_files, read_log_time_range + skill catalog + memory + compact session. Model tự load SKILL.md bằng read_file.

- Tools: `read_file(path)`, `write_file(path, content)`, `list_files(path)`, `read_log_time_range(path, start_time, end_time)`, `save_memory(note)`, `forget_memory(query)`
- Skills: `weekly-report`
- Memory: ghi chú dài hạn về người dùng, lưu ở `workspace/memory/memory.json`, nạp vào system prompt mỗi lượt
- Compact session: tự rút gọn history khi quá dài, không gọi thêm model (xem mục **Compact session**)

## Cài đặt và chạy

Cần Python 3.11+. Chạy trong thư mục project này. Chọn một trong hai cách.

**Cách 1: pip + requirements.txt**

```bash
python -m venv .venv
# Windows (PowerShell): .venv\Scripts\Activate.ps1      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
# Điền OPENAI_API_KEY, MODEL_NAME (và OPENAI_BASE_URL nếu dùng endpoint khác) vào .env
streamlit run app.py
```

Chạy test cần thêm pytest: `pip install -r requirements-dev.txt`.

**Cách 2: [uv](https://docs.astral.sh/uv/)**

```bash
uv sync
cp -n .env.example .env
uv run streamlit run app.py
```

(Trong repo lab gốc, 5 stage dùng chung `.venv` và `uv.lock` ở thư mục `agent-tools-skills-lab`: dùng `uv sync --all-packages --locked`. Khi chạy độc lập như trên thì `uv sync` là đủ.)

Mở **Local URL** in ra terminal (mặc định `http://localhost:8501`). `.streamlit/config.toml` của project bật `server.headless`, nên Streamlit không hỏi email ở lần chạy đầu và không tự mở trình duyệt; file này cũng đặt màu theme và tắt gửi thống kê sử dụng. Streamlit chỉ đọc file này khi chạy trong thư mục project.

Đường dẫn được resolve từ vị trí source. Chạy từ thư mục khác: `uv run --project stage-02-skills streamlit run stage-02-skills/app.py`; app vẫn dùng đúng `.env`, workspace và `traces/` của project này.

## Cấu hình model

| Biến | Bắt buộc | Ý nghĩa |
|---|---|---|
| `OPENAI_API_KEY` | Có | API key của provider |
| `MODEL_NAME` | Có | Tên model, cần hỗ trợ native tool calling |
| `OPENAI_BASE_URL` | Không | OpenAI-compatible endpoint. Endpoint phải hỗ trợ tool calling theo chuẩn OpenAI Chat Completions (`tools`, `tool_calls`, message role `tool`). |

Thiếu `OPENAI_API_KEY` hoặc `MODEL_NAME`: UI hiện cảnh báo, ô chat bị khóa và app không gọi model. App không truyền `temperature` hay tham số model khác; key không được ghi vào trace/log.

## Prompt thử

1. `Tạo báo cáo tuần từ data/weekly_notes.md, lưu vào output/weekly-report.md.`
2. (Cuộc trò chuyện mới) `2 + 3 bằng bao nhiêu?`

Kỳ vọng: Lượt 1: model call #1 chỉ có catalog trong system prompt; model gọi `read_file` với `skills/weekly-report/SKILL.md`, sau đó đọc `skills/weekly-report/references/report-template.md`, đọc dữ liệu và ghi `output/weekly-report.md`. Snapshot model call #2 có tool message chứa body SKILL.md. Câu hỏi 2 + 3 không cần load skill.

## Xem output, trace, state và context

- **Bố cục**: trang không cuộn; chỉ cột chat và cột State & Context cuộn riêng, cao theo cửa sổ trình duyệt (khối CSS nhỏ `PAGE_CSS` trong `app.py`). Nội dung dài (trace, bảng, file output) hiện đầy đủ trong cột, không có khung cuộn lồng nhau.
- **Chat (cột trái)**: mỗi lượt assistant có expander **Các bước thực hiện (N model call, M tool call)**: từng model call, mỗi tool call trong một khung có badge ok/lỗi, thời gian chạy, arguments (lệnh bash hiện dạng code), result; content/stdout/stderr hiện đầy đủ. Final answer nằm ngoài expander. Nút **Cuộc trò chuyện mới** (cạnh tiêu đề) xóa history, counters, snapshots, skill đã load của conversation cũ; không xóa `traces/` hay file output.
- **State & Context (cột phải)**: badge trạng thái và 4 counters cập nhật trong lúc chạy (rê chuột vào biểu tượng ? để xem định nghĩa); **Tools được cấp** (schema); **Skills trong catalog** (metadata, chưa phải đã load); **Skill content đã vào history** (chỉ khi `read_file` SKILL.md thành công, kèm message index và tool_call_id); **Tài nguyên đã đọc**; **Message history hiện tại**; **Event log**.
- **Context gửi model (lớp LangChain)**: snapshot request chụp ngay trước mỗi model call: system prompt thực tế, messages theo thứ tự, tools schema, metadata (conversation_id, run_id, lượt, model call, event sequence, thời điểm, model name, số message, số ký tự, usage nếu provider trả về). Trước model call đầu tiên, panel hiện **Context cấu hình (chưa gửi)**. Sau khi lượt kết thúc có thể chọn lại snapshot cũ (chỉ đọc, không chạy lại agent) và tải snapshot JSON. Snapshot không phải provider wire payload, tokenizer output hay nội dung bên trong model.
- **File đầu ra**: chọn file trong `workspace/output/`, xem Markdown/text và tải xuống. Xem file là thao tác UI, không gửi nội dung vào context của model.
- **Trace trên đĩa**: `traces/<thời gian>_<conversation>_turnNN_<run>.jsonl`, mỗi dòng một event (sequence, type, tool_call_id, tool_name, arguments, result, elapsed_ms; event `model_request` kèm snapshot request). Exception không mong đợi ghi thêm vào `traces/debug.log`.

## Định nghĩa trong State & Context

| Trường | Ý nghĩa |
|---|---|
| Lượt chat | Một lần gửi input; bắt đầu từ 1 trong mỗi conversation. |
| Lần gọi model trong lượt | Tăng ngay trước mỗi model request thực tế (middleware `wrap_model_call`); reset khi gửi lượt mới. Retry nội bộ của OpenAI SDK không quan sát được nên không đếm riêng. |
| Bước sự kiện trong lượt | Số thứ tự observer event (`user_submitted`, `model_request`, `model_response`, `tool_started`, `tool_finished`, `run_completed`, `run_failed`). Không phải LangGraph step. |
| Tool calls trong lượt | Số tool call đã thực thi, mỗi call có ID riêng. Một model response có thể yêu cầu nhiều tool calls. |
| Trạng thái | Sẵn sàng / Đang gọi model / Đang chạy tool / Hoàn tất / Lỗi. |

## Giới hạn thực thi

Mỗi lượt: tối đa 8 lần gọi model (`ModelCallLimitMiddleware`), 20 tool calls (`ToolCallLimitMiddleware`), recursion limit LangGraph 50 (số bước graph, không phải số tool calls). Giá trị nằm trong `config.py`.

Lỗi runtime/provider: UI hiện lỗi, giữ trace đã có, rollback model history về trước lượt lỗi. App không tự chạy lại lượt lỗi.

## Workspace và reset

Agent chỉ làm việc trong `workspace/`: `read_file` đọc file trong workspace, `write_file` chỉ ghi dưới `workspace/output/`. Lần chạy đầu, nếu chưa có workspace, app copy từ `fixtures/`; rerun không ghi đè.

Khôi phục dữ liệu gốc (xóa output và memory, giữ traces):

```bash
python reset_workspace.py        # hoặc: uv run python reset_workspace.py
```

Lệnh chỉ chạy khi workspace có marker `.lab-workspace` của lab.

## Skills

`skill_catalog.py` quét `workspace/skills/*/SKILL.md`, chỉ đưa `name`, `description`, `location` vào system prompt. Body và reference không có trong context ban đầu. Model tự đọc SKILL.md bằng `read_file` khi task khớp description; tool result ở lại trong history cho các lượt sau. Skill thiếu metadata hoặc YAML sai bị bỏ qua kèm diagnostic; trùng `name` báo lỗi và giữ bản đầu (xem expander **Skills trong catalog**). Thêm skill mới: tạo `workspace/skills/<name>/SKILL.md` (và bản trong `fixtures/skills/` nếu muốn giữ sau reset).

## Memory

- `save_memory(note)`: lưu MỘT ghi chú ngắn (tối đa 300 ký tự). Ghi chú trùng hoặc gần giống ghi chú đã có (sai chính tả, khác dấu câu, thiếu/thừa vài từ) không tạo bản mới: trả `duplicate` (giữ bản cũ) hoặc `updated` (bản mới đầy đủ hơn thay bản cũ). Khác số (ví dụ pool 20 vs 50) được coi là thông tin mới. Ghi chú ngắn (dưới 40 ký tự) chỉ trùng khi giống hệt.
- `forget_memory(query)`: xóa một ghi chú theo id hoặc cụm từ; nhiều ghi chú khớp thì trả `candidates` để chọn lại bằng id.
- Memory nằm trong `workspace/memory/memory.json`, nạp tối đa 4000 ký tự (ghi chú mới nhất) vào system prompt ở mỗi lượt. **Memory giữ nguyên khi bấm "Cuộc trò chuyện mới"**; muốn xóa hết: `python reset_workspace.py` (xóa cả output và memory, khôi phục data gốc).
- File hỏng: tool báo `MEMORY_CORRUPT`, không ghi đè file.

## Compact session

Trước mỗi lượt chat, app kiểm tra `compaction_reasons(...)`; nếu có lý do thì thay phần history cũ bằng một bản tóm tắt, giữ nguyên các lượt cuối. **Không gọi model** nên không tốn thêm token.

| Lý do | Khi nào |
|---|---|
| `context_threshold` | Tổng ký tự history + câu mới vượt `COMPACT_TRIGGER_CHARS` (6000, ngưỡng thấp để demo) |
| `repeated_or_large_tool_outputs` | Có tool result dài bị lặp hoặc tổng tool result vượt nửa ngưỡng |
| `milestone` / `cold_start` | Bấm nút **Checkpoint milestone** / **Cold-start checkpoint** trên đầu trang |

Bản tóm tắt gồm 3 phần: yêu cầu của người dùng, các câu trả lời đã chốt, và bằng chứng lỗi trích từ tool. Dòng log lỗi được gộp theo mẫu (bỏ timestamp, txn_id, số), ví dụ `... DB_POOL_EXHAUSTED (×38; 13:37:12→13:40:54)`, dòng hiếm nhưng nghiêm trọng (như dòng `possible leak ... settlement.py:88`) luôn được ưu tiên giữ. Giữ lại ít nhất `COMPACT_KEEP_LAST` (6) message cuối, bắt đầu bằng lượt của người dùng nên không bao giờ làm mồ côi tool result. Compact nhiều lần thì bản tóm tắt cũ được cộng dồn, không lồng nhau. Nếu compact gặp lỗi, history được giữ nguyên và UI hiện lý do.

Trên UI, lượt có compact hiện dòng **Compact session** (số ký tự trước/sau, số message) và expander **Bản tóm tắt**.

### Test compact

Không cần API key:

```bash
pytest tests/test_compact.py -v -s     # -s để in bản tóm tắt của kịch bản điều tra log
pytest tests/test_memory.py -v
```

Kịch bản test dựng lại đúng history của 5 prompt dưới đây (log thật `data/server.log`), nén lại rồi kiểm tra bản tóm tắt vẫn còn: lỗi `DB_POOL_EXHAUSTED`, module `payment`, giờ `13:37:12`, điều đã thử (pool size 20), và nguyên nhân nghi ngờ `settlement.py:88`.

Test thủ công trên UI (cần API key). Chạy `python reset_workspace.py` trước để xóa memory cũ, nếu không model có thể trả lời từ memory chứ không phải từ bản tóm tắt. Mở app, gửi lần lượt trong CÙNG một cuộc trò chuyện:

1. `Đọc data/server.log, tìm lỗi chính.`
2. `Lỗi xuất hiện lúc mấy giờ, module nào?`
3. `Mình đã thử tăng pool size lên 20 nhưng vẫn lỗi, ghi nhớ giúp, thử hướng khác.`
4. `Đọc lại log đoạn 13:39–13:41 xem có gì khác.`
5. `Tóm lại mình đang điều tra lỗi gì, đã thử gì, bước tiếp theo là gì?`

Kỳ vọng:

- Lượt 1-2: `DB_POOL_EXHAUSTED`, module `payment`, lỗi đầu tiên lúc `13:37:12`. Log bị cắt ngắn bởi `ToolResultBudgetMiddleware` (1500 ký tự) nên model có thể tự gọi `read_log_time_range`.
- Lượt 3: gọi `save_memory` (status `created`); `workspace/memory/memory.json` có đúng 1 ghi chú về pool size 20, gửi lại câu này không tạo thêm ghi chú.
- Lượt 4: `read_log_time_range`, thấy dòng 13:40:00 `nightly_settlement` giữ 7 connection 410s, nghi thiếu `conn.close()` ở `settlement.py:88`. Kết quả dài hơn 50 dòng thì cuối có dòng `[TRUNCATED ...]`.
- Trước lượt 5: xuất hiện **Compact session** (tự động khi vượt 6000 ký tự, hoặc bấm **Checkpoint milestone** trước khi gửi lượt 5 để ép compact). Lượt 5 trả lời đúng: đang điều tra `DB_POOL_EXHAUSTED` ở `payment`, đã thử tăng pool lên 20 nhưng vẫn lỗi, bước tiếp theo là kiểm tra/sửa connection leak ở job `nightly_settlement` (`settlement.py:88`).
- Muốn thấy compact sớm hơn, hạ `COMPACT_TRIGGER_CHARS` trong `config.py` (ví dụ 3000).

## Tests

```bash
pytest            # hoặc: uv run pytest
```

Tests dùng mock model, không cần API key.

## Giới hạn môi trường

- Chạy local, một người dùng cho mỗi project. Không có xác thực, không chia sẻ workspace đa người dùng.