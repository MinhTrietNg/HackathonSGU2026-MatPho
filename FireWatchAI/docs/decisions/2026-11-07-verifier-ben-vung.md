# ADR 2026-11-07: Verifier bền vững (hàng chờ, ngân sách nền, cầu dao)

Trạng thái: đề xuất, sau cờ `verifier.ben_vung` (mặc định tắt).

## Bối cảnh

Pipeline FireWatch: Video Source → Heartbeat → Detector → Voting → Verifier (VLM) →
Event Store. Hiện tại khi Voting quyết, Verifier được gọi trên một `ThreadPoolExecutor`
(`vlm.max_workers`, hàng chờ không giới hạn), cảnh báo chờ tối đa `vlm.grace_s` (2 s)
rồi phát `created` với `verification = UNVERIFIED` nếu VLM chưa trả lời; kết quả về sau
được vá vào cùng `event_id` bằng `updated`.

Các điểm yếu đã thấy khi đọc code:

- Event không phân biệt "đang chờ VLM" với "VLM hỏng": cả hai là `UNVERIFIED`, `vlm = null`.
  Người trực không biết khi nào phải tự xác thực.
- Không có giới hạn thời gian cho kết quả muộn: với `timeout_s = 15`, `retries = 1`, một
  yêu cầu giữ worker tới khoảng 30 s; `updated` có thể đến rất trễ hoặc không mang thông
  tin gì (UNVERIFIED → UNVERIFIED).
- Hạn grace chỉ được kiểm tra mỗi heartbeat: nguồn video treo thì `updated` cũng treo.
- API chết hoặc bị giới hạn (429) vẫn bị gọi đều đặn, làm đầy hàng chờ.
- `notify_suppressed = false` chặn cả `updated` mang SUPPRESSED: app thấy cảnh báo chờ
  mà không bao giờ nhận kết quả.

## Quyết định

### Ba nguyên tắc

1. **Không giữ cảnh báo chờ VLM.** Cảnh báo phát không muộn hơn cửa sổ đồng bộ
   `vlm.grace_s`, dù VLM chậm, lỗi hay tắt.
2. **VLM không hạ mức, không gỡ cảnh báo.** Mức độ (`severity`) do Voting quyết. Kết quả
   `REJECTED` chỉ ghi trạng thái.
3. **Chỉ con người được bỏ qua.** Bỏ qua cảnh báo chỉ qua ack của người trực
   (`dismiss_controlled`); ba nút và leo thang giữ nguyên.

### Cờ và tương thích

- Mọi hành vi dưới đây nằm sau `verifier.ben_vung`, mặc định `false`. Thiếu khối
  `verifier` trong `config.yaml` thì chạy như cờ tắt.
- Cờ tắt: hành vi, log và JSON của event y hệt hiện tại (trường mới không xuất hiện trong
  JSON). Có test snapshot chứng minh.
- Schema chỉ **thêm** trường. Không đổi tên, kiểu, hay bỏ trường nào.

### Trường mới trong event

Schema hiện có đặt tên bằng tiếng Anh (`event_id`, `verification`, `started_at`...), nên
trường mới cũng dùng tiếng Anh để nhất quán:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `verifier.status` | `PENDING` \| `VERIFIED` \| `REJECTED` \| `VLM_TIMEOUT` \| `VLM_ERROR` \| `VLM_OFF` | trạng thái xác minh tự động |
| `verifier.needs_human_check` | bool | `true` khi `VLM_TIMEOUT`, `VLM_ERROR`, `VLM_OFF` |
| `verifier.latency_ms` | int \| null | thời gian VLM trả lời, null nếu không có câu trả lời |
| `verifier.reason` | str \| null | mã ngắn, không bao giờ chứa body HTTP hay chuỗi lỗi thô |

`verification` giữ nguyên Literal cũ, ánh xạ: `PENDING` → `UNVERIFIED`, `VERIFIED` →
`VERIFIED`, `REJECTED` → `SUPPRESSED`, `VLM_TIMEOUT` / `VLM_ERROR` / `VLM_OFF` →
`UNVERIFIED`.

Mã `reason` dự kiến: `cho_vlm`, `timeout`, `qua_han_hang_cho`, `http_429`, `http_4xx`,
`http_5xx`, `loi_mang`, `loi_phan_tich`, `cau_dao_mo`, `vlm_tat`.

### Ba mốc thời gian

Đồng hồ tính từ lúc Voting quyết (0 s):

- **Cửa sổ đồng bộ (`vlm.grace_s`, 2 s).** VLM trả lời trong cửa sổ thì `created` mang luôn
  kết quả, không có `updated`. Hết cửa sổ thì phát `created` với `PENDING`. Thời điểm phát
  cảnh báo trên trục video giống như khi cờ tắt.
- **Ngân sách nền (`verifier.ngan_sach_s`, 10 s).** VLM tiếp tục chạy nền; có kết quả thì
  phát `updated` với `VERIFIED`, `REJECTED` hoặc `VLM_ERROR`.
- **Quá ngân sách.** Phát `updated` với `VLM_TIMEOUT`, `needs_human_check = true`. Kết quả
  đến muộn bị bỏ, không phát thêm.

Mỗi `event_id` có đúng một trạng thái cuối; mọi chuyển trạng thái đi qua một khoá, nên
`updated` không bao giờ được phát trước `created` của nó.

### Không phụ thuộc heartbeat

Cửa sổ đồng bộ và ngân sách nền do một luồng hẹn giờ riêng (đồng hồ tiêm được) và
callback của future quyết định, không do vòng heartbeat. Nguồn video treo thì
`updated` vẫn phát đúng hạn. Luồng chính của pipeline không bao giờ bị chặn.

### Timeout mỗi lượt gọi khi cờ bật

Khi cờ bật, timeout của lượt gọi VLM không cố định mà bằng **ngân sách còn lại tại lúc bắt
đầu gọi trừ 0,5 s**, `retries = 0`. Nếu giá trị đó nhỏ hơn 1 s thì không gọi, chuyển thẳng
`VLM_TIMEOUT` với reason `qua_han_hang_cho`. Ví dụ: gọi ngay ở 0 s thì timeout 9,5 s; gọi ở
6 s (đã chờ hàng) thì timeout 3,5 s; ở 9 s thì không gọi.

Lý do: worker phải được giải phóng trước khi ngân sách 10 s hết; nếu giữ 15 s × 2 lượt như
cấu hình cũ thì mỗi yêu cầu chậm chiếm worker tới 30 s sau khi event đã bị đánh
`VLM_TIMEOUT`, và hàng chờ đầy nhanh. Khoảng 0,5 s chừa lại để lượt gọi kết thúc và kết quả
kịp ghi trước mốc ngân sách. Cờ tắt thì `vlm.timeout_s` và `vlm.retries` giữ nguyên.

### Hàng chờ

- Giới hạn `verifier.hang_cho_toi_da` (8) mục đang chờ gọi, khoá theo `event_id`. Yêu cầu
  mới cùng `event_id` thay keyframe cũ, không xếp thêm.
- Chỉ có **một hạn duy nhất**: ngân sách `ngan_sach_s`, tính từ lúc Voting quyết. Không
  có hạn riêng cho hàng chờ. Khi hết hạn, event nhận `VLM_TIMEOUT` với reason:
  - `qua_han_hang_cho` nếu chưa gọi VLM (mục bị rút khỏi hàng, không gọi nữa);
  - `timeout` nếu đã gọi mà chưa có kết quả.
- Hàng đầy: bỏ mục cũ nhất, phát `VLM_TIMEOUT` với reason `qua_han_hang_cho`.
- Worker lấy việc từ hàng; số worker = `vlm.max_workers`.

### Cầu dao

- Đếm theo yêu cầu xác minh (không theo từng lần retry). Lỗi, 429 và hết ngân sách đều
  tính là thất bại.
- `verifier.cau_dao.loi_lien_tiep` (3) thất bại liên tiếp → mở trong
  `verifier.cau_dao.mo_s` (60 s). Khi mở: không gọi VLM, event phát với `VLM_OFF`,
  `needs_human_check = true`, reason `cau_dao_mo`.
- Hết `mo_s`: nửa mở, cho đúng một lượt gọi thử (các yêu cầu khác trong lúc đó nhận
  `VLM_OFF`). Thành công thì đóng, thất bại thì mở lại.

### Kênh phát

- Cờ bật: `updated` của verifier luôn được đẩy qua WebSocket và webhook, bỏ qua
  `alerts.notify_suppressed`. WebSocket gửi `{"type": "event_update", "reason":
  "verifier", ...}` để không lẫn với `"escalation"`.
- `/health` thêm khối `verifier` (chỉ khi cờ bật): trạng thái cầu dao, số mục trong hàng,
  tỉ lệ trả lời kịp ngân sách trong 10 phút gần nhất, p50 / p95 độ trễ VLM trong cửa sổ đó,
  số lần `VLM_OFF`. Các trường cũ không đổi.
- Console HITL: event có `needs_human_check = true` hiện nhãn rõ và dòng "Xác minh tự động
  không khả dụng, cần người xác thực". Ba nút và leo thang giữ nguyên.

## Hệ quả

- App và backend phân biệt được "đang chờ", "đã xác minh", "VLM không khả dụng"; trường
  hợp cuối báo rõ người trực phải tự nhìn.
- Mỗi cảnh báo có kết luận tự động chậm nhất sau `ngan_sach_s`, kể cả khi nguồn treo.
- API chết không bị gọi dồn; sau `mo_s` hệ thống tự thử lại.
- Lượt gọi được gọi ngay có timeout 9,5 s, nhỉnh hơn p95 đo ngày 03/11/2026 (8,9 s với
  gemini-3.5-flash-lite); lượt gọi đã chờ hàng có timeout ngắn hơn. Khi cờ bật, một phần
  yêu cầu chậm hoặc phải chờ hàng sẽ thành `VLM_TIMEOUT` thay vì được xác minh muộn. Đây
  là đánh đổi có chủ ý: kết luận đúng hạn quan trọng hơn kết luận muộn. Tỉ lệ trả lời kịp
  trên `/health` dùng để theo dõi đánh đổi này.
- Hiện mỗi cảnh báo của Voting có `event_id` riêng, nên việc thay keyframe theo `event_id`
  chỉ xảy ra khi cùng một `event_id` được gửi xác minh lại; chưa gộp theo track.
- Backend nhận thêm một object `verifier`; client cũ bỏ qua được vì không trường nào đổi.

## Không làm

- Không để VLM hạ mức, gỡ, hay tự bỏ qua cảnh báo.
- Không đổi `voting.py`, `detector.py`, `sources.py`, `evalkit.py`.
- Không đổi tên, kiểu hay ý nghĩa của trường cũ; không thêm giá trị mới vào `verification`.
- Không tăng timeout mỗi lượt gọi; không thêm nhà cung cấp VLM dự phòng.
- Không gộp xác minh theo track, không xác minh lại sau khi đã có trạng thái cuối.
- Không phát `created` ở 0 s (ngay khi Voting quyết) thay vì cuối cửa sổ đồng bộ 2 s. Đây là
  lựa chọn tương lai, cần backend đồng ý vì nó đổi thời điểm phát so với hợp đồng hiện tại.
- Không bật cờ mặc định; bật sau khi chủ repo chạy thử demo.
