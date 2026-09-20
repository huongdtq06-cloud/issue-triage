# Issue Triage Mini-App

Mini-app này minh họa workflow LLM cho phân loại issue phần mềm bằng FastAPI, Pydantic structured output, validation ở application layer, tool calling deterministic và trace hiển thị trên UI.

## Architecture

```text
User input
  -> prompt template
  -> LLM structured output: IssueTriage
  -> Pydantic validation
  -> get_component_owner(component, environment)
  -> final response
  -> visible trace
```

`owner_team` không nằm trong `IssueTriage`. Giá trị này luôn đến từ tool trong application.

### Component vocabulary

`COMPONENT_TEAMS` trong `app/tools.py` là nguồn chân lý duy nhất cho danh sách component. Thêm một component vào bảng đó là đủ để mở rộng cả ba tầng: prompt, kiểu `Component` trong `IssueTriage`, và `TOOL_SCHEMA`.

Kiểu `Component` được viết tay thay vì sinh động từ `COMPONENT_TEAMS`, vì static checker từ chối biến bên trong type expression. Test `test_component_type_matches_table` giữ hai bên khớp nhau — nếu bạn thêm component vào bảng mà quên kiểu, test sẽ fail.

Model thường trả về cụm từ tự do (`"Payment Gateway"`, `"payment_gateway"`, `"product search"`). `normalize_component()` quy chúng về vocabulary chuẩn **trước khi** Pydantic validate, nên gần đúng không biến thành lỗi 422. Giá trị không quy được sẽ thành `component=null` kèm một dòng log warning — cố ý, để lỗ hổng vocabulary lộ ra thay vì hỏng âm thầm.

## Project Structure

```text
app/
  main.py
  models.py
  prompts.py
  tools.py
  triage.py
  static/
docs/
  uoc_tinh_chi_phi.html
tests/
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Điền `.env`:

```env
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-flash
```

Với DeepSeek, dùng DeepSeek API key trong `OPENAI_API_KEY`. DeepSeek hỗ trợ OpenAI-compatible base URL `https://api.deepseek.com`; model hiện trong docs là `deepseek-flash` hoặc `deepseek-v4-pro`.

## Run

```bash
uvicorn app.main:app --reload
```

Mở `http://127.0.0.1:8000`.

## API

```http
POST /api/triage
Content-Type: application/json

{
  "issue": "Nút thanh toán trả HTTP 500 với mọi thẻ Visa từ 14:30."
}
```

Response gồm `trace_id`, `triage`, `owner_team`, `final_response` và `trace`.

## Tests

```bash
pytest
```

Các test dùng mock LLM, không gọi API thật.

## Token And Cost

Xem `docs/uoc_tinh_chi_phi.html`. Tài liệu dùng giả định giá để minh họa cách tính chi phí cho 10,000 issue/tháng.
