# 1. Learning objectives

Sau khi học xong tài liệu này, bạn có thể:

- lần theo telemetry từ lúc `backend.main` được import, qua FastAPI, Orchestrator và LangGraph, đến lúc process shutdown;
- phân biệt HTTP server span tự động với workflow/node span được tạo thủ công;
- đọc đúng quan hệ `trace_id`, `span_id`, parent context, `session_id` và LangGraph `thread_id`;
- giải thích processor/exporter hiện tại, giới hạn của chúng và tác động khi export lỗi;
- kiểm tra cách exception được ghi ở manual span và automatic HTTP span mà không đưa provider message vào trace;
- đánh giá control privacy nào được code thực thi, control nào chỉ là convention/tài liệu;
- bật console tracing cục bộ và đọc một trace mà không đưa dữ liệu thật vào request.

Quy ước nguồn bằng chứng trong tài liệu:

- **[Code dự án]**: kết luận đọc trực tiếp từ source hiện tại.
- **[Test]**: behavior được test hiện tại xác nhận bằng exporter in-memory và dependency mock.
- **[Thư viện cài đặt]**: behavior đọc từ source của đúng phiên bản trong `venv`; đây không phải logic riêng của dự án.
- **[Nhận xét]**: đánh giá kiến trúc hoặc khuyến nghị, không phải behavior đang được code bảo đảm.

# 2. OpenTelemetry’s role in this project

OpenTelemetry ở đây là lớp quan sát chạy ngang qua runtime, không phải engine thực thi workflow:

```text
HTTP request
  -> FastAPI automatic server span
     -> Orchestrator manual workflow span
        -> LangGraph manual node spans
           -> BERT / T5 / Gemini / pure processing
```

**[Code dự án]** `backend/main.py` sở hữu lifecycle cấp ứng dụng: đọc `.env`, tạo telemetry runtime, instrument FastAPI và shutdown provider. `backend/agents/orchestrator.py` đặt span quanh từng use case. `backend/agents/ielts_graph.py` đặt span quanh code của từng node. `backend/observability/telemetry.py` gom cấu hình, provider, exporter, processor, helper span, HTTP sanitization và cleanup.

Telemetry không quyết định graph nào chạy, không truyền LangGraph state và không tạo checkpoint. Orchestrator/LangGraph vẫn làm các việc đó. Telemetry chỉ quan sát các boundary đã được code chọn. Vì vậy:

- `trace_id` liên kết các operation trong một distributed trace;
- `span_id` định danh một operation quan sát được;
- `session_id` là định danh nghiệp vụ của một lần xử lý IELTS;
- `thread_id` là khóa checkpoint của LangGraph và hiện lấy đúng giá trị `session_id`.

Ba định danh cuối không tự động ánh xạ sang nhau. Code cố ý không ghi raw `session_id`/`thread_id` vào span, nên trace không thể được tìm ngược bằng session hiện tại.

# 3. Package inventory

Chỉ bốn package OpenTelemetry xuất hiện trong `requirements.txt`:

| Package | Version pin | Module/file sử dụng | Vai trò | Kiểu instrumentation |
|---|---:|---|---|---|
| `opentelemetry-api` | `1.44.0` | `backend/observability/telemetry.py`; test import `StatusCode` | API cho `Tracer`, `Span`, `SpanKind`, `Status`; active context và current span | Nền tảng cho manual và automatic instrumentation |
| `opentelemetry-sdk` | `1.44.0` | `backend/observability/telemetry.py`; `tests/test_telemetry.py` dùng in-memory exporter | `TracerProvider`, `Resource`, `SimpleSpanProcessor`, `BatchSpanProcessor`, console exporter | Cấu hình thủ công |
| `opentelemetry-instrumentation-fastapi` | `0.65b0` | lazy import trong `instrument_fastapi()`; test dùng `FastAPIInstrumentor.uninstrument_app()` | Bọc FastAPI/ASGI để tạo HTTP server span | Automatic instrumentation được kích hoạt bằng code |
| `opentelemetry-exporter-otlp-proto-http` | `1.44.0` | lazy import trong `_build_exporter()` khi chọn `otlp` | Gửi span qua OTLP/HTTP protobuf | Exporter cấu hình thủ công |

**[Code dự án]** Không có package instrumentation riêng cho Google Gen AI, `httpx`/`requests`, PyMongo, SQLite hay LangGraph. Do đó không được suy ra outbound Gemini HTTP span, MongoDB span hay checkpoint SQL span từ dependency list.

# 4. Startup lifecycle

## 4.1 Trình tự import và startup

1. **Đọc `.env`.** Khi module `backend/main.py` được import, `load_dotenv()` chạy ở module scope trước khi đọc các biến telemetry. Nó tìm file `.env` theo behavior của `python-dotenv`; trong cách chạy dự án từ root, file cấu hình thực tế là `backend/.env` theo hướng dẫn/script, nhưng `main.py` không truyền một path tuyệt đối cho `load_dotenv()`.
2. **Đọc settings và tạo runtime.** Ngay sau đó, `telemetry_runtime = initialize_telemetry()` gọi `TelemetrySettings.from_environment()` qua `create_telemetry_runtime()` trong `backend/observability/telemetry.py`.
3. **Tạo app và instrument.** `FastAPI(...)` được tạo, rồi `instrument_fastapi(app, telemetry_runtime)` chạy ở module scope. Đây là trước khi Uvicorn bắt đầu nhận request và trước FastAPI lifespan.
4. **Startup ứng dụng.** `backend.main.lifespan()` gọi `await orchestrator.start()`. Việc compile LangGraph/checkpointer xảy ra ở đây, không phải trong telemetry setup.
5. **Phục vụ request.** HTTP middleware tạo server span; Orchestrator và graph tạo manual spans nếu runtime đang enabled.
6. **Shutdown.** Phần `finally` lồng nhau trong `lifespan()` đóng Orchestrator, Mongo client rồi gọi `shutdown_telemetry()`.

Điểm quan trọng: telemetry được khởi tạo ở **import time**, còn Orchestrator được start ở **FastAPI lifespan startup**.

## 4.2 Settings và provider

`backend/observability/telemetry.py::TelemetrySettings.from_environment()` đọc trực tiếp:

| Biến | Default của project | Cách dùng |
|---|---|---|
| `OTEL_SDK_DISABLED` | `true` | `_environment_flag()` chấp nhận `1/true/yes/on` và `0/false/no/off`; giá trị sai được warning rồi dùng default `true` |
| `OTEL_TRACES_EXPORTER` | `console` | chọn `console`, `otlp`, `none`; tên khác warning và fallback console |
| `OTEL_SERVICE_NAME` | `ielts-writing-agent` | trở thành `service.name` trong `Resource` |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | không có | truyền cho OTLP trace exporter nếu có |

Nếu disabled hoặc exporter là `none`, `create_telemetry_runtime()` trả `TelemetryRuntime(enabled=False)` trước khi tạo provider/exporter.

Nếu enabled:

- **[Code dự án]** một **SDK `TracerProvider` mới** được tạo bằng `TracerProvider(resource=Resource.create(...))`;
- code không gọi `trace.get_tracer_provider()` và không gọi `trace.set_tracer_provider()`;
- tracer thủ công được lấy trực tiếp từ provider đó bằng `provider.get_tracer("ielts-writing-agent")`;
- FastAPI instrumentor cũng nhận chính provider đó qua tham số `tracer_provider`.

Vì vậy HTTP span và manual span cùng provider dù provider không được đăng ký làm global provider. Một instrumentation khác chỉ dùng global provider sẽ không tự động dùng provider riêng này.

`Resource.create({SERVICE_NAME: settings.service_name})` đặt `service.name`. **[Thư viện cài đặt]** `Resource.create()` còn merge resource mặc định và `OTEL_RESOURCE_ATTRIBUTES`; explicit `service.name` của project được merge sau nên thắng nếu trùng key. Vì vậy `service.version` và `deployment.environment.name` trong `backend/.env.example` được SDK đọc, dù `TelemetrySettings` không parse hai field đó. SDK cũng đọc sampler từ `OTEL_TRACES_SAMPLER`; project không tự tạo sampler.

## 4.3 Processor/exporter được gắn lúc nào

Trong `create_telemetry_runtime()`:

- nếu test/code caller inject `span_exporter`, project dùng `SimpleSpanProcessor`;
- nếu dùng exporter từ environment (`console` hoặc `otlp`), project dùng `BatchSpanProcessor`.

Đây là điều kiện theo **exporter có được inject hay không**, không phải theo loại console hay OTLP. Runtime production dùng console vẫn là Batch.

## 4.4 Gọi setup nhiều lần và shutdown

`initialize_telemetry()` có thể được gọi nhiều lần: nó tạo runtime mới, thay module-global `_runtime`, rồi shutdown runtime cũ nếu cũ đang enabled. Tuy nhiên toàn bộ setup cấp app không hoàn toàn idempotent:

- `instrument_fastapi()` luôn gọi `app.add_middleware(_SanitizeUnhandledExceptionMiddleware)` trước khi gọi instrumentor;
- **[Thư viện cài đặt]** `FastAPIInstrumentor` có cờ chặn instrument cùng app lần hai, nhưng custom middleware của project không có guard riêng;
- reinitialize provider sau khi app đã instrument cũng không tự nối middleware hiện tại sang provider mới.

Production path trong `backend/main.py` chỉ gọi mỗi bước một lần, nên không có duplicate trong flow bình thường.

`TelemetryRuntime.shutdown()` gọi `provider.force_flush()` rồi `provider.shutdown()`. `shutdown_telemetry()` trước hết thay `_runtime` bằng runtime disabled, sau đó flush/shutdown runtime cũ. Trong `backend.main.lifespan()`, các `finally` lồng nhau bảo đảm telemetry shutdown vẫn được gọi nếu `orchestrator.close()` hoặc `client.close()` raise.

Giới hạn xác nhận từ code: `await orchestrator.start()` nằm **trước** khối `try` của lifespan. Nếu startup đó raise, `shutdown_telemetry()` trong lifespan không chạy. Code provider/library có cơ chế `atexit`, nhưng không nên coi đó là thay thế hoàn toàn cho cleanup lifecycle rõ ràng.

# 5. FastAPI instrumentation

## 5.1 Automatic server span

`backend/observability/telemetry.py::instrument_fastapi()` lazy-import `FastAPIInstrumentor` và gọi `instrument_app()` với provider riêng. **[Thư viện cài đặt]** instrumentor bọc ASGI middleware stack; với một request HTTP bình thường không có active local span, middleware:

1. extract incoming propagation headers (ví dụ W3C `traceparent`) vào context;
2. tạo `SpanKind.SERVER`;
3. make server span current trong lúc FastAPI xử lý request;
4. ghi response status;
5. detach context và end span sau khi ASGI response hoàn tất.

Test hiện tại xác nhận route span có tên dạng `GET /grammar_correction`. Với các endpoint chính, tên dự kiến là `POST /evaluate_essay`, `POST /grammar_correction`, `POST /essay_process`. Tên/attribute HTTP chi tiết còn chịu semantic-convention mode của instrumentation version, nên tài liệu chỉ coi dạng `METHOD route` là behavior đã đọc/test ở phiên bản cài đặt.

Các nhóm attribute dự kiến từ instrumentation `0.65b0` gồm method, route/path, URL scheme/server, network protocol và response status. Tên semantic key có thể là bộ mới (`http.request.method`, `http.route`, `url.scheme`, `url.path`, `server.address`, `network.protocol.version`, `http.response.status_code`) hoặc bộ legacy tương ứng (`http.method`, `http.target`, `http.scheme`, `http.host`, `http.flavor`, `http.status_code`) tùy semantic-convention stability environment. Các key privacy mà project chủ động overwrite được liệt kê ở mục kế tiếp; đó là những key có behavior đáng tin cậy hơn trong code riêng của project.

Project không truyền `excluded_urls`. Vì vậy mọi HTTP route đều được instrument khi enabled: `/`, `/health`, `/ready`, `/live`, `/version`, ba workflow endpoint, OpenAPI/docs và cả route không khớp. Biến exclusion chuẩn của thư viện có thể ảnh hưởng nếu operator tự đặt ở environment, nhưng project và `.env.example` không cấu hình nó. Health endpoints vì thế **có span** theo cấu hình hiện tại.

`exclude_spans=["receive", "send"]` chỉ loại các ASGI internal receive/send spans. Nó không loại server span.

## 5.2 Attributes và privacy hooks

Automatic middleware thu thập metadata HTTP chuẩn như method, route/path, scheme/server, protocol và status tùy semantic-convention mode. Project thêm `server_request_hook=_sanitize_server_request` để overwrite dữ liệu nhạy cảm:

- client address/IP thành `[REDACTED]`, port thành `0`;
- user-agent attributes cũ và mới thành `[REDACTED]`;
- nếu query string không rỗng, target chỉ còn path, URL được dựng lại không có query và `url.query` thành `[REDACTED]`.

`_safe_url()` chỉ dựng `scheme://host[:port]/path`, không nối query. Test `test_fastapi_redacts_query_and_unhandled_exception_message` xác nhận query value, client address và user-agent không xuất hiện trong finished spans.

Header capture được khóa lại bằng:

```python
http_capture_headers_server_request=["$^"]
http_capture_headers_server_response=["$^"]
http_capture_headers_sanitize_fields=[".*"]
```

Regex `$^` không khớp header nào, nên request/response headers không được capture; sanitize-all là lớp phòng vệ bổ sung nếu capture logic thay đổi. Request **body** không được FastAPI instrumentation hiện tại ghi vào span. Query parameter `answer` của `/grammar_correction` được hook che toàn bộ khi query không rỗng.

## 5.3 Middleware exception sanitizer và ảnh hưởng request

Khi tracing enabled, project thêm `_SanitizeUnhandledExceptionMiddleware`. Nó để request thành công đi qua nguyên trạng. Nếu có unhandled exception, nó thay exception thoát khỏi app bằng `SanitizedTelemetryError(<qualified-type>)` và bỏ message/cause hiển thị. Automatic OTel exception handler ở lớp ngoài vì thế chỉ thấy biểu diễn đã sanitize.

Kết luận chính xác:

- successful response/business result không thay đổi;
- lỗi vẫn là lỗi và vẫn tạo HTTP 500, không bị nuốt;
- nhưng type/message exception quan sát ở biên ASGI đã bị thay đổi để bảo vệ trace/log của instrumentation;
- khi tracing disabled, middleware sanitizer không được thêm, nên unhandled exception nguyên bản có thể đi đến Uvicorn/test harness. Đây là khác biệt error-surface, dù workflow logic vẫn như cũ.

# 6. Manual spans

Tất cả manual span đi qua `_start_span()` và có `SpanKind.INTERNAL`. Helper tắt automatic exception recording của context manager (`record_exception=False`, `set_status_on_exception=False`) để tự sanitize rồi bare-raise exception gốc.

## 6.1 Workflow root spans

“Root” ở đây có nghĩa là root của **application workflow subtree**. Trong một HTTP request, nó là child của HTTP server span, không phải root của toàn trace.

| Span | File; class.method | Operation được bao | Parent dự kiến | Attributes | Lỗi và lúc kết thúc |
|---|---|---|---|---|---|
| `ielts.workflow.evaluate` | `backend/agents/orchestrator.py`; `IELTSWritingOrchestrator.evaluate_essay()` | lazy `start()`, chọn/tạo session, `evaluation_graph.ainvoke()`, lấy `state["report"]` | `POST /evaluate_essay` server span; hoặc active caller span; không có thì root | `ielts.workflow.name=evaluate`, `ielts.session.source=provided|generated`, `ielts.checkpoint.enabled=true`, backend `sqlite|injected` | exception được sanitize-record rồi raise; end khi rời `with`, kể cả lỗi |
| `ielts.workflow.grammar` | cùng file; `correct_grammar()` | `start()`, session, grammar graph, report | `POST /grammar_correction` | tương tự, workflow `grammar` | tương tự |
| `ielts.workflow.combined` | cùng file; `process_essay()` | `start()`, session, combined graph, report | `POST /essay_process` | tương tự, workflow `combined` | tương tự |

Workflow span bắt đầu **trước** `await self.start()`. Khi app startup bình thường, `start()` đã là no-op; nếu một caller dùng Orchestrator ngoài FastAPI, thời gian lazy initialization có thể nằm trong span.

## 6.2 LangGraph node spans

| Span | `backend/agents/ielts_graph.py` function | Operation/tool | Parent dự kiến | Attributes riêng | Node kết thúc khi |
|---|---|---|---|---|---|
| `ielts.node.validate_input` | `validate_input()` | trim và validate question/answer | workflow span | `ielts.node.name=validate_input` | function return/raise |
| `ielts.node.prepare_session` | `prepare_session()` | bảo đảm session trong combined state | workflow span | node name | function return/raise |
| `ielts.node.score_essay` | closure từ `_score_essay_node()` | await injected BERT scoring dependency | workflow span | node name; `ielts.tool.name=bert_scoring` | dependency và float conversion xong/raise |
| `ielts.node.correct_grammar` | closure từ `_correct_grammar_node()` | await injected CoEdit T5 dependency | workflow span | tool `coedit_t5` | dependency xong/raise |
| `ielts.node.generate_feedback` | closure từ `_generate_feedback_node()` | await injected Gemini feedback dependency | workflow span | tool `gemini_feedback` | toàn bộ feedback call/retry xong/raise |
| `ielts.node.process_scores` | `process_scores_node()` | extract/clean score, thuần local | workflow span | tool `score_processor` | function return/raise |
| `ielts.node.build_report` | một trong ba `build_*_report_node()` | dựng report tương ứng | workflow span | tool `report_generator` | function return/raise |

Ba report functions dùng cùng span name/attributes; workflow parent cho biết đó là evaluation, grammar hay combined. **[Test]** Combined workflow test xác nhận cả bảy node span là direct child của workflow span. Graph edge không làm node sau trở thành child của node trước; các node là sibling operations trong cùng workflow.

## 6.3 Tool/model/database spans thực sự có hay không

- `ielts.node.score_essay`, `correct_grammar`, `generate_feedback` là span boundary bao cả tool call. Không có manual child span sâu hơn cho model load, inference hay từng Gemini attempt.
- `process_scores` và `build_report` vẫn gắn `ielts.tool.name`, nhưng đây là local processing, không phải remote/model span.
- Không có manual span cho SQLite checkpointer, MongoDB insert hay Mongo client.
- Không có automatic instrumentation package cho Google Gen AI/HTTP client/PyMongo. Vì vậy hiện **không có outbound Gemini HTTP span và không có MongoDB span** được code này tạo.

# 7. Span hierarchy

Các cây dưới đây mô tả span thực sự có trong project khi tracing enabled. Mọi node là `INTERNAL`; HTTP span là `SERVER`.

## 7.1 `POST /evaluate_essay`

```text
POST /evaluate_essay [SERVER]
└─ ielts.workflow.evaluate [INTERNAL]
   ├─ ielts.node.validate_input
   ├─ ielts.node.score_essay
   ├─ ielts.node.generate_feedback
   ├─ ielts.node.process_scores
   └─ ielts.node.build_report
```

Không có Gemini HTTP child span. Retry Gemini, nếu xảy ra, nằm trong duration của một `generate_feedback` span.

## 7.2 `POST /grammar_correction`

```text
POST /grammar_correction [SERVER]
└─ ielts.workflow.grammar [INTERNAL]
   ├─ ielts.node.validate_input
   ├─ ielts.node.correct_grammar
   └─ ielts.node.build_report
```

## 7.3 `POST /essay_process`

```text
POST /essay_process [SERVER]
└─ ielts.workflow.combined [INTERNAL]
   ├─ ielts.node.validate_input
   ├─ ielts.node.prepare_session
   ├─ ielts.node.score_essay ───────────────┐  chạy song song
   ├─ ielts.node.correct_grammar ───────────┘  sau prepare_session
   ├─ ielts.node.generate_feedback              sau score_essay
   ├─ ielts.node.process_scores                 sau generate_feedback
   └─ ielts.node.build_report                   join processed scores + grammar
```

Nếu MongoDB được cấu hình, hai insert chạy **sau khi** `ielts.workflow.combined` đã end vì Orchestrator đã trả report, nhưng vẫn trước khi HTTP server span end. Chúng không sinh database span. Vì vậy duration HTTP có thể lớn hơn workflow bởi persistence và response handling.

# 8. Context propagation

## 8.1 Active context nằm ở đâu

**[Thư viện cài đặt]** OpenTelemetry Python giữ current context bằng `contextvars.ContextVar`. FastAPI ASGI middleware attach server span vào context. `_start_span()` dùng `tracer.start_as_current_span(...)` mà không truyền parent tường minh, nên provider lấy current span làm parent và tạm đặt manual span mới làm current.

Luồng context bình thường:

```text
incoming trace context (nếu có)
  -> current HTTP server span
     -> current workflow span
        -> current node span trong task của node
```

Khi mỗi context manager kết thúc, context trước được khôi phục. `trace_id` giữ nguyên trong toàn cây; mỗi span có `span_id` riêng. Nếu request có W3C `traceparent` hợp lệ, server span tiếp tục trace đó; nếu không, server span mở trace mới.

## 8.2 LangGraph và các nhánh song song

Combined graph fan-out sau `prepare_session`. LangGraph hiện chạy `score_essay` và `correct_grammar` trong các async task riêng. Async task copy current `contextvars` context lúc được tạo, nên hai node nhìn thấy cùng workflow span làm parent:

- cùng `trace_id` với HTTP/workflow;
- hai `span_id` khác nhau;
- cùng `parent.span_id` là workflow span;
- timing có thể overlap nhưng parent/child không biểu diễn graph dependency. Edge/order phải đọc từ timestamps hoặc graph definition.

**[Test]** `test_combined_workflow_creates_root_and_node_spans` xác nhận tất cả combined node spans có direct parent là workflow span, bao gồm hai nhánh song song.

## 8.3 Thread offloading

Các boundary có `asyncio.to_thread`:

- `backend/agents/ielts_graph.py::run_bert_scoring()` offload BERT;
- `backend/tools/grammar_checker.py::check_grammar()` offload blocking T5 processing;
- `backend/tools/feedback_generator.py::get_feedback_for_score()` offload mỗi Gemini attempt;
- `backend/main.py::essay_process()` offload Mongo inserts.

**[Probe trên đúng môi trường dự án]** một probe không gọi mạng/model đã xác nhận `asyncio.to_thread` giữ cùng current `trace_id` và current `span_id` trong worker thread. Đây cũng là behavior chuẩn của Python hiện dùng: `to_thread` sao chép current `contextvars.Context`. Do đó nếu code trong worker tạo child span bằng tracer thích hợp, nó có thể nhận node span làm parent.

Hiện các model/provider/Mongo functions trong thread không tạo OTel span, nên propagation này không sinh thêm span. Context vẫn có thể mất nếu tương lai dùng raw `threading.Thread`, executor API không copy context, callback detached, subprocess, hoặc thư viện tự quản thread mà không propagate. Những trường hợp đó chưa xuất hiện ở boundary được khảo sát.

## 8.4 Ba loại ID không được nhầm

| ID | Ai tạo | Phạm vi/ý nghĩa | Có được đưa vào span không |
|---|---|---|---|
| `session_id` | Orchestrator dùng UUID nếu caller không cấp | định danh nghiệp vụ trong report/state | raw value: không; chỉ `ielts.session.source` |
| `thread_id` | Orchestrator gán bằng đúng `session_id` | namespace/checkpoint key của LangGraph | không |
| `trace_id` | OTel propagator/provider hoặc upstream | nối các span trong một trace | có trong metadata mỗi span, nhưng không nằm trong business response |

Không có hash/pseudonym của session được ghi. Do đó privacy tốt hơn, nhưng thiếu khả năng correlation session-to-trace có kiểm soát.

# 9. Processor and exporters

## 9.1 Implementation hiện tại

### `BatchSpanProcessor` trong runtime bình thường

Khi exporter được tạo từ environment, `create_telemetry_runtime()` đăng ký `BatchSpanProcessor(exporter)`. Mỗi span đã end được đưa vào queue; worker nền gom batch và gọi exporter. Project không truyền batch size, queue size hay schedule delay, nên **[Thư viện cài đặt]** các default/biến `OTEL_BSP_*` của SDK quyết định.

Code không có comment nêu lý do chọn processor. **[Nhận xét dựa trên cấu trúc test]** Simple được dùng khi inject exporter để assertion thấy span ngay; Batch được dùng cho runtime để tách export khỏi request path. Đây là diễn giải thiết kế, không phải ý định được tác giả ghi thành comment.

Hệ quả:

- request thông thường không chờ network export của từng span;
- span con có thể được enqueue trước span cha vì node end trước workflow, workflow end trước HTTP;
- backend dựng lại tree bằng IDs, không dựa vào thứ tự dòng console;
- queue đầy/export chậm có thể làm drop span; không làm LangGraph retry business operation.

### `SimpleSpanProcessor` trong test/injection

Khi caller truyền một `span_exporter` trực tiếp, project dùng `SimpleSpanProcessor`. `tests/test_telemetry.py::setUp()` inject `InMemorySpanExporter`, nhờ đó finished span có ngay để assertions đọc. Đây là test path, không phải console production path.

### Console exporter

`_build_exporter()` trả `ConsoleSpanExporter()` khi `OTEL_TRACES_EXPORTER=console` hoặc khi exporter name không biết. **[Thư viện cài đặt]** exporter serialize từng span thành JSON-like text ra standard output. Vì nó nằm sau Batch processor trong normal runtime, output thường xuất hiện theo batch/delay, không nhất thiết ngay tại lúc node kết thúc.

### OTLP HTTP exporter

Khi `OTEL_TRACES_EXPORTER=otlp`, `_build_exporter()` lazy-import `OTLPSpanExporter`:

- nếu `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` có giá trị, code truyền nó làm `endpoint` và exporter dùng đúng endpoint đó; phải cấp path hoàn chỉnh như `/v1/traces` nếu receiver yêu cầu;
- nếu biến traces-specific không có, code gọi `OTLPSpanExporter()` không đối số. **[Thư viện cài đặt]** lúc đó exporter có thể đọc `OTEL_EXPORTER_OTLP_ENDPOINT` và nối trace path, hoặc dùng default `http://localhost:4318/v1/traces`.

Project không truyền headers, certificate, compression, timeout hoặc retry policy. **[Thư viện cài đặt]** version `1.44.0` đọc timeout traces-specific/general của OTLP và fallback mặc định 10 giây; exporter thử tối đa 6 vòng với exponential backoff có jitter cho response retryable. Đây là behavior thư viện, không phải retry do project viết; thay version có thể đổi chi tiết. Project cũng không set các biến này trong `.env.example`.

### Nếu OTLP endpoint không truy cập được

Với normal Batch processor, export xảy ra trong worker nền. Lỗi kết nối được exporter/processor log hoặc đánh dấu export failure; nó không được raise ngược vào FastAPI request đã chạy. Business request vì thế thường vẫn trả theo kết quả workflow.

Cần phân biệt ba thời điểm:

- lỗi cấu hình/import exporter lúc `backend.main` import có thể làm app không startup;
- lỗi network export sau đó thường không làm request fail vì Batch processor tách nền;
- `force_flush()`/`shutdown()` có thể chờ công việc export và làm shutdown lâu hơn; code không kiểm tra giá trị boolean trả về từ `force_flush()`.

Project không chứa OpenTelemetry Collector, trace backend, Docker service hay deployment config cho observability. OTLP mode chỉ gửi tới một endpoint **đã tồn tại** do operator cung cấp.

## 9.2 So sánh bổ sung — không phải mô tả code hiện tại

| Lựa chọn | Phù hợp | Trade-off |
|---|---|---|
| Console exporter | học local, kiểm tra naming/attributes/privacy nhanh | output nhiều, khó query/retention, có thể lộ metadata local nếu console được thu gom |
| OTLP exporter | gửi chuẩn hóa tới Collector/backend | cần endpoint, auth/TLS/retention vận hành đúng |
| Simple processor | test deterministic, exporter rất nhanh | export đồng bộ theo `on_end`; network exporter có thể tăng latency |
| Batch processor | service runtime và remote export | cần queue/flush tuning; có thể mất span khi crash hoặc queue đầy |

Project chọn hợp lý: Simple cho injected in-memory test; Batch cho console/OTLP runtime.

# 10. Error handling

## 10.1 Manual span exception

`backend/observability/telemetry.py::_start_span()` tắt exception behavior mặc định của context manager. Trong `except Exception`, nó gọi `_record_safe_exception()` rồi bare `raise`.

`_record_safe_exception()` làm các bước:

1. lấy tên type đầy đủ của exception gốc, ví dụ module + class name;
2. tạo `SanitizedTelemetryError` với message chỉ là tên type;
3. gắn traceback của exception gốc vào wrapper bằng `.with_traceback(...)`;
4. `span.record_exception()` wrapper, kèm `error.type` và `exception.escaped=true`;
5. đặt span status `ERROR`, description là original qualified type;
6. đặt span attribute `error.type`;
7. `_start_span()` raise lại **exception gốc** cho caller.

Do đó:

- original exception type tồn tại trong custom `error.type` và status description;
- standard `exception.type` của event có thể là wrapper `SanitizedTelemetryError`, không phải original type;
- provider/user message gốc không được dùng làm event message/status;
- stack trace của manual span vẫn được ghi dựa trên traceback gốc, nên file paths/function names có thể xuất hiện;
- telemetry không nuốt business exception.

**[Test]** `test_workflow_records_sanitized_exception_and_error_status` xác nhận node lỗi và workflow parent đều có `ERROR`, đều có exception event, sentinel essay/key không xuất hiện, trong khi caller vẫn nhận exception gốc.

## 10.2 Propagation node → workflow → HTTP

Nếu một node raise:

1. node `_start_span()` record sanitized event/status, rồi raise gốc;
2. LangGraph invocation dừng/raise; các downstream node không chạy;
3. workflow `_start_span()` record cùng failure ở workflow level, rồi raise gốc;
4. endpoint không catch lỗi đó;
5. `_SanitizeUnhandledExceptionMiddleware` thay exception ở ASGI boundary;
6. FastAPI automatic instrumentation ghi server span lỗi bằng sanitized wrapper và response trở thành 500.

Một lỗi có thể vì thế tạo error signal ở node, workflow và HTTP server span. Đây không phải ba lỗi khác nhau; là ba abstraction boundary cùng phản ánh một failure.

Trong combined graph, nếu một nhánh raise, workflow invocation fail. Nhánh kia có thể đã hoàn thành hoặc đang bị runtime cancel tùy timing/LangGraph scheduling; code dự án không có catch/recovery để biến lỗi thành partial report. Không nên khẳng định mọi sibling luôn hoàn tất.

## 10.3 FastAPI automatic exception

Automatic instrumentor có exception handler riêng. Project đặt sanitizer middleware bên trong lớp OTel để exception handler chỉ thấy `SanitizedTelemetryError` với message là type an toàn. `from None` ngăn cause gốc được trình bày như chained cause. Automatic stack trace phản ánh wrapper đi qua middleware boundary, không giống cơ chế manual wrapper giữ explicit original traceback.

Khi telemetry disabled, sanitizer middleware không được cài. Vì vậy privacy của unhandled exception trong Uvicorn/application logs không được helper telemetry bảo vệ.

## 10.4 Gemini retry

`backend/tools/feedback_generator.py::get_feedback_for_score()` có loop retry riêng. Mỗi attempt gọi blocking provider qua `asyncio.to_thread(run_gemini)`, logger chỉ ghi attempt counts và exception **type**, sau đó sleep theo backoff. Manual `ielts.node.generate_feedback` bao toàn bộ dependency call, nên:

- không có span cho từng attempt;
- successful retry tạo một node span OK có duration gồm attempts + waits;
- nếu hết retries, exception cuối đi qua sanitizer node/workflow như trên;
- không có outbound HTTP span vì không có Google/HTTP client instrumentation.

# 11. Privacy and security

## 11.1 Data inventory

| Dữ liệu | Có được ghi vào trace hiện tại không? | Cơ chế bảo vệ xác nhận từ code | File liên quan |
|---|---|---|---|
| Essay/answer | Không được manual span ghi; HTTP body không capture. Query của grammar endpoint được redact | helper chỉ dùng allowlist metadata; FastAPI hook che query | `telemetry.py`, `ielts_graph.py`, `main.py` |
| IELTS question | Không | không truyền state/content vào `workflow_span` hoặc `node_span`; HTTP request body không capture | `orchestrator.py`, `ielts_graph.py` |
| Prompt Gemini | Không | prompt chỉ tồn tại trong feedback tool; không có span attribute/event cho prompt | `feedback_generator.py`, `telemetry.py` |
| Feedback/result | Không | node chỉ ghi tool name; report/state không đưa vào span | `ielts_graph.py` |
| API key | Không | không đọc/đưa key vào telemetry; exception message được sanitize | `feedback_generator.py`, `telemetry.py` |
| Raw `session_id` | Không | chỉ ghi `ielts.session.source=provided|generated` | `orchestrator.py`, `telemetry.py` |
| Hashed/pseudonymous session | Không tồn tại | project chưa triển khai correlation token | không có |
| Query string | Có attribute nhưng value bị thay bằng `[REDACTED]` khi query không rỗng; safe URL bỏ query | `_sanitize_server_request()`, `_safe_url()` | `telemetry.py` |
| Request/response headers | Không capture | regex `$^` không khớp; sanitize fields `.*` | `telemetry.py::instrument_fastapi()` |
| Client IP/address | Chỉ giá trị `[REDACTED]`; ports `0` | overwrite cả semantic attributes cũ/mới | `telemetry.py::_sanitize_server_request()` |
| User-agent | Chỉ `[REDACTED]` | overwrite `user_agent.original` và `http.user_agent` | cùng function |
| Provider exception message | Không trong manual spans; HTTP unhandled path được wrapper sanitize khi enabled | `_record_safe_exception()` và `_SanitizeUnhandledExceptionMiddleware` | `telemetry.py` |
| MongoDB URI | Không | không có Mongo instrumentation/attribute; URI chỉ dùng tạo client | `main.py` |

“Không trong trace” không có nghĩa là “không lưu ở đâu”: essay/question/feedback có thể nằm trong LangGraph SQLite checkpoint và optional MongoDB documents theo business design. Hai persistence đó nằm ngoài phạm vi telemetry privacy table.

## 11.2 Enforcement bằng code và convention

Control được **enforce bằng code**:

- manual spans chỉ nhận metadata đã chọn, không nhận state/payload;
- header capture bị vô hiệu tường minh;
- query URL, client identity và user-agent được overwrite;
- exception message được thay bằng type trước khi record;
- test quét toàn bộ span names, attributes, statuses và events để chắc sentinel content/key/session không xuất hiện ở các flow được test.

Control mới mang tính **convention/coverage hiện tại**, chưa phải enforcement toàn cục:

- không có API allowlist ngăn developer tương lai gọi `span.set_attribute("essay", ...)`;
- không có span processor cuối đường ống để scrub tất cả attributes/events;
- không có test cho mọi biến resource do operator tự cấu hình;
- `OTEL_RESOURCE_ATTRIBUTES` có thể do operator thêm tùy ý và SDK sẽ export, nên không được đặt secret ở đó;
- không có test hoặc redactor chung cho logs ngoài telemetry.

## 11.3 Rủi ro còn lại

- `backend/main.py::essay_process()` dùng `logger.exception(...)` khi MongoDB fail và truyền raw session value vào log. Đây **không phải span**, nhưng vẫn là privacy gap ở logging.
- `/grammar_correction` nhận answer qua query parameter. OTel span che query, nhưng Uvicorn access log, reverse proxy, browser history hoặc gateway ngoài project có thể vẫn ghi URL. Telemetry redaction không bảo vệ các hệ đó.
- Manual exception event giữ stack trace. Nó loại content message nhưng vẫn có file paths/function names; cần coi đó là operational metadata.
- Console exporter ghi ra stdout. Nếu stdout được ship đến centralized logging, retention/access control của log system vẫn phải được quản lý.
- Resource attributes do environment điều khiển không qua sanitizer.
- Không có pseudonymous session correlation. Nếu thêm, hash không salt hoặc token ổn định có thể trở thành high-cardinality identifier và vẫn có rủi ro linkage.

## 11.4 Cardinality

Attributes hiện tại chủ yếu bounded: workflow/node/tool names, `provided|generated`, `sqlite|injected`, booleans, redaction constants. `error.type` có tập hữu hạn theo exception classes. `service.instance.id` do SDK resource tạo là unique theo process instance; high-cardinality hơn nhưng là semantic resource identity thông thường.

`url.full` không chứa query, nhưng host/port/path vẫn có thể tăng cardinality nếu app nhận nhiều dynamic/unmatched paths. Các route chính là tĩnh. Raw session không được ghi nên tránh nguồn cardinality lớn nhất.

# 12. Disabled behavior

Với:

```env
OTEL_SDK_DISABLED=true
```

runtime chính xác là:

1. `backend.main` vẫn import toàn bộ module telemetry và OpenTelemetry API/SDK imports ở đầu file vẫn phải tồn tại.
2. `load_dotenv()` vẫn chạy; `initialize_telemetry()` vẫn được gọi.
3. `TelemetrySettings.from_environment()` đọc flag; `create_telemetry_runtime()` trả `TelemetryRuntime(enabled=False)` trước khi tạo provider/exporter.
4. `instrument_fastapi()` được gọi nhưng return ngay; không cài FastAPI instrumentation và không thêm sanitizer middleware.
5. `workflow_span()`/`node_span()` vẫn xuất hiện trong business code, nhưng `_start_span()` thấy không có tracer, chỉ `yield None`; helper **bỏ qua span hoàn toàn**, không xin một no-op span từ global provider.
6. Code bên trong mọi `with` vẫn chạy bình thường: Orchestrator, LangGraph, checkpoint, model dependencies và report không phụ thuộc span object.
7. `shutdown_telemetry()` vẫn chạy, đổi `_runtime` thành disabled và gọi no-op `TelemetryRuntime.shutdown()` vì không có provider.

Vì vậy successful business behavior không đổi. Ngoại lệ đáng chú ý là unhandled HTTP exception không được middleware riêng của project sanitize khi disabled; kết quả HTTP vẫn lỗi nhưng logging/test harness có thể thấy original exception.

**[Test]** `test_environment_can_disable_telemetry` tạo runtime disabled, đi qua `workflow_span()` và xác nhận exporter in-memory nhận zero spans. `test_invalid_disabled_flag_keeps_project_default` xác nhận flag sai quay về default disabled. Chưa có API-level test so sánh toàn bộ response của enabled và disabled mode.

# 13. Runtime walkthrough

Mô phỏng `POST /essay_process` với payload chỉ ký hiệu:

```json
{
  "question": "<redacted>",
  "answer": "<redacted>"
}
```

| Bước | Current span | Parent | `trace_id` | Code tạo/kết thúc và behavior |
|---:|---|---|---|---|
| 1 | chưa có local app span; có thể có extracted remote context | upstream nếu request mang `traceparent` | dùng upstream hoặc chưa có | FastAPI ASGI middleware trong instrumentor nhận request |
| 2 | `POST /essay_process` (`SERVER`) | remote parent hoặc none | giữ upstream hoặc tạo mới | automatic middleware tạo/make-current server span; hook redact HTTP metadata |
| 3 | server span | như trên | không đổi | `backend.main.essay_process()` gọi `orchestrator.process_essay()` |
| 4 | `ielts.workflow.combined` | server span | không đổi | `IELTSWritingOrchestrator.process_essay()` vào `workflow_span`; gọi `start()`, tạo/reuse session, `ainvoke()` với `thread_id` |
| 5 | lần lượt `validate_input`, `prepare_session` | workflow span | không đổi | node functions vào `node_span`; mỗi node end khi partial state update return |
| 6 | `score_essay` và `correct_grammar` trong hai async tasks | cả hai cùng workflow span | không đổi | combined graph fan-out; durations có thể overlap; BERT/T5 blocking work đi qua `to_thread` với context được copy |
| 7 | `generate_feedback` rồi `process_scores`; grammar có thể đã xong/chưa xong | workflow span | không đổi | feedback chỉ bắt đầu sau score; một feedback span bao mọi Gemini retry; processor chạy sau feedback |
| 8 | `build_report` | workflow span | không đổi | LangGraph join đợi `process_scores` và `correct_grammar`, rồi report node end |
| 9 | workflow span end, server span current trở lại | server span | không đổi | `ainvoke()` trả state; Orchestrator trả report; context manager end workflow |
| 10 | server span | upstream/none | không đổi | optional Mongo inserts chạy qua `to_thread`; không DB span; persistence failure bị endpoint catch và response vẫn tiếp tục |
| 11 | server span end sau response | upstream/none | không đổi | ASGI middleware ghi status/end server span; Batch processor đã enqueue các spans khi chúng lần lượt end |
| 12 | không còn request current span | — | trace vẫn được nhận diện trong exported records | worker của Batch processor gọi console hoặc OTLP exporter; request không chờ từng export |

Các node span có thể xuất hiện trên console trước workflow/HTTP span vì end sớm hơn. Ghép cây bằng `trace_id`, `span_id` và `parent_id`, không bằng thứ tự output.

# 14. Local trace-reading guide

Các bước sau dùng Windows PowerShell, thư mục `venv` chuẩn của project và không sửa `.env`.

## 14.1 Bật console tracing cho một process

Trong terminal backend ở project root:

```powershell
$env:OTEL_SDK_DISABLED = "false"
$env:OTEL_TRACES_EXPORTER = "console"
$env:OTEL_SERVICE_NAME = "ielts-writing-agent-local"
.\run_backend.ps1 -NoReload
```

Dùng `-NoReload` để chỉ có một process, giúp tránh trace output lặp/khó đọc do reload worker. Environment của shell có precedence vì `load_dotenv()` mặc định không override biến đã có. Telemetry chỉ đọc lúc import, nên phải restart backend sau khi đổi biến.

## 14.2 Request an toàn không chạy model

Trong terminal thứ hai:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/health"
```

Bạn sẽ thấy một server span tên gần `GET /health`. Request này kiểm tra automatic instrumentation nhưng không tạo workflow/node span và không gọi model/API.

## 14.3 Quan sát full workflow bằng dữ liệu tổng hợp

Chỉ thực hiện khi local models và Gemini test credentials đã được cấu hình, vì endpoint này **sẽ gọi tool thật**:

```powershell
$body = @{
    question = "<synthetic-test-question>"
    answer   = "<synthetic-test-answer>"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/essay_process" `
    -ContentType "application/json" `
    -Body $body
```

Không dùng essay, prompt hay credential thật trong payload/terminal history. Trong quá trình tạo tài liệu này, lệnh full workflow trên **không được chạy**.

## 14.4 Cách đọc output

1. Tìm span `POST /essay_process`, ghi lại `trace_id` và `span_id`.
2. Tìm `ielts.workflow.combined` có cùng `trace_id`, `parent_id` trỏ tới server `span_id`.
3. Tìm node spans cùng `trace_id`; `parent_id` của chúng trỏ tới workflow `span_id`.
4. So sánh `start_time`/`end_time` của `score_essay` và `correct_grammar`. Khoảng thời gian giao nhau chứng minh concurrency; chỉ so duration không đủ chứng minh overlap.
5. So latency từng node. `generate_feedback` duration có thể gồm retry waits; hiện không có per-attempt span.
6. Span lỗi có status `ERROR`, `error.type` và exception event. Không kỳ vọng provider message trong event.

Batch export có thể làm các JSON records in ra không theo cây. Hãy lọc/so sánh IDs thay vì đọc tuần tự.

## 14.5 Tắt tracing

Dừng backend, rồi trong terminal backend:

```powershell
$env:OTEL_SDK_DISABLED = "true"
Remove-Item Env:OTEL_TRACES_EXPORTER -ErrorAction SilentlyContinue
Remove-Item Env:OTEL_SERVICE_NAME -ErrorAction SilentlyContinue
.\run_backend.ps1 -NoReload
```

Phải restart vì runtime/provider đã được cố định khi import `backend.main`.

# 15. Design review

## 15.1 Điểm tốt nên giữ

- **Boundary hợp lý.** Setup/lifecycle ở `main`, workflow span ở Orchestrator, node span ở graph. Tool code không phải biết HTTP.
- **Provider nhất quán.** FastAPI và manual spans dùng cùng explicit provider, tạo cây đúng mà không phụ thuộc global provider.
- **Tracing optional.** Disabled path không rải `if telemetry` vào business logic và không tạo provider/exporter.
- **Dependency injection test tốt.** In-memory exporter + mocked graph tools xác nhận hierarchy/privacy mà không tải model hay gọi Gemini.
- **Privacy mặc định tốt.** Payload không thành attributes, header capture tắt, network identity/query redacted, exception message sanitize.
- **Batch processor đúng hướng cho runtime.** Network exporter không nằm trên request critical path.
- **Cleanup lồng `finally`.** Telemetry shutdown được bảo đảm sau các cleanup khác khi lifespan đã đi vào `try`.

## 15.2 Coupling và hạn chế

- Module-global `_runtime` làm helper dễ dùng nhưng tạo shared mutable state. Parallel test runtimes hoặc reconfiguration động có thể can thiệp nhau.
- Provider không global là chủ ý hợp lệ, nhưng automatic instrumentation mới phải được truyền explicit provider; nếu developer thêm library instrumentation theo cách mặc định, traces có thể tách/no-op.
- `instrument_fastapi()` không idempotent hoàn toàn vì custom middleware được add trước guard của instrumentor.
- `workflow_span()` hard-code `checkpoint.enabled=true` và backend label từ ownership (`sqlite|injected`), không phải introspection backend thực. Một injected SQLite saver vẫn được label `injected`.
- Ba report nodes dùng cùng span name; đủ khi nhìn parent workflow, nhưng khó phân tích độc lập theo report variant.
- Không có spans cho model load, queue wait, inference riêng, Gemini attempts, checkpoint I/O hoặc MongoDB. Hiện granularity phù hợp cho “workflow/node latency”, nhưng chưa đủ chẩn đoán sâu provider/database.
- Mongo persistence nằm ngoài workflow span. Điều này phân tách compute orchestration rõ, nhưng nếu người đọc hiểu workflow span là toàn endpoint latency thì sẽ bỏ sót persistence.
- Setup tại module import thuận tiện, nhưng import side effect khiến tests/reload/multi-worker tạo provider sớm. Mỗi Uvicorn worker có provider/Batch worker riêng; console output có thể xen kẽ.
- Startup failure trước `lifespan` try có cleanup gap đã nêu.

## 15.3 Naming và số lượng spans

Naming `ielts.workflow.*` và `ielts.node.*` nhất quán, low-cardinality, dễ query. `ielts.tool.name` cũng bounded. Số span hiện tại không quá nhiều: mỗi request có 1 HTTP + 1 workflow + 3/5/7 nodes.

Điểm có thể cải thiện sau khi có nhu cầu thực tế:

- phân biệt `build_evaluation_report`, `build_grammar_report`, `build_combined_report` bằng attribute bounded thay vì tăng tên tùy ý;
- thêm child span cho `model.load` và `model.inference` nếu cần tách cold start khỏi inference;
- thêm per-attempt Gemini spans với attempt number bounded, nhưng tuyệt đối không gắn prompt/key/message;
- instrument PyMongo/HTTP client chỉ sau khi review semantic attributes/privacy, vì automatic instrumentation có thể thu thập endpoint, statement hoặc headers ngoài dự kiến.

## 15.4 Processor cho local và production

Console + Batch hợp lý để học local. OTLP + Batch là nền tảng đúng cho production, nhưng chưa đủ một hệ observability production: cần Collector/backend, TLS/auth, sampling, queue/export monitoring và retention policy. Nếu thêm Collector, phần business code không cần đổi; chủ yếu cấu hình `OTEL_TRACES_EXPORTER=otlp`, endpoint đầy đủ và security của transport. Có thể cân nhắc OTLP endpoint trỏ Collector sidecar/agent thay vì backend vendor trực tiếp.

## 15.5 Privacy hardening tương lai

Priority hợp lý:

1. chuyển grammar input khỏi query sang request body để giảm leakage ngoài OTel;
2. bỏ raw session khỏi Mongo failure log hoặc dùng correlation token đã review;
3. thêm allowlist/scrubbing exporter/processor test cho attributes/events/resource;
4. kiểm thử HTTP error privacy ở enabled/disabled modes và Uvicorn logging;
5. quy định rõ resource attributes không chứa secrets.

## 15.6 Metrics và structured logging

Theo `AGENTS.md`, nên ổn định span names/privacy trước khi thêm metrics. Metrics hữu ích sau khi có câu hỏi vận hành rõ: request latency/error rate, node duration, retry count, checkpoint latency. Không gắn session/question vào metric labels vì cardinality/privacy.

Structured logging nên lấy current `trace_id`/`span_id` tại thời điểm log và thêm dưới dạng fields chuẩn, không đưa raw session/content. Khi tracing disabled hoặc context invalid, fields nên vắng/null chứ không tự tạo ID giả. Trước khi correlation, cần sửa log Mongo raw session và thống nhất redaction policy giữa logs và traces.

# 16. Common misunderstandings

1. **“Workflow span là trace root.”** Chỉ đúng khi gọi Orchestrator ngoài HTTP mà không có active span. Trong API, parent của nó là HTTP server span.
2. **“Graph edge tạo parent-child span.”** Không. Mọi node hiện là direct child của workflow. Edges quyết định scheduling/state, không quyết định OTel parent.
3. **“BERT và T5 song song thì khác trace.”** Không. Chúng có cùng trace/workflow parent nhưng span IDs khác.
4. **“Có `ielts.tool.name=gemini_feedback` nghĩa là có outbound HTTP span.”** Không. Đây chỉ là attribute của node span.
5. **“Console exporter luôn đồng bộ.”** Exporter tự ghi console, nhưng normal runtime đặt nó sau Batch processor nên request không gọi export trực tiếp.
6. **“Project dùng global tracer provider.”** Không. Nó tạo private SDK provider và truyền explicit cho FastAPI/manual tracer.
7. **“`OTEL_SDK_DISABLED=true` làm module OTel không được import.”** Không. Imports/setup function vẫn chạy; chỉ không tạo provider/instrumentation/spans.
8. **“Disabled mode hoàn toàn giống enabled mode.”** Successful business path giống; unhandled ASGI exception không qua sanitizer middleware khi disabled.
9. **“Redact trace nghĩa là dữ liệu không thể rò ở đâu khác.”** Không. Query có thể nằm ở proxy/access log; checkpoint/Mongo lưu business data; application log có policy riêng.
10. **“Reuse `session_id` sẽ reuse `trace_id`.”** Không. Session/thread thuộc LangGraph; trace thuộc request propagation.
11. **“Node error bị telemetry nuốt.”** Manual helper record rồi raise gốc. Chỉ ở HTTP boundary exception được đổi sang sanitized wrapper trước automatic recording.
12. **“Không thấy span nghĩa là operation không chạy.”** Mongo inserts, checkpoint I/O và provider HTTP vẫn có thể chạy nhưng chưa được instrument.

## Documentation mismatches

Không thấy mâu thuẫn trực tiếp giữa `README.md`, `AGENTS.md` và code về default disabled, console/OTLP choices, workflow/node spans hay redaction. Có các chỗ cần đọc chính xác hơn wording tài liệu:

- `AGENTS.md` gọi workflow span là “top-level application span”. Trong HTTP trace thực tế nó là child của automatic server span; “top-level” chỉ đúng trong subtree ứng dụng.
- Sơ đồ tài liệu liệt kê BERT/T5/Gemini/processor/report dưới LangGraph, nhưng code chỉ tạo **node-level span** bao chúng; không có model/provider child spans riêng.
- Tài liệu nói không ghi exception messages. Manual path enforce trực tiếp; automatic HTTP path đạt điều đó nhờ middleware wrapper khi tracing enabled. Khi tracing disabled, middleware này không tồn tại và claim không thể mở rộng sang Uvicorn/application logs.
- `.env.example` có `OTEL_RESOURCE_ATTRIBUTES` và `OTEL_TRACES_SAMPLER`, nhưng `TelemetrySettings` không parse chúng. Chúng vẫn được SDK phiên bản hiện tại đọc gián tiếp; behavior này thuộc SDK.
- Tài liệu nói query/client/user-agent được redact và code/test khớp. Tuy nhiên protection chỉ áp dụng OTel spans, không phải mọi access/proxy log.

# 17. Keywords for further study

- OpenTelemetry API vs SDK
- `TracerProvider`, `Tracer`, `Span`, `SpanKind`
- active context và `contextvars`
- W3C Trace Context, `traceparent`, remote parent
- `trace_id`, `span_id`, parent span
- semantic conventions và stability opt-in
- FastAPI/ASGI instrumentation
- server request hook và middleware ordering
- `Resource`, `service.name`, `service.instance.id`
- head sampling, parent-based sampling
- `SimpleSpanProcessor`, `BatchSpanProcessor`
- OTLP/HTTP protobuf, Collector, trace backend
- force flush, graceful shutdown, queue backpressure
- exception event, span status, escaped exception
- telemetry data minimization, redaction, cardinality
- context propagation qua `asyncio.Task` và `asyncio.to_thread`
- instrumentation scope/name/version
- trace-log correlation
- RED method: rate, errors, duration
- exemplars và metrics (sau khi trace/privacy ổn định)
