# Bàn giao cho backend: event, API, WebSocket, webhook

Hợp đồng giữa FireWatch và backend. Đây là tài liệu duy nhất cho phần này; mọi thay đổi
hợp đồng sửa tại đây. Nguồn gốc: README của `Model-Mat-Pho-` @ `afa5a70` (mục 3, 3b,
4), đã đối chiếu lại với `src/firewatch/alerts.py` và `server.py`.

## 1. Event

Một alert là một event. Schema top-level **không tự đổi**; chỉ được thêm trường mới.

```json
{
  "event_id": "uuid", "camera_id": "cam01", "context": "HAM|TRET|NGOAI",
  "severity": "WARNING|CRITICAL", "verification": "VERIFIED|UNVERIFIED|SUPPRESSED",
  "started_at": "ISO8601", "video_ts_sec": 12.0,
  "boxes": [{"cls": "fire", "conf": 0.87, "xyxy": [120, 80, 260, 210]}],
  "vlm": {"is_fire": true, "is_smoke": true, "confidence": 0.92,
          "description_vi": "...", "fire_type": "UNCONTROLLED|CONTROLLED|UNKNOWN|null"},
  "snapshot_path": "events/20261102_120000_xxxxxxxx.jpg"
}
```

- `severity` do detector quyết: CRITICAL khi đủ `voting.k_fire` heartbeat có box lửa,
  ngược lại là WARNING. VLM **không** hạ severity.
- `started_at` là giờ thật của khung hình xác nhận cháy, không phải lúc VLM trả lời.
- `vlm` là `null` khi VLM tắt, lỗi hay hết giờ.
- `vlm.fire_type` chỉ được hỏi khi `context = NGOAI`; với HAM và TRET luôn là
  `UNCONTROLLED`. `CONTROLLED` **không** đổi `verification` hay severity: event vẫn phát,
  và chỉ người trực được bỏ qua.

### `verification`

| VLM trả lời | `verification` | Có phát? |
|---|---|---|
| thấy lửa hoặc khói | `VERIFIED` | có |
| không thấy cả hai | `SUPPRESSED` | có theo mặc định; `alerts.notify_suppressed: false` thì chỉ ghi đĩa |
| lỗi, timeout, thiếu key, VLM tắt | `UNVERIFIED` | **có** (fail-open: thà báo thừa) |

### Cập nhật cùng `event_id`

- Alert chờ VLM tối đa `vlm.grace_s` (mặc định 2 s). Chưa có kết quả thì event được phát
  ngay với `UNVERIFIED`.
- Khi kết quả về, **cùng `event_id`** được cập nhật (`verification`, `vlm`):
  - file JSON ghi đè tại chỗ;
  - WebSocket nhận `event_update`;
  - webhook được POST lại.
- Backend phải **upsert theo `event_id`**, không coi mỗi lần nhận là một sự cố mới.

### Xác minh giả lập

Khi chạy `vlm.provider=mock`:
- `GET /` và `GET /health` trả `vlm_provider: "mock"`, và `GET /` có thêm
  `vlm_is_mock: true`;
- `description_vi` luôn có tiền tố `[mock]`.

App nên hiện cờ này để không ai tưởng event đã được xác minh thật.

## 2. REST và WebSocket (`python -m firewatch serve`)

| Endpoint | Việc |
|---|---|
| `GET /events?limit=50` | danh sách event, mới nhất trước; `limit=0` là tất cả, âm bị từ chối 422 |
| `GET /events/{id}` | một event; 404 nếu không có |
| `POST /events/{id}/ack` | người trực trả lời: body `{"action": "confirm" \| "dismiss_controlled" \| "watch", "note": "..."}`; 404 nếu không có event, 422 nếu action sai |
| `GET /events/{id}/ack`, `GET /acks` | ack của một event (`null` nếu chưa có) và tất cả ack |
| `GET /snapshots/<file>` | ảnh keyframe trong thư mục event |
| `POST /webhook-test` | backend gửi JSON bất kỳ, nhận lại body và một `sample_event` đúng schema |
| `GET /health` | xem dưới |
| `GET /console` | trang người trực (HTML tĩnh) |
| `GET /` | thông tin dịch vụ và danh sách endpoint |
| `WS /ws` | message realtime, xem dưới |

Message trên `WS /ws`:

| `type` | Khi nào | Trường thêm |
|---|---|---|
| `hello` | ngay khi nối | `events_so_far` |
| `event` | alert mới | `event` |
| `event_update` | cập nhật cùng `event_id` (kết quả VLM, nhắc lại) | `event`; `reason: "escalation"` khi gửi lại CRITICAL chưa ai trả lời; `reason: "verifier"` khi object `verifier` đổi trạng thái (cờ `verifier.ben_vung` bật, mục 5); không có `reason` khi là cập nhật VLM lúc cờ tắt |
| `ack` | người trực bấm nút | `ack` |

`GET /health`:
- Trả `200 {"status": "ok", "pipeline": {...}, "vlm_provider": "..."}` khi pipeline còn
  nhịp.
- Trả `503` khi `status` là `stale` (quá lâu không có heartbeat) hoặc `dead` (pipeline lỗi,
  hoặc nguồn live kết thúc).
- `pipeline` gồm: `heartbeats`, `alerts`, `last_heartbeat_age_s`, `uptime_s`,
  `source_live`, `error`.
- Cờ `verifier.ben_vung` bật thì có thêm khối `verifier` (mục 5); các trường trên không
  đổi.

## 3. Người trực và nhắc lại

- Ack lưu ở `events/acks.json`, tách khỏi event, nên schema event không đổi.
- `confirm` và `dismiss_controlled` tắt việc nhắc `STILL_BURNING` của track tương ứng.
  `watch` không tắt gì.
- Leo thang severity, hoặc cháy lại sau khi đã tắt, vẫn được báo. Chỉ con người được bỏ
  qua một cảnh báo.
- Event CRITICAL chưa ai trả lời sau `alerts.escalation_s` (mặc định 120 s, 0 = tắt)
  được gửi lại cùng `event_id` qua WebSocket và webhook, lặp mỗi chu kỳ cho tới khi có
  người trả lời.
- `dismiss_controlled` xuất keyframe sạch, ảnh đã vẽ box và JSON metadata vào
  `alerts.hitl_negatives_dir`, để làm hard negative.

## 4. Webhook

Hợp đồng đã chốt với đội backend ngày 2026-11-07.

| Mục | Giá trị |
|---|---|
| URL | do backend cung cấp, đặt vào `FIREWATCH_WEBHOOK_URL` trong `.env`. Không đặt thì FireWatch không gửi webhook |
| Phương thức | `POST`, `Content-Type: application/json` |
| Xác thực | token đặt vào `FIREWATCH_WEBHOOK_TOKEN`. Có token thì gửi **cả hai** header với cùng giá trị: `Authorization: Bearer <token>` và `X-Internal-Secret: <token>`. Token rỗng hoặc chưa đặt thì không gửi header xác thực nào |
| Payload | event **đầy đủ** đúng schema mục 1, không đổi, không cắt bớt trường |
| Cập nhật | mọi lần gửi lại cùng `event_id` (event đã cập nhật) đi **cùng URL đó** với cùng payload và header. Backend upsert theo `event_id` |
| Không dùng | các endpoint `/internal/ai/verifying` và `/internal/ai/suppressed` của backend. Trạng thái xác minh và `SUPPRESSED` đã nằm trong event (`verification`, `vlm`, và `verifier` khi bật cờ) |

Bên gửi:
- Gửi trên thread riêng, không chặn pipeline.
- Có ba trường hợp gửi lại cùng `event_id`: cập nhật VLM, nhắc lại CRITICAL, và object
  `verifier` đổi trạng thái (mục 5, khi bật cờ).
- Lỗi 4xx (trừ 408 và 429) không retry, vì gửi lại cũng vậy. Lỗi 5xx và lỗi mạng retry
  theo `alerts.webhook_retries`.
- Backend nên trả 2xx ngay khi đã nhận, rồi mới xử lý.

Test: `tests/test_webhook_hop_dong.py` dựng một backend giả trên localhost, kiểm đủ hai
header và payload là event đầy đủ.

## 5. Verifier bền vững (sau cờ, mặc định tắt)

Thiết kế ở `docs/decisions/2026-11-07-verifier-ben-vung.md`.

**Trạng thái hiện tại.** Đã làm đủ theo ADR trên nhánh `FireWatch-AI`: trạng thái,
schema, config; hàng chờ và ngân sách nền (`PENDING` ở 2 s, `VLM_TIMEOUT` ở 10 s, độc
lập heartbeat); cầu dao; khối `verifier` trên `/health`; `reason: "verifier"` trên
WebSocket; console người trực. Cờ `verifier.ben_vung` mặc định tắt cho tới khi chủ repo
chạy thử và chốt.

Khi cờ tắt, hoặc config không có khối `verifier`, event giữ đúng schema mục 1 và trường
`verifier` không xuất hiện.

### Object `verifier` trong event

Khi cờ bật, event có thêm object:

```json
"verifier": {"status": "PENDING|VERIFIED|REJECTED|VLM_TIMEOUT|VLM_ERROR|VLM_OFF",
             "needs_human_check": true, "latency_ms": 2100, "reason": "cho_vlm"}
```

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `status` | enum | `PENDING`: đã phát, VLM chưa trả lời. `VERIFIED` / `REJECTED`: VLM thấy / không thấy lửa, khói. `VLM_TIMEOUT`: quá ngân sách 10 s. `VLM_ERROR`: VLM lỗi. `VLM_OFF`: không gọi VLM (tắt, thiếu key, cầu dao mở) |
| `needs_human_check` | bool | `true` khi và chỉ khi `status` là `VLM_TIMEOUT`, `VLM_ERROR`, `VLM_OFF`: người trực phải tự nhìn ảnh |
| `latency_ms` | int \| null | thời gian từ lúc Voting quyết tới lúc VLM trả lời; `null` khi không có câu trả lời |
| `reason` | str \| null | mã ngắn: `cho_vlm`, `timeout`, `qua_han_hang_cho`, `http_429`, `http_4xx`, `http_5xx`, `loi_mang`, `loi_phan_tich`, `cau_dao_mo`, `vlm_tat`. Không bao giờ chứa nội dung lỗi thô hay body HTTP |

- `verification` cũ vẫn được điền theo bảng ánh xạ trong ADR, nên client cũ không phải đổi:
  - `PENDING`, `VLM_TIMEOUT`, `VLM_ERROR`, `VLM_OFF` → `UNVERIFIED`;
  - `REJECTED` → `SUPPRESSED`.
- `severity` không bao giờ đổi theo `verifier`; `REJECTED` không gỡ cảnh báo.
- Mỗi `event_id` nhận nhiều nhất một `created` và một `updated` của verifier; `updated`
  không bao giờ đến trước `created`. Sau `VLM_TIMEOUT`, kết quả VLM đến muộn bị bỏ,
  không có `updated` nào nữa.
- Khi `verifier` đổi trạng thái, event được đẩy lại cùng `event_id` qua WebSocket
  (`event_update`, `reason: "verifier"`) và webhook. Việc đẩy này không phụ thuộc
  `notify_suppressed`.

### App hiển thị thế nào

- `needs_human_check = true`: hiện nhãn rõ và dòng "Xác minh tự động không khả dụng,
  cần người xác thực". Console `/console` làm đúng như vậy; ba nút và leo thang giữ
  nguyên.
- `PENDING`: hiện "đang xác minh"; `VERIFIED` / `REJECTED`: hiện kết luận của VLM, nhưng
  cảnh báo `REJECTED` vẫn phải hiện, vì chỉ người trực được bỏ qua.
- Dòng thời gian của một sự cố: `created` lúc 2 s (hoặc sớm hơn nếu VLM trả lời kịp),
  `updated` chậm nhất lúc 10 s. App không cần đặt timeout riêng.

### Khối `verifier` trên `GET /health`

Chỉ có khi cờ bật; các trường cũ của `/health` không đổi.

```json
"verifier": {"breaker": "closed|open|half_open", "breaker_opens": 0, "queued": 0,
             "window_s": 600, "requests_in_window": 12,
             "answered_ratio_in_window": 0.833,
             "latency_p50_ms": 4100, "latency_p95_ms": 8900, "vlm_off_total": 0}
```

| Trường | Ý nghĩa |
|---|---|
| `breaker`, `breaker_opens` | trạng thái cầu dao và số lần mở từ lúc khởi động. `open`: không gọi VLM, mọi event là `VLM_OFF`; `half_open`: đang cho một lượt gọi thử |
| `queued` | số cảnh báo đang chờ worker gọi VLM (tối đa `verifier.hang_cho_toi_da`) |
| `requests_in_window` | số yêu cầu xác minh có trạng thái cuối trong `window_s` giây gần nhất |
| `answered_ratio_in_window` | phần trong đó VLM trả lời kịp ngân sách (`VERIFIED` / `REJECTED`); `null` khi chưa có yêu cầu. Giảm là dấu hiệu VLM chậm, hàng chờ đầy hoặc cầu dao mở |
| `latency_p50_ms`, `latency_p95_ms` | độ trễ từ lúc Voting quyết tới lúc VLM trả lời, của các câu trả lời kịp trong cửa sổ; `null` khi không có |
| `vlm_off_total` | số event đã nhận `VLM_OFF` từ lúc khởi động |
