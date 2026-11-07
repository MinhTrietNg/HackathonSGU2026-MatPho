# TÀI LIỆU ĐẶC TẢ API TOÀN DIỆN (INPUT & OUTPUT SPECIFICATION)
## Hệ Thống Giám Sát Camera & AI Báo Cháy Khẩn Cấp — Mắt Phố (v1.2.0)

> **Tài liệu này được xuất trực tiếp và đối soát 1-1 từ mã nguồn thực tế của FastAPI Core Gateway (`backend/src/`) và `docs/API_SPECIFICATION.md` v1.2.**
> - **Base REST URL (Local / Docker)**: `http://127.0.0.1:8000/api/v1` (Android Emulator: `http://10.0.2.2:8000/api/v1`)
> - **Base REST URL (Production / Tunnel)**: `https://api.matpho.vn/api/v1`
> - **WebSocket Hub URL**: `ws://127.0.0.1:8000/api/v1/ws` (hoặc `wss://api.matpho.vn/api/v1/ws`)
> - **Edge Duplex WebSocket URL**: `ws://127.0.0.1:8000/api/v1/internal/edge/ws`
> - **MediaMTX HLS Stream URL**: `http://127.0.0.1:8888/live/{cam_id}/index.m3u8`
> - **OpenAPI 3.1 Schema**: [`backend/openapi.json`](./openapi.json) | Swagger UI: `http://127.0.0.1:8000/docs`

---

## MỤC LỤC
1. [Chuẩn Giao Tiếp Chung & Cấu Trúc Lỗi Thống Nhất (Unified Error Schema)](#1-chuẩn-giao-tiếp-chung--cấu-trúc-lỗi-thống-nhất)
2. [Cụm 1: Kiểm Tra Hạ Tầng & Sức Khỏe Hệ Thống (`/health`)](#2-cụm-1-kiểm-tra-hạ-tầng--sức-khỏe-hệ-thống-health)
3. [Cụm 2: Xác Thực, OTP & Phiên Người Dùng (`/api/v1/auth`)](#3-cụm-2-xác-thực-otp--phiên-người-dùng-apiv1auth)
4. [Cụm 3: Hồ Sơ Cá Nhân, Cài Đặt Còi & FCM Token (`/api/v1/users`)](#4-cụm-3-hồ-sơ-cá-nhân-cài-đặt-còi--fcm-token-apiv1users)
5. [Cụm 4: Quản Trị Nhóm Liên Gia & Phân Quyền 4 Vai Trò (`/api/v1/groups`)](#5-cụm-4-quản-trị-nhóm-liên-gia--phân-quyền-4-vai-trò-apiv1groups)
6. [Cụm 5: Khu Vực / Vị Trí Lắp Đặt Camera (`/api/v1/groups/{group_id}/subgroups`)](#6-cụm-5-khu-vực--vị-trí-lắp-đặt-camera-apiv1groupsgroup_idsubgroups)
7. [Cụm 6: Quản Lý Lời Mời Gia Nhập Nhóm (`/api/v1/invitations`)](#7-cụm-6-quản-lý-lời-mời-gia-nhập-nhóm-apiv1invitations)
8. [Cụm 7: Quản Lý Camera, Thăm Dò RTSP, Stream HLS & Thùng Rác 30 Ngày (`/api/v1/cameras`)](#8-cụm-7-quản-lý-camera-thăm-dò-rtsp-stream-hls--thùng-rác-30-ngày-apiv1cameras)
9. [Cụm 8: Sự Cố Cháy, Đếm Ngược Leo Thang 2 Tầng & Điều Phối 114 (`/api/v1/alerts`)](#9-cụm-8-sự-cố-cháy-đếm-ngược-leo-thang-2-tầng--điều-phối-114-apiv1alerts)
10. [Cụm 9: Cài Đặt Hệ Thống & Thử Nghiệm Còi Báo Động (`/api/v1/settings`)](#10-cụm-9-cài-đặt-hệ-thống--thử-nghiệm-còi-báo-động-apiv1settings)
11. [Cụm 10: Webhook Nội Bộ AI FireWatch (`/api/v1/internal/ai`)](#11-cụm-10-webhook-nội-bộ-ai-firewatch-apiv1internalai)
12. [Cụm 11: Kênh Thời Gian Thực WebSocket Hub (`/api/v1/ws` & `/internal/edge/ws`)](#12-cụm-11-kênh-thời-gian-thực-websocket-hub-apiv1ws--internaledgews)
13. [Cụm 12: Ma Trận 6 Loại Thông Báo Đẩy FCM Data Messages](#13-cụm-12-ma-trận-6-loại-thông-báo-đẩy-fcm-data-messages)

---

## 1. CHUẨN GIAO TIẾP CHUNG & CẤU TRÚC LỖI THỐNG NHẤT

### 1.1. Quy ước dữ liệu
- **Content-Type**: `application/json; charset=utf-8` (`snake_case`).
- **Thời gian (Timestamps)**: Chuẩn ISO-8601 UTC (`YYYY-MM-DDTHH:mm:ss.sssZ`, ví dụ: `"2026-11-07T10:15:30.125Z"`).
- **Số điện thoại**: Tự động chuẩn hóa về định dạng quốc tế E.164 (`+84xxxxxxxxx`) dù client gửi `"0912345678"`, `"84912345678"` hay `"+84912345678"`.
- **Định danh có ngữ nghĩa (Semantic IDs)**:
  - Người dùng: `usr_<12_hex>`
  - Nhóm liên gia: `grp_<12_hex>` | Nhóm cá nhân mặc định: `grp_personal_<user_id>`
  - Khu vực (Subgroup): `sub_<12_hex>`
  - Camera: `cam_<12_hex>`
  - Lời mời: `inv_<12_hex>`
  - Sự cố cháy: `alt_<12_hex>`
  - Nhật ký kiểm toán (Audit Log): `aud_<12_hex>` / `log_<12_hex>`

### 1.2. Cơ chế xác thực (Authentication Headers)
1. **API Người dùng (Protected Endpoints)**:
   ```http
   Authorization: Bearer <Firebase_ID_Token>
   ```
   *(Trong môi trường `development`, hỗ trợ truyền trực tiếp `Bearer <custom_token>`, `Bearer usr_xxx` hoặc `Bearer demo_token` để kiểm thử tự động).*
2. **API Nội bộ Edge AI / FireWatch**:
   ```http
   X-Internal-Secret: <INTERNAL_API_SECRET_KEY>
   ```

### 1.3. Cấu trúc lỗi đồng nhất (Unified Error Schema)
**100% các phản hồi lỗi (4xx, 5xx)** từ mọi endpoint đều tuân thủ duy nhất cấu trúc JSON sau:
```json
{
  "error": {
    "code": "MÃ_LỖI_VIẾT_HOA",
    "message": "Thông báo tiếng Việt rõ ràng để hiển thị lên UI.",
    "details": {}
  }
}
```

#### Bảng Tra Cứu Mã Lỗi Chuẩn:
| HTTP Status | `error.code` | `error.details` | Tình huống xảy ra |
| :---: | :--- | :--- | :--- |
| `400` | `CAMERA_NOT_REACHABLE`, `CAMERA_AUTH_FAILED`, `CAMERA_VENDOR_BLOCKED`, `CAMERA_NO_RESPONSE` | `{"device_name": "...", "host": "..."}` | Thăm dò RTSP thất bại (Màn hình I4) |
| `400` | `INVALID_RESET_TOKEN`, `EXPIRED_RESET_TOKEN` | `{}` | Token đặt lại mật khẩu không hợp lệ hoặc quá 15 phút |
| `401` | `UNAUTHORIZED`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `USER_NOT_FOUND`, `INVALID_INTERNAL_SECRET` | `{}` | Thiếu hoặc sai Bearer Token / Internal Secret |
| `403` | `PERMISSION_DENIED`, `FORBIDDEN` | `{}` | Không đủ quyền RBAC (VD: `NOTIFIER` cố xem stream hoặc đóng sự cố; `LEADER` tự rời nhóm) |
| `404` | `NOT_FOUND`, `GROUP_NOT_FOUND`, `CAMERA_NOT_FOUND`, `MEMBER_NOT_FOUND`, `SUBGROUP_NOT_FOUND`, `INVITATION_NOT_FOUND` | `{}` | Tài nguyên không tồn tại hoặc đã bị xóa |
| `404` | `PHONE_NOT_REGISTERED` | `{}` | SĐT chưa đăng ký (khi Quên mật khẩu hoặc Mời thành viên) |
| `409` | `PHONE_ALREADY_REGISTERED`, `ALREADY_IN_GROUP`, `ALREADY_INVITED`, `CONFLICT` | `{}` | Xung đột dữ liệu (SĐT đã có tài khoản, đã trong nhóm) |
| `410` | `OTP_EXPIRED`, `INVITATION_UNAVAILABLE` | `{}` | Mã OTP quá hạn 60s; Lời mời đã bị hủy/chấp nhận/từ chối |
| `422` | `VALIDATION_ERROR` | `{"validation_errors": [{"field": "...", "issue": "..."}]}` | Dữ liệu đầu vào sai kiểu hoặc thiếu trường bắt buộc |
| `422` | `WRONG_PASSWORD` | `{"attempts_left": 4}` | Sai SĐT hoặc mật khẩu đăng nhập (OWASP chống dò SĐT) |
| `422` | `OTP_WRONG` | `{"attempts_left": 2}` | Nhập sai mã OTP 6 chữ số |
| `423` | `ACCOUNT_LOCKED` | `{"locked_until": "2026-11-07T10:30:00+00:00"}` | Tài khoản bị khóa 15 phút sau 5 lần nhập sai mật khẩu |
| `429` | `OTP_LOCKED` | `{"retry_at": "2026-11-07T10:20:00+00:00"}` | Nhập sai OTP 3 lần liên tiếp (khóa 5 phút) |
| `429` | `OTP_RESEND_COOLDOWN` | `{"available_at": "2026-11-07T10:16:00+00:00"}` | Gửi lại OTP khi chưa hết 60s đếm ngược |

---

## 2. CỤM 1: KIỂM TRA HẠ TẦNG & SỨC KHỎE HỆ THỐNG (`/health`)

### 2.1. Kiểm tra Liveness cơ bản (Root Health Probe)
- **Method & Path**: `GET /health`
- **Auth**: Public (Không yêu cầu token)
- **Input**: Không có.
- **Output (`200 OK`)**:
  ```json
  {
    "status": "ok",
    "service": "Mắt Phố - AI Surveillance & Fire Emergency API",
    "version": "1.2.0"
  }
  ```

### 2.2. Kiểm tra Sức khỏe Chi tiết Hạ tầng (Detailed Readiness Probe)
- **Method & Path**: `GET /api/v1/health`
- **Auth**: Public
- **Input**: Không có.
- **Output (`200 OK`)**:
  ```json
  {
    "status": "ok",
    "service": "Mắt Phố - AI Surveillance & Fire Emergency API",
    "version": "1.2.0",
    "environment": "development",
    "services": {
      "firestore": "healthy",
      "storage": "healthy",
      "redis": "healthy"
    }
  }
  ```

### 2.3. Kiểm thử Cấu trúc Lỗi Thống nhất (Test Error Endpoint)
- **Method & Path**: `POST /api/v1/health/test-error`
- **Auth**: Public
- **Input (Request Body)**:
  ```json
  {
    "error_type": "not_found"
  }
  ```
  *(Giá trị hỗ trợ: `"not_found"` $\to$ 404, `"permission_denied"` $\to$ 403, `"validation"` $\to$ 422, `"custom"` $\to$ 400, `"internal"` $\to$ 500).*
- **Output (`404 Not Found` khi `error_type = "not_found"`)**:
  ```json
  {
    "error": {
      "code": "TEST_NOT_FOUND",
      "message": "Tài nguyên kiểm thử không tồn tại.",
      "details": {}
    }
  }
  ```

---

## 3. CỤM 2: XÁC THỰC, OTP & PHIÊN NGƯỜI DÙNG (`/api/v1/auth`)

### 3.1. Kiểm tra Số điện thoại khả dụng (Figma B1)
- **Method & Path**: `POST /api/v1/auth/check-phone`
- **Auth**: Public
- **Input (Request Body)**:
  ```json
  {
    "phone_number": "0912345678"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "phone_number": "+84912345678",
    "is_available": true
  }
  ```

### 3.2. Yêu cầu Gửi OTP Đăng ký Tài khoản mới (Figma B1 $\to$ B2)
- **Method & Path**: `POST /api/v1/auth/register/request-otp`
- **Auth**: Public
- **Input (Request Body)**:
  ```json
  {
    "phone_number": "0912345678",
    "full_name": "Nguyễn Minh Anh",
    "password": "Password123@"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "challenge_id": "otp_chl_register_9f8e7d6c5b4a",
    "expires_in": 60,
    "resend_cooldown": 60,
    "dev_otp": "123456"
  }
  ```
- **Lỗi**: `409 PHONE_ALREADY_REGISTERED` nếu SĐT đã tồn tại.

### 3.3. Yêu cầu Gửi OTP Quên Mật khẩu (Figma B4 $\to$ B2)
- **Method & Path**: `POST /api/v1/auth/forgot-password/request-otp`
- **Auth**: Public
- **Input (Request Body)**:
  ```json
  {
    "phone_number": "0912345678"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "challenge_id": "otp_chl_forgot_password_1a2b3c4d5e6f",
    "expires_in": 60,
    "resend_cooldown": 60,
    "dev_otp": "123456"
  }
  ```
- **Lỗi**: `404 PHONE_NOT_REGISTERED` nếu SĐT chưa đăng ký.

### 3.4. Xác thực Mã OTP 6 chữ số (Figma B2, B3)
- **Method & Path**: `POST /api/v1/auth/verify-otp`
- **Auth**: Public
- **Input (Request Body)**:
  ```json
  {
    "challenge_id": "otp_chl_register_9f8e7d6c5b4a",
    "code": "123456",
    "fcm_token": "fcm_device_token_optional"
  }
  ```
- **Output 1 — Khi `purpose == "register"` (`200 OK`)**:
  *(Tự động khởi tạo atomic transaction: `phone_registry`, `users`, nhóm cá nhân `grp_personal_{uid}`, member `LEADER`, `group_memberships`)*
  ```json
  {
    "type": "REGISTER_SUCCESS",
    "custom_token": "eyJhbGciOiJSUzI1NiIs...",
    "user": {
      "user_id": "usr_a1b2c3d4e5f6",
      "phone_number": "+84912345678",
      "full_name": "Nguyễn Minh Anh",
      "loud_when_silent": true,
      "personal_group_id": "grp_personal_usr_a1b2c3d4e5f6"
    }
  }
  ```
- **Output 2 — Khi `purpose == "forgot_password"` (`200 OK`)**:
  ```json
  {
    "type": "RESET_PASSWORD_VERIFIED",
    "reset_token": "rst_tok_778899aabbccddeeff00112233445566"
  }
  ```
- **Lỗi**: `422 OTP_WRONG` (`details.attempts_left`), `429 OTP_LOCKED` (`details.retry_at`), `410 OTP_EXPIRED`.

### 3.5. Gửi lại Mã OTP (Figma B3)
- **Method & Path**: `POST /api/v1/auth/resend-otp` *(Alias: `POST /api/v1/auth/register/resend-otp`)*
- **Auth**: Public
- **Input (Request Body)**:
  ```json
  {
    "challenge_id": "otp_chl_register_9f8e7d6c5b4a"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "challenge_id": "otp_chl_register_5f4e3d2c1b0a",
    "expires_in": 60,
    "resend_cooldown": 60,
    "dev_otp": "123456"
  }
  ```
- **Lỗi**: `429 OTP_RESEND_COOLDOWN` (`details.available_at`), `410 OTP_EXPIRED`.

### 3.6. Đăng nhập SĐT + Mật khẩu (Figma A5, A6)
- **Method & Path**: `POST /api/v1/auth/login`
- **Auth**: Public
- **Input (Request Body)**:
  ```json
  {
    "phone_number": "0912345678",
    "password": "Password123@",
    "fcm_token": "fcm_device_token_optional"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "custom_token": "eyJhbGciOiJSUzI1NiIs...",
    "user": {
      "user_id": "usr_a1b2c3d4e5f6",
      "phone_number": "+84912345678",
      "full_name": "Nguyễn Minh Anh",
      "loud_when_silent": true,
      "personal_group_id": "grp_personal_usr_a1b2c3d4e5f6"
    }
  }
  ```
- **Lỗi**:
  - `422 WRONG_PASSWORD`: `{"attempts_left": 4}` (Trả về đồng nhất cả khi SĐT chưa tồn tại lẫn khi sai mật khẩu).
  - `423 ACCOUNT_LOCKED`: `{"locked_until": "2026-11-07T10:30:00+00:00"}` (Sau 5 lần nhập sai liên tiếp).

### 3.7. Đặt lại Mật khẩu mới sau khi xác thực OTP (Figma B5)
- **Method & Path**: `POST /api/v1/auth/reset-password` *(Alias: `POST /api/v1/auth/forgot-password/reset`)*
- **Auth**: Public (Sử dụng `reset_token` từ bước `verify-otp`)
- **Input (Request Body)**:
  ```json
  {
    "reset_token": "rst_tok_778899aabbccddeeff00112233445566",
    "new_password": "NewPassword456@"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Mật khẩu đã được thay đổi thành công. Máy khác đã đăng xuất."
  }
  ```

### 3.8. Đổi Mật khẩu trong Cài đặt (Figma H5)
- **Method & Path**: `POST /api/v1/auth/change-password`
- **Auth**: `Bearer <Token>`
- **Input (Request Body)**:
  ```json
  {
    "current_password": "Password123@",
    "new_password": "NewPassword456@"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Đổi mật khẩu thành công"
  }
  ```
- **Lỗi**: `422 WRONG_PASSWORD` nếu `current_password` không khớp.

### 3.9. Đăng xuất Thiết bị (Figma H6)
- **Method & Path**: `POST /api/v1/auth/logout`
- **Auth**: `Bearer <Token>`
- **Input (Request Body)**:
  ```json
  {
    "fcm_token": "fcm_device_token_xyz"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Đã hủy đăng ký nhận thông báo cho thiết bị này"
  }
  ```

---

## 4. CỤM 3: HỒ SƠ CÁ NHÂN, CÀI ĐẶT CÒI & FCM TOKEN (`/api/v1/users`)

### 4.1. Lấy Thông tin Tài khoản Hiện tại
- **Method & Path**: `GET /api/v1/users/me`
- **Auth**: `Bearer <Token>`
- **Input**: Không có.
- **Output (`200 OK`)**:
  ```json
  {
    "user_id": "usr_a1b2c3d4e5f6",
    "phone_number": "+84912345678",
    "full_name": "Nguyễn Minh Anh",
    "loud_when_silent": true,
    "personal_group_id": "grp_personal_usr_a1b2c3d4e5f6"
  }
  ```

### 4.2. Xem Cài đặt Thông báo Cá nhân
- **Method & Path**: `GET /api/v1/users/me/settings`
- **Auth**: `Bearer <Token>`
- **Output (`200 OK`)**:
  ```json
  {
    "loud_when_silent": true,
    "full_name": "Nguyễn Minh Anh"
  }
  ```

### 4.3. Cập nhật Cài đặt Còi Im Lặng & Họ Tên (Figma H1)
- **Method & Path**: `PATCH /api/v1/users/me/settings` *(Aliases: `PUT /api/v1/users/me`, `PATCH /api/v1/users/me/loud-when-silent`)*
- **Auth**: `Bearer <Token>`
- **Input (Request Body)**:
  ```json
  {
    "loud_when_silent": false,
    "full_name": "Nguyễn Minh Anh (Đã cập nhật)"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "loud_when_silent": false,
    "full_name": "Nguyễn Minh Anh (Đã cập nhật)"
  }
  ```

### 4.4. Đăng ký / Cập nhật FCM Device Token
- **Method & Path**: `POST /api/v1/users/me/fcm-tokens` *(Alias: `POST /api/v1/users/me/fcm-token`)*
- **Auth**: `Bearer <Token>`
- **Input (Request Body)**:
  ```json
  {
    "fcm_token": "fcm_token_android_or_ios_device_001"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "FCM token đã được cập nhật thành công."
  }
  ```

---

## 5. CỤM 4: QUẢN TRỊ NHÓM LIÊN GIA & PHÂN QUYỀN 4 VAI TRÒ (`/api/v1/groups`)

### 5.1. Danh sách Nhóm của Tôi (Figma J7, I13)
- **Method & Path**: `GET /api/v1/groups`
- **Auth**: `Bearer <Token>`
- **Output (`200 OK`)**:
  ```json
  [
    {
      "group_id": "grp_personal_usr_a1b2c3d4e5f6",
      "group_name": "Cá nhân",
      "is_personal": true,
      "leader_id": "usr_a1b2c3d4e5f6",
      "address": null,
      "member_count": 1,
      "camera_count": 0,
      "my_role": "LEADER",
      "my_nickname": "Tôi",
      "created_at": "2026-11-07T09:00:00.000Z",
      "updated_at": "2026-11-07T09:00:00.000Z"
    },
    {
      "group_id": "grp_8899aabbccdd",
      "group_name": "Tổ Liên Gia PCCC Khu Phố 3",
      "is_personal": false,
      "leader_id": "usr_a1b2c3d4e5f6",
      "address": "123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM",
      "member_count": 4,
      "camera_count": 2,
      "my_role": "LEADER",
      "my_nickname": "Tổ Trưởng",
      "created_at": "2026-11-07T09:10:00.000Z",
      "updated_at": "2026-11-07T09:10:00.000Z"
    }
  ]
  ```

### 5.2. Tạo Nhóm Mới (Figma J8)
- **Method & Path**: `POST /api/v1/groups`
- **Auth**: `Bearer <Token>`
- **Input (Request Body)**:
  ```json
  {
    "name": "Tổ Liên Gia PCCC Khu Phố 3",
    "address": "123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM",
    "my_nickname": "Tổ Trưởng"
  }
  ```
- **Output (`201 Created`)**:
  ```json
  {
    "group_id": "grp_8899aabbccdd",
    "group_name": "Tổ Liên Gia PCCC Khu Phố 3",
    "is_personal": false,
    "leader_id": "usr_a1b2c3d4e5f6",
    "address": "123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM",
    "member_count": 1,
    "camera_count": 0,
    "my_role": "LEADER",
    "my_nickname": "Tổ Trưởng",
    "created_at": "2026-11-07T09:10:00.000Z"
  }
  ```

### 5.3. Xem Chi tiết Nhóm
- **Method & Path**: `GET /api/v1/groups/{group_id}`
- **Auth**: `Bearer <Token>` (Phải là thành viên nhóm)
- **Output (`200 OK`)**: Cùng cấu trúc với đối tượng nhóm ở mục 5.1.

### 5.4. Cập nhật Tên nhóm & Địa chỉ Cứu nạn 114
- **Method & Path**: `PATCH /api/v1/groups/{group_id}` *(Alias: `PUT /api/v1/groups/{group_id}`)*
- **Auth**: `Bearer <Token>`
- **Quyền RBAC**:
  - Đổi `name`: `LEADER` hoặc `MEMBER_MANAGER`.
  - Đổi `address` (Địa chỉ cứu nạn 114): **Chỉ duy nhất `LEADER`** (ADR 0008).
- **Input (Request Body)**:
  ```json
  {
    "name": "Tổ Liên Gia PCCC Khu Phố 3 - Mở Rộng",
    "address": "125 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "group_id": "grp_8899aabbccdd",
    "group_name": "Tổ Liên Gia PCCC Khu Phố 3 - Mở Rộng",
    "is_personal": false,
    "leader_id": "usr_a1b2c3d4e5f6",
    "address": "125 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM",
    "member_count": 4,
    "camera_count": 2,
    "updated_at": "2026-11-07T09:20:00.000Z"
  }
  ```

### 5.5. Giải tán Nhóm (Figma J15)
- **Method & Path**: `DELETE /api/v1/groups/{group_id}`
- **Auth**: `Bearer <Token>` (Chỉ `LEADER`; Không cho phép xóa nhóm cá nhân `is_personal=true`)
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Đã giải tán nhóm thành công"
  }
  ```

### 5.6. Rời Nhóm (Figma J14)
- **Method & Path**: `POST /api/v1/groups/{group_id}/leave`
- **Auth**: `Bearer <Token>` (`LEADER` bị chặn `403 PERMISSION_DENIED` nếu chưa chuyển quyền trưởng nhóm)
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Đã rời khỏi nhóm thành công"
  }
  ```

### 5.7. Chuyển Quyền Trưởng Nhóm (Transfer Ownership)
- **Method & Path**: `POST /api/v1/groups/{group_id}/transfer-ownership`
- **Auth**: `Bearer <Token>` (Chỉ `LEADER`)
- **Input (Request Body)**:
  ```json
  {
    "new_leader_id": "usr_member_002"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Đã chuyển giao quyền Trưởng nhóm thành công.",
    "group_id": "grp_8899aabbccdd",
    "new_leader_id": "usr_member_002"
  }
  ```

### 5.8. Danh sách Thành viên & Lời mời đang chờ (Figma J1, J6)
- **Method & Path**: `GET /api/v1/groups/{group_id}/members`
- **Auth**: `Bearer <Token>` (Thành viên nhóm)
- **Output (`200 OK`)**:
  ```json
  {
    "members": [
      {
        "user_id": "usr_a1b2c3d4e5f6",
        "full_name": "Nguyễn Minh Anh",
        "phone_number": "+84912345678",
        "role": "LEADER",
        "nickname": "Tổ Trưởng",
        "note": "Chủ sở hữu nhóm",
        "camera_ids": null,
        "joined_at": "2026-11-07T09:10:00.000Z",
        "is_you": true
      }
    ],
    "pending_invitations": [
      {
        "invitation_id": "inv_112233445566",
        "phone_number": "+84987654321",
        "role": "MEMBER",
        "nickname": "Chú Ba Bảo Vệ",
        "camera_ids": ["cam_001"],
        "camera_names": [],
        "created_at": "2026-11-07T09:15:00.000Z"
      }
    ]
  }
  ```

### 5.9. Mời Thành viên bằng Số điện thoại (Figma J2)
- **Method & Path**: `POST /api/v1/groups/{group_id}/invitations`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Input (Request Body)**:
  ```json
  {
    "phone_number": "0987654321",
    "role": "MEMBER",
    "nickname": "Chú Ba Bảo Vệ",
    "camera_ids": ["cam_12a4b8c9e011"]
  }
  ```
  *(Các giá trị `role`: `"MEMBER_MANAGER"`, `"MEMBER"`, `"NOTIFIER"`; `camera_ids`: `null` = xem toàn bộ camera trong nhóm, mảng `[...]` = chỉ xem các camera được chỉ định).*
- **Output (`201 Created`)**:
  ```json
  {
    "invitation_id": "inv_112233445566",
    "phone_number": "+84987654321",
    "role": "MEMBER",
    "nickname": "Chú Ba Bảo Vệ",
    "status": "PENDING",
    "created_at": "2026-11-07T09:15:00.000Z"
  }
  ```
- **Lỗi**: `404 PHONE_NOT_REGISTERED`, `409 ALREADY_IN_GROUP`, `409 ALREADY_INVITED`.

### 5.10. Thu hồi Lời mời đang chờ (Figma J1, J5)
- **Method & Path**: `DELETE /api/v1/groups/{group_id}/invitations/{invitation_id}`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Đã thu hồi lời mời thành công"
  }
  ```

### 5.11. Đổi Vai trò Thành viên (Figma J4)
- **Method & Path**: `PATCH /api/v1/groups/{group_id}/members/{user_id}/role`
- **Auth**: `Bearer <Token>` (**Chỉ `LEADER`**)
- **Input (Request Body)**:
  ```json
  {
    "role": "MEMBER_MANAGER"
  }
  ```
- **Output (`200 OK`)**: Đối tượng `Member` đã cập nhật.

### 5.12. Phân công Camera cho Thành viên (Figma J4)
- **Method & Path**: `PUT /api/v1/groups/{group_id}/members/{user_id}/cameras` *(Alias: `PATCH`)*
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Input (Request Body)**:
  ```json
  {
    "camera_ids": ["cam_12a4b8c9e011", "cam_99aabbccddee"]
  }
  ```
  *(Truyền `null` để cấp quyền xem toàn bộ camera trong nhóm).*
- **Output (`200 OK`)**: Đối tượng `Member` đã cập nhật.

### 5.13. Đổi Biệt danh Thành viên trong Nhóm (Figma J11, J12)
- **Method & Path**: `PATCH /api/v1/groups/{group_id}/members/{user_id}/nickname`
- **Auth**: `Bearer <Token>` (Chính thành viên đó, hoặc `LEADER` / `MEMBER_MANAGER`)
- **Input (Request Body)**:
  ```json
  {
    "nickname": "Anh Tư Tổ Phó"
  }
  ```
- **Output (`200 OK`)**: Đối tượng `Member` đã cập nhật.

### 5.14. Xóa Thành viên khỏi Nhóm (Figma J1, J5)
- **Method & Path**: `DELETE /api/v1/groups/{group_id}/members/{user_id}`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`; Hỗ trợ truyền `inv_xxx` vào `{user_id}` để tự động thu hồi lời mời)
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Đã xóa thành viên khỏi nhóm thành công"
  }
  ```

### 5.15. Nhật ký Kiểm toán Cấp Cơ Sở (Group Audit Logs)
- **Method & Path**: `GET /api/v1/groups/{group_id}/audit-logs?limit=50`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Output (`200 OK`)**:
  ```json
  {
    "group_id": "grp_8899aabbccdd",
    "items": [
      {
        "log_id": "aud_33b8a1c9e44d",
        "group_id": "grp_8899aabbccdd",
        "actor_id": "usr_a1b2c3d4e5f6",
        "action": "CREATE_GROUP",
        "target_entity": "group:grp_8899aabbccdd",
        "details": {
          "group_name": "Tổ Liên Gia PCCC Khu Phố 3",
          "address": "123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM"
        },
        "created_at": "2026-11-07T09:10:00.000Z"
      }
    ],
    "total": 1
  }
  ```

---

## 6. CỤM 5: KHU VỰC / VỊ TRÍ LẮP ĐẶT CAMERA (`/api/v1/groups/{group_id}/subgroups`)

### 6.1. Danh sách Khu vực trong Nhóm (Figma I5)
- **Method & Path**: `GET /api/v1/groups/{group_id}/subgroups`
- **Auth**: `Bearer <Token>` (Mọi thành viên trong nhóm)
- **Output (`200 OK`)**:
  ```json
  [
    {
      "subgroup_id": "sub_22c4a9e10ff4",
      "name": "Bếp Tầng 1",
      "description": "Khu vực nấu ăn và bình gas",
      "camera_count": 1,
      "created_at": "2026-11-07T09:25:00.000Z"
    }
  ]
  ```

### 6.2. Tạo Khu vực Lắp đặt Mới (Figma I9)
- **Method & Path**: `POST /api/v1/groups/{group_id}/subgroups`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Input (Request Body)**:
  ```json
  {
    "name": "Bếp Tầng 1",
    "description": "Khu vực nấu ăn và bình gas"
  }
  ```
- **Output (`201 Created`)**:
  ```json
  {
    "subgroup_id": "sub_22c4a9e10ff4",
    "name": "Bếp Tầng 1",
    "description": "Khu vực nấu ăn và bình gas",
    "camera_count": 0,
    "created_at": "2026-11-07T09:25:00.000Z"
  }
  ```

### 6.3. Cập nhật Khu vực Lắp đặt
- **Method & Path**: `PATCH /api/v1/groups/{group_id}/subgroups/{subgroup_id}` *(Alias: `PUT`)*
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Input (Request Body)**:
  ```json
  {
    "name": "Nhà Kho & Bếp Tầng 1",
    "description": "Đã mở rộng vùng giám sát"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "subgroup_id": "sub_22c4a9e10ff4",
    "name": "Nhà Kho & Bếp Tầng 1",
    "description": "Đã mở rộng vùng giám sát",
    "camera_count": 1
  }
  ```

### 6.4. Xóa Khu vực Lắp đặt
- **Method & Path**: `DELETE /api/v1/groups/{group_id}/subgroups/{subgroup_id}`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Đã xóa khu vực thành công"
  }
  ```

---

## 7. CỤM 6: QUẢN LÝ LỜI MỜI GIA NHẬP NHÓM (`/api/v1/invitations`)

### 7.1. Danh sách Lời mời Gửi tới Tôi (Figma J3)
- **Method & Path**: `GET /api/v1/invitations/my-invitations` *(Aliases: `GET /api/v1/invitations`, `GET /api/v1/groups/invitations/me`)*
- **Auth**: `Bearer <Token>`
- **Output (`200 OK`)**:
  ```json
  [
    {
      "invitation_id": "inv_112233445566",
      "id": "inv_112233445566",
      "group_id": "grp_8899aabbccdd",
      "group_name": "Tổ Liên Gia PCCC Khu Phố 3",
      "group_address": "123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM",
      "invited_by_name": "Nguyễn Minh Anh",
      "inviter_name": "Nguyễn Minh Anh",
      "role": "MEMBER",
      "nickname": "Chú Ba Bảo Vệ",
      "suggested_nickname": "Chú Ba Bảo Vệ",
      "member_count": 1,
      "camera_count": 1,
      "camera_names": [],
      "status": "PENDING",
      "created_at": "2026-11-07T09:15:00.000Z"
    }
  ]
  ```

### 7.2. Xem Chi tiết Lời mời (Figma J3)
- **Method & Path**: `GET /api/v1/invitations/{invitation_id}`
- **Auth**: `Bearer <Token>` (Chỉ người nhận lời mời hoặc `LEADER`/`MEMBER_MANAGER` của nhóm đó)
- **Output (`200 OK`)**: Đối tượng lời mời như mục 7.1.
- **Lỗi**: `410 INVITATION_UNAVAILABLE` nếu lời mời không tồn tại, đã xử lý hoặc không thuộc quyền xem.

### 7.3. Chấp nhận Lời mời Gia nhập Nhóm (Figma J3)
- **Method & Path**: `POST /api/v1/invitations/{invitation_id}/accept`
- **Auth**: `Bearer <Token>` (Khớp SĐT người nhận)
- **Input (Request Body - Optional)**:
  ```json
  {
    "nickname": "Chú Ba (Ca Đêm)"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Chào mừng bạn gia nhập Tổ Liên Gia PCCC Khu Phố 3!",
    "group_id": "grp_8899aabbccdd",
    "group_name": "Tổ Liên Gia PCCC Khu Phố 3",
    "role": "MEMBER",
    "my_nickname": "Chú Ba (Ca Đêm)"
  }
  ```

### 7.4. Từ chối Lời mời Gia nhập (Figma J3)
- **Method & Path**: `POST /api/v1/invitations/{invitation_id}/decline` *(Aliases: `POST /api/v1/invitations/{invitation_id}/reject`, `DELETE /api/v1/invitations/{invitation_id}`)*
- **Auth**: `Bearer <Token>`
- **Output (`200 OK`)**:
  ```json
  {
    "status": "success",
    "message": "Đã từ chối lời mời tham gia nhóm."
  }
  ```

---

## 8. CỤM 7: QUẢN LÝ CAMERA, THĂM DÒ RTSP, STREAM HLS & THÙNG RÁC 30 NGÀY (`/api/v1/cameras`)

### 8.1. Thăm dò Luồng RTSP (Probe Camera - Figma I2, I4, I5)
- **Method & Path**: `POST /api/v1/cameras/probe`
- **Auth**: `Bearer <Token>`
- **Input (Request Body)**:
  ```json
  {
    "rtsp_url": "rtsp://admin:123456@192.168.1.100:554/Streaming/Channels/101?mock=true",
    "edge_device_id": "edg_station_01"
  }
  ```
- **Output (`200 OK`)**:
  ```json
  {
    "device_name": "Hikvision DS-2CD2143G2-I (Thử nghiệm)",
    "resolution": "1920x1080",
    "fps": 25,
    "preview_snapshot_url": "https://storage.googleapis.com/matpho-c7e77.firebasestorage.app/probes/preview_mock.jpg"
  }
  ```
- **Lỗi (`400 Bad Request`)**:
  - `CAMERA_NOT_REACHABLE` (URL không bắt đầu bằng `rtsp://`)
  - `CAMERA_AUTH_FAILED` (Sai hoặc thiếu user:password)
  - `CAMERA_VENDOR_BLOCKED` (Hãng chặn truy cập)
  - `CAMERA_NO_RESPONSE` (Quá thời gian chờ 3-5s)

### 8.2. Lưu Camera Mới vào Nhóm (Figma I5)
- **Method & Path**: `POST /api/v1/cameras`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Input (Request Body)**:
  ```json
  {
    "group_id": "grp_8899aabbccdd",
    "subgroup_id": "sub_22c4a9e10ff4",
    "cam_name": "Camera Bếp Tầng 1",
    "device_name": "Hikvision DS-2CD2143G2-I",
    "edge_device_id": "edg_station_01",
    "rtsp_url": "rtsp://admin:123456@192.168.1.100:554/Streaming/Channels/101?mock=true",
    "watch_area": {
      "left": 0.1,
      "top": 0.15,
      "width": 0.8,
      "height": 0.75
    }
  }
  ```
- **Output (`201 Created`)**:
  ```json
  {
    "cam_id": "cam_12a4b8c9e011",
    "cam_name": "Camera Bếp Tầng 1",
    "group_id": "grp_8899aabbccdd",
    "subgroup_id": "sub_22c4a9e10ff4",
    "subgroup_name": "Bếp Tầng 1",
    "device_name": "Hikvision DS-2CD2143G2-I",
    "status": "ONLINE",
    "last_seen_at": null,
    "live_stream_url": "http://127.0.0.1:8888/live/cam_12a4b8c9e011/index.m3u8",
    "watch_area": {
      "left": 0.1,
      "top": 0.15,
      "width": 0.8,
      "height": 0.75
    },
    "created_at": "2026-11-07T09:30:00.000Z"
  }
  ```

### 8.3. Danh sách Camera trong Nhóm (Figma E1, I7)
- **Method & Path**: `GET /api/v1/cameras?group_id={group_id}&subgroup_id={subgroup_id}` *(Alias: `GET /api/v1/groups/{group_id}/cameras`)*
- **Auth**: `Bearer <Token>` (Thành viên nhóm)
- **Bảo mật RBAC**:
  - `LEADER` & `MEMBER_MANAGER`: Nhận đầy đủ `live_stream_url`.
  - `MEMBER`: Chỉ nhận `live_stream_url` của các camera được phân quyền (`camera_ids == null` hoặc `cam_id in camera_ids`), còn lại `live_stream_url = null`.
  - `NOTIFIER`: **Luôn nhận `live_stream_url = null`**.
- **Output (`200 OK`)**: Mảng các đối tượng Camera như mục 8.2.

### 8.4. Chi tiết Một Camera & Danh sách Người nhận Báo động (Figma E2, I8)
- **Method & Path**: `GET /api/v1/cameras/{cam_id}`
- **Auth**: `Bearer <Token>` (Thành viên nhóm)
- **Output (`200 OK`)**:
  ```json
  {
    "cam_id": "cam_12a4b8c9e011",
    "cam_name": "Camera Bếp Tầng 1",
    "group_id": "grp_8899aabbccdd",
    "subgroup_id": "sub_22c4a9e10ff4",
    "subgroup_name": "Bếp Tầng 1",
    "device_name": "Hikvision DS-2CD2143G2-I",
    "status": "ONLINE",
    "last_seen_at": null,
    "live_stream_url": "http://127.0.0.1:8888/live/cam_12a4b8c9e011/index.m3u8",
    "watch_area": {
      "left": 0.1,
      "top": 0.15,
      "width": 0.8,
      "height": 0.75
    },
    "notified_names": [
      "Nguyễn Minh Anh",
      "Chú Ba (Ca Đêm)"
    ]
  }
  ```

### 8.5. Lấy Link Stream HLS Trực tiếp & Đánh thức Luồng On-Demand
- **Method & Path**: `GET /api/v1/cameras/{cam_id}/stream` *(Alias: `GET /api/v1/cameras/{cam_id}/stream-url`)*
- **Auth**: `Bearer <Token>`
- **Bảo mật RBAC**:
  - `NOTIFIER` gọi API này sẽ bị **chặn đứng với mã `403 PERMISSION_DENIED`**.
  - `MEMBER` không được gán camera này cũng bị chặn `403 PERMISSION_DENIED`.
  - Khi hợp lệ, Backend tự động gửi lệnh `START_LIVE` qua kênh WebSocket xuống Edge Node để bật push RTSP $\to$ HLS.
- **Output (`200 OK`)**:
  ```json
  {
    "cam_id": "cam_12a4b8c9e011",
    "status": "ONLINE",
    "stream_type": "HLS",
    "stream_url": "http://127.0.0.1:8888/live/cam_12a4b8c9e011/index.m3u8"
  }
  ```

### 8.6. Giữ Luồng Xem Trực tiếp (Keepalive) & Tắt Luồng (Stop Stream)
- **Keepalive**: `POST /api/v1/cameras/{cam_id}/stream/keepalive` $\to$ `200 OK`: `{"status": "ok", "cam_id": "cam_12a4b8c9e011"}`
- **Stop**: `POST /api/v1/cameras/{cam_id}/stream/stop` $\to$ `200 OK`: `{"status": "ok", "cam_id": "cam_12a4b8c9e011"}`

### 8.7. Cập nhật Cấu hình Camera & Vùng Quét AI (Watch Area)
- **Method & Path 1 (Cập nhật tổng hợp)**: `PATCH /api/v1/cameras/{cam_id}` *(Alias: `PUT /api/v1/cameras/{cam_id}`)*
  - **Input**:
    ```json
    {
      "cam_name": "Camera Bếp Chính Tầng 1",
      "subgroup_id": "sub_22c4a9e10ff4",
      "is_active": true,
      "is_ai_enabled": true,
      "watch_area": {
        "left": 0.05,
        "top": 0.1,
        "width": 0.9,
        "height": 0.85
      }
    }
    ```
- **Method & Path 2 (Chỉ cập nhật Watch Area)**: `PUT /api/v1/cameras/{cam_id}/watch-area`
  - **Input**:
    ```json
    {
      "left": 0.05,
      "top": 0.1,
      "width": 0.9,
      "height": 0.85
    }
    ```
  - **Output (`200 OK`)**:
    ```json
    {
      "cam_id": "cam_12a4b8c9e011",
      "watch_area": {
        "left": 0.05,
        "top": 0.1,
        "width": 0.9,
        "height": 0.85
      }
    }
    ```

### 8.8. Thử Kết nối lại Camera (Reconnect - Figma I8)
- **Method & Path**: `POST /api/v1/cameras/{cam_id}/reconnect`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Output (`200 OK`)**: Đối tượng Camera kèm trạng thái kết nối mới (`ONLINE` / `OFFLINE`).

### 8.9. Bỏ qua Dấu hiệu Đang Xác minh (Dismiss Suspect - Figma E2a, E2b)
- **Method & Path**: `POST /api/v1/cameras/{cam_id}/suspect/dismiss`
- **Auth**: `Bearer <Token>` (`LEADER`, `MEMBER_MANAGER`, `MEMBER`)
- **Output**: `204 No Content` (Không có body).

### 8.10. Xóa Mềm Camera vào Thùng Rác 30 Ngày (Soft Delete - Figma I7, I12)
- **Method & Path**: `DELETE /api/v1/cameras/{cam_id}`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Output (`200 OK`)**:
  ```json
  {
    "status": "deleted",
    "cam_id": "cam_12a4b8c9e011",
    "purge_at": "2026-12-07T09:40:00.000Z"
  }
  ```

### 8.11. Danh sách Camera trong Thùng Rác (Trash Bin - Figma I12)
- **Method & Path**: `GET /api/v1/cameras/trash?group_id={group_id}`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Output (`200 OK`)**:
  ```json
  [
    {
      "cam_id": "cam_12a4b8c9e011",
      "cam_name": "Camera Bếp Tầng 1",
      "group_id": "grp_8899aabbccdd",
      "subgroup_id": "sub_22c4a9e10ff4",
      "subgroup_name": "Bếp Tầng 1",
      "device_name": "Hikvision DS-2CD2143G2-I",
      "status": "DELETED",
      "deleted_at": "2026-11-07T09:40:00.000Z",
      "purge_at": "2026-12-07T09:40:00.000Z"
    }
  ]
  ```

### 8.12. Khôi phục Camera từ Thùng Rác (Restore - Figma I12)
- **Method & Path**: `POST /api/v1/cameras/{cam_id}/restore`
- **Auth**: `Bearer <Token>` (`LEADER` hoặc `MEMBER_MANAGER`)
- **Output (`200 OK`)**:
  ```json
  {
    "status": "ok",
    "message": "Đã khôi phục camera thành công"
  }
  ```

### 8.13. Xóa Vĩnh Viễn Camera khỏi Hệ thống (Permanent Delete - Figma I12)
- **Method & Path**: `DELETE /api/v1/cameras/{cam_id}/permanent`
- **Auth**: `Bearer <Token>` (**Chỉ duy nhất `LEADER`**; `MEMBER_MANAGER` bị chặn `403 PERMISSION_DENIED`)
- **Output (`200 OK`)**:
  ```json
  {
    "status": "ok",
    "message": "Đã xóa vĩnh viễn camera"
  }
  ```

---

## 9. CỤM 8: SỰ CỐ CHÁY, ĐẾM NGƯỢC LEO THANG 2 TẦNG & ĐIỀU PHỐI 114 (`/api/v1/alerts`)

### 9.1. Lịch sử Báo động 30 Ngày (Cursor Pagination & Filter - Figma G1, G3)
- **Method & Path**: `GET /api/v1/alerts`
- **Auth**: `Bearer <Token>`
- **Query Parameters**:
  - `group_id` *(optional)*: Lọc theo nhóm cụ thể (nếu bỏ trống sẽ lấy toàn bộ nhóm của user).
  - `filter` *(optional, default `"all"`)*: `"all"` | `"fire"` | `"dismissed"` | `"false_alarm"`.
  - `cursor` *(optional)*: Chuỗi ISO-8601 `next_cursor` của trang trước.
  - `limit` *(optional, default `20`, max `100`)*.
- **Output (`200 OK`)**:
  ```json
  {
    "items": [
      {
        "alert_id": "alt_88d011e2f334",
        "cam_id": "cam_12a4b8c9e011",
        "cam_name": "Camera Bếp Tầng 1",
        "location_name": "Bếp Tầng 1",
        "status": "NEW",
        "sign": "FIRE",
        "confidence": 0.94,
        "verification": "VERIFIED",
        "summary": "Phát hiện dấu hiệu fire tại Bếp Tầng 1",
        "detail": "Mô hình YOLO26n ONNX phát hiện fire với độ tin cậy 0.94.",
        "still_url": "https://firebasestorage.googleapis.com/v0/b/.../initial_detected.jpg?alt=media&token=...",
        "detected_at": "2026-11-07T10:00:00.000Z",
        "called_114_at": null,
        "resolved_at": null,
        "resolved_by_name": null
      }
    ],
    "next_cursor": null
  }
  ```

### 9.2. Chi tiết Sự cố & Timeline Các Bước (Zero-Friction Emergency Access - Figma F2, G4, G5)
- **Method & Path**: `GET /api/v1/alerts/{alert_id}?emergency_token={emergency_token}`
- **Auth**:
  - Cách 1: Header `Authorization: Bearer <Token>` (Thành viên nhóm).
  - Cách 2: Query `?emergency_token=emg_<ts>_<sig>` (Cho phép mở thẳng màn hình khẩn cấp F2 từ thông báo đẩy FCM mà không cần chờ bước làm mới token đăng nhập).
- **Output (`200 OK`)**:
  ```json
  {
    "alert_id": "alt_88d011e2f334",
    "cam_id": "cam_12a4b8c9e011",
    "cam_name": "Camera Bếp Tầng 1",
    "location_name": "Bếp Tầng 1",
    "address": "123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM",
    "status": "NEW",
    "sign": "FIRE",
    "confidence": 0.94,
    "check_count": 2,
    "verification": "VERIFIED",
    "summary": "Phát hiện dấu hiệu fire tại Bếp Tầng 1",
    "detail": "Mô hình YOLO26n ONNX phát hiện fire với độ tin cậy 0.94.",
    "call_script": "Cháy tại Bếp Tầng 1, cơ sở Camera Bếp Tầng 1",
    "still_url": "https://firebasestorage.googleapis.com/v0/b/.../initial_detected.jpg?alt=media&token=...",
    "detected_at": "2026-11-07T10:00:00.000Z",
    "called_114_at": null,
    "resolved_at": null,
    "resolved_by": null,
    "resolved_by_name": null,
    "resolution_note": null,
    "steps": {
      "DETECTED": "2026-11-07T10:00:00.000Z",
      "IMAGE_SENT": "2026-11-07T10:00:00.000Z",
      "AI_VERIFIED": "2026-11-07T10:00:00.000Z",
      "ALERT_TRIGGERED": "2026-11-07T10:00:00.000Z"
    },
    "timeline_snapshots": [
      {
        "url": "https://firebasestorage.googleapis.com/v0/b/.../initial_detected.jpg?alt=media&token=...",
        "bbox": [0.12, 0.25, 0.45, 0.68],
        "timestamp": "2026-11-07T10:00:00.000Z"
      }
    ]
  }
  ```

### 9.3. Trạng thái Bộ đếm Đếm ngược Leo thang 2 Tầng 60s (ADR 0011)
- **Method & Path**: `GET /api/v1/alerts/{alert_id}/escalation-status`
- **Auth**: `Bearer <Token>` (Thành viên nhóm)
- **Output (`200 OK`)**:
  ```json
  {
    "alert_id": "alt_88d011e2f334",
    "group_id": "grp_8899aabbccdd",
    "status": "NEW",
    "timer_active": true,
    "remaining_seconds": 48,
    "escalation_level": 0
  }
  ```

### 9.4. Ghi nhận Gọi 114 & Kích hoạt Còi Cấp 2 Toàn Nhóm (Figma F2, F7)
- **Method & Path**: `POST /api/v1/alerts/{alert_id}/call-114`
- **Auth**: `Bearer <Token>` (Thành viên nhóm)
- **Hiệu ứng hệ thống**:
  1. Hủy ngay lập tức bộ đếm 60s trên Redis (`cancel_timer`).
  2. Chuyển trạng thái sự cố sang `CONFIRMED`, ghi nhận `called_114_at`.
  3. Phát sóng WebSocket `FIRE_ALERT` (`escalation_level: 1`) và đẩy FCM High Priority tới **100% thành viên trong nhóm**.
- **Output (`200 OK`)**:
  ```json
  {
    "alert_id": "alt_88d011e2f334",
    "status": "CONFIRMED",
    "called_114_at": "2026-11-07T10:00:25.000Z",
    "address": "123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM",
    "address_to_read": "Báo cháy khẩn cấp tại: 123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM, khu vực Bếp Tầng 1.",
    "call_script": "Báo cháy khẩn cấp tại: 123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM, khu vực Bếp Tầng 1.",
    "message": "Đã ghi nhận cuộc gọi 114 khẩn cấp và kích hoạt còi hú toàn bộ thành viên"
  }
  ```

### 9.5. Đánh dấu Sự cố "Đã Xử Lý" (Resolve - Figma F2 $\to$ F5)
- **Method & Path**: `POST /api/v1/alerts/{alert_id}/resolve`
- **Auth**: `Bearer <Token>` (`LEADER`, `MEMBER_MANAGER`, `MEMBER`; **`NOTIFIER` bị chặn `403 PERMISSION_DENIED`**)
- **Hiệu ứng hệ thống**: Hủy timer 60s trên Redis, phát WebSocket & FCM `FIRE_ALERT_UPDATED` (`status: "RESOLVED"`) để tắt còi đồng loạt trên mọi máy.
- **Input (Request Body)**:
  ```json
  {
    "resolution_note": "Đã dập tắt bằng bình chữa cháy CO2 tại chỗ"
  }
  ```
- **Output (`200 OK`)**: Đối tượng chi tiết sự cố đã cập nhật (`status: "RESOLVED"`, có bước `"RESOLVED"` trong `steps`).

### 9.6. Đánh dấu "Báo Động Giả / Báo Nhầm" (False Alarm - Figma F2, F4 $\to$ I10)
- **Method & Path**: `POST /api/v1/alerts/{alert_id}/mark-false-alarm`
- **Auth**: `Bearer <Token>` (`LEADER`, `MEMBER_MANAGER`, `MEMBER`; **`NOTIFIER` bị chặn `403 PERMISSION_DENIED`**)
- **Hiệu ứng hệ thống**: Hủy timer 60s trên Redis, cập nhật `status: "FALSE_ALARM"`, `verification: "CONFIRMED_NOT_FIRE"`, phát WebSocket & FCM tắt còi.
- **Output (`200 OK`)**: Đối tượng chi tiết sự cố đã cập nhật (`status: "FALSE_ALARM"`).

### 9.7. Báo lại Cháy Thật khi AI lọc nhầm (Report Real Fire - Figma G5)
- **Method & Path**: `POST /api/v1/alerts/{alert_id}/report-real-fire`
- **Auth**: `Bearer <Token>` (Thành viên nhóm)
- **Output (`200 OK`)**:
  ```json
  {
    "alert_id": "alt_88d011e2f334",
    "status": "CONFIRMED",
    "address": "123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM",
    "message": "Đã kích hoạt còi báo động khẩn cấp tới toàn bộ thành viên"
  }
  ```

### 9.8. Thẻ Thông tin Điều phối Cứu nạn 114 (Emergency Dispatch Card - Figma F7)
- **Method & Path**: `GET /api/v1/alerts/{alert_id}/dispatch-info`
- **Auth**: `Bearer <Token>` (Thành viên nhóm)
- **Output (`200 OK`)**:
  ```json
  {
    "alert_id": "alt_88d011e2f334",
    "facility_name": "Tổ Liên Gia PCCC Khu Phố 3",
    "address": "123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM",
    "location_name": "Bếp Tầng 1",
    "cam_name": "Camera Bếp Tầng 1",
    "status": "CONFIRMED",
    "call_script": "Báo cháy khẩn cấp tại: 123 Nguyễn Trãi, Phường 2, Quận 5, TP.HCM, khu vực Bếp Tầng 1.",
    "emergency_contacts": [
      {
        "user_id": "usr_a1b2c3d4e5f6",
        "full_name": "Nguyễn Minh Anh",
        "phone_number": "+84912345678",
        "role": "LEADER"
      }
    ],
    "still_url": "https://firebasestorage.googleapis.com/v0/b/.../initial_detected.jpg?alt=media&token=...",
    "detected_at": "2026-11-07T10:00:00.000Z",
    "called_114_at": "2026-11-07T10:00:25.000Z"
  }
  ```

### 9.9. Dòng thời gian Kiểm toán Sự cố Báo động (Alert Audit Trail)
- **Method & Path**: `GET /api/v1/alerts/{alert_id}/audit-logs`
- **Auth**: `Bearer <Token>` (Thành viên nhóm)
- **Output (`200 OK`)**:
  ```json
  {
    "alert_id": "alt_88d011e2f334",
    "items": [
      {
        "log_id": "log_99aabbccddee",
        "action": "CALL_114_INITIATED",
        "actor_id": "usr_a1b2c3d4e5f6",
        "actor_name": "Nguyễn Minh Anh",
        "target_entity": "alert:alt_88d011e2f334",
        "details": {
          "action": "call_114"
        },
        "created_at": "2026-11-07T10:00:25.000Z"
      },
      {
        "log_id": "log_112233445566",
        "action": "ALERT_TRIGGERED",
        "actor_id": "system_ai_firewatch",
        "actor_name": "Thành viên",
        "target_entity": "alert:alt_88d011e2f334",
        "details": {
          "cam_id": "cam_12a4b8c9e011",
          "confidence": 0.94,
          "sign": "fire"
        },
        "created_at": "2026-11-07T10:00:00.000Z"
      }
    ],
    "total": 2
  }
  ```

---

## 10. CỤM 9: CÀI ĐẶT HỆ THỐNG & THỬ NGHIỆM CÒI BÁO ĐỘNG (`/api/v1/settings`)

### 10.1. Gửi thử Cảnh báo Push FCM kiểm tra Loa & Còi (Figma H4)
- **Method & Path**: `POST /api/v1/settings/test-alert`
- **Auth**: `Bearer <Token>`
- **Input**: `{}` (Không yêu cầu trường dữ liệu)
- **Output (`200 OK`)**:
  ```json
  {
    "status": "dispatched",
    "test_id": "tst_1794042000",
    "tokens_targeted": 1,
    "dispatched_count": 1,
    "sent_at": "2026-11-07T10:20:00.000Z"
  }
  ```

### 10.2. Xem Thông tin Hệ thống
- **Method & Path**: `GET /api/v1/settings/system`
- **Auth**: `Bearer <Token>`
- **Output (`200 OK`)**:
  ```json
  {
    "project_name": "Mắt Phố - AI Surveillance & Fire Emergency API",
    "version": "1.2.0",
    "environment": "development",
    "server_time": "2026-11-07T10:20:00.000Z"
  }
  ```

---

## 11. CỤM 10: WEBHOOK NỘI BỘ AI FIREWATCH (`/api/v1/internal/ai`)

> **Yêu cầu Header bắt buộc cho mọi request trong Cụm 10**:
> `X-Internal-Secret: <INTERNAL_API_SECRET_KEY>`

### 11.1. Tiếp nhận Sự kiện Phát hiện Cháy từ Edge AI (90s Debounce & Two-Tier Siren)
- **Method & Path**:
  - `POST /api/v1/internal/ai/fire-events`
  - `POST /internal/ai/fire-events` *(Alias nội bộ Docker LAN)*
  - `POST /api/v1/alerts/events` *(Alias chuẩn AI Gateway)*
- **Cơ chế xử lý**:
  - **Debounce 90 giây**: Nếu trên cùng `cam_id` đã có sự cố `NEW` hoặc `CONFIRMED` trong vòng 90 giây qua, hệ thống **không tạo bản ghi rác mới** mà gom frame ảnh vào mảng `timeline_snapshots` (tối đa 60 frames) và cập nhật `confidence = max(...)`.
  - **Nếu là sự cố mới**: Upload ảnh lên Firebase Storage lấy Token-based CDN URL, khởi tạo sự cố `NEW`, bật bộ đếm leo thang 60s trên Redis (`escalation:timer:{alert_id}`), phát sóng WebSocket Cấp 1 (`escalation_level: 0`) cho `LEADER` & `MEMBER_MANAGER` và bắn thông báo FCM High Priority song song (`< 500ms`).
- **Input (Request Body)**:
  ```json
  {
    "cam_id": "cam_12a4b8c9e011",
    "class_name": "fire",
    "confidence": 0.94,
    "timestamp": 1794042000.5,
    "bbox": [0.12, 0.25, 0.45, 0.68],
    "image_base64": "/9j/4AAQSkZJRgABAQAAAQABAAD..."
  }
  ```
- **Output (`202 Accepted`)**:
  ```json
  {
    "status": "accepted",
    "alert_id": "alt_88d011e2f334",
    "escalation_level": 0
  }
  ```

### 11.2. Phát Tín hiệu AI Đang Xác minh Nghi vấn (Figma E2a–E2c Viền Vàng)
- **Method & Path**: `POST /api/v1/internal/ai/verifying` *(Alias: `POST /internal/ai/verifying`)*
- **Input (Request Body)**:
  ```json
  {
    "cam_id": "cam_12a4b8c9e011",
    "sign": "SMOKE",
    "confidence": 0.68,
    "message": "Đang xác minh tín hiệu khói nghi vấn...",
    "steps": [
      {"step": 1, "label": "Phát hiện vùng khói mờ", "done": true},
      {"step": 2, "label": "Đang đối chiếu chuyển động 5 frame", "done": false}
    ]
  }
  ```
- **Output (`202 Accepted`)**:
  ```json
  {
    "status": "accepted",
    "cam_id": "cam_12a4b8c9e011"
  }
  ```

### 11.3. Phát Tín hiệu AI Đã Lọc / Triệt tiêu Báo động Giả (Toast Xám E4)
- **Method & Path**: `POST /api/v1/internal/ai/suppressed` *(Alias: `POST /internal/ai/suppressed`)*
- **Input (Request Body)**:
  ```json
  {
    "cam_id": "cam_12a4b8c9e011",
    "alert_id": "alt_supp_001",
    "summary": "Không phải cháy",
    "detail": "AI kết luận: Ánh đèn xe máy phản chiếu qua cửa kính."
  }
  ```
- **Output (`202 Accepted`)**:
  ```json
  {
    "status": "accepted",
    "cam_id": "cam_12a4b8c9e011"
  }
  ```

---

## 12. CỤM 11: KÊNH THỜI GIAN THỰC WEBSOCKET HUB (`/api/v1/ws` & `/internal/edge/ws`)

### 12.1. Kênh WebSocket cho Ứng dụng Mobile / Web Client
- **URL**: `ws://<host>/api/v1/ws?token=<Token>` *(hoặc truyền Header `Authorization: Bearer <Token>`)*
- **Cơ chế Phân phòng Tự động (Two-Tier Isolation)**:
  - Khi kết nối thành công, Server tự động đăng ký socket vào:
    - `user_{user_id}`
    - `group_{group_id}` (Tất cả các nhóm mà user là thành viên — nhận báo động Cấp 2 `escalation_level: 1`)
    - `group_{group_id}_leaders` (Chỉ dành cho `LEADER` và `MEMBER_MANAGER` — nhận báo động Cấp 1 `escalation_level: 0`)

#### A. Bản tin Server gửi ngay khi kết nối thành công (`CONNECTED`):
```json
{
  "type": "CONNECTED",
  "user_id": "usr_a1b2c3d4e5f6",
  "rooms": [
    "user_usr_a1b2c3d4e5f6",
    "group_grp_personal_usr_a1b2c3d4e5f6",
    "group_grp_personal_usr_a1b2c3d4e5f6_leaders",
    "group_grp_8899aabbccdd",
    "group_grp_8899aabbccdd_leaders"
  ],
  "timestamp": 1794042000.123
}
```

#### B. Các Bản tin Client gửi lên Server (Client $\to$ Server):
1. **Heartbeat Ping**:
   - Input: `"ping"` hoặc `{"type": "ping"}`
   - Output: `{"type": "pong", "timestamp": 1794042005.123}`
2. **Đăng ký theo dõi phòng Camera cụ thể (`subscribe_camera`)**:
   - Input: `{"type": "subscribe_camera", "cam_id": "cam_12a4b8c9e011"}`
   - Output (Nếu đủ quyền RBAC): `{"type": "SUBSCRIBED", "room": "camera_cam_12a4b8c9e011", "timestamp": 1794042010.0}`
   - Output (Nếu là `NOTIFIER` hoặc không có quyền): `{"type": "ERROR", "code": "PERMISSION_DENIED", "message": "Bạn không có quyền theo dõi camera cam_12a4b8c9e011."}`
3. **Xác nhận đã nhận cảnh báo (`ack`)**:
   - Input: `{"type": "ack", "alert_id": "alt_88d011e2f334"}`
   - Output: `{"type": "ack_ok", "alert_id": "alt_88d011e2f334", "timestamp": 1794042012.0}`

#### C. Các Bản tin Server đẩy xuống Client (Server $\to$ Client):
1. **Nhịp tim Camera định kỳ 5 giây (`CAMERA_HEARTBEAT`)**:
   ```json
   {
     "type": "CAMERA_HEARTBEAT",
     "cam_id": "cam_12a4b8c9e011",
     "status": "ONLINE",
     "ai_status": "SCANNING",
     "fps": 25
   }
   ```
2. **AI Đang Xác minh Nghi vấn (`AI_VERIFYING`)**:
   ```json
   {
     "type": "AI_VERIFYING",
     "cam_id": "cam_12a4b8c9e011",
     "sign": "SMOKE",
     "confidence": 0.68,
     "message": "Đang xác minh tín hiệu khói nghi vấn...",
     "steps": [{"step": 1, "label": "Phát hiện vùng khói mờ", "done": true}]
   }
   ```
3. **AI Triệt tiêu Báo động Giả (`FIRE_ALERT_SUPPRESSED`)**:
   ```json
   {
     "type": "FIRE_ALERT_SUPPRESSED",
     "alert_id": "alt_supp_001",
     "cam_id": "cam_12a4b8c9e011",
     "summary": "Không phải cháy",
     "detail": "AI kết luận: Ánh đèn phản chiếu."
   }
   ```
4. **Báo Động Cháy Khẩn Cấp 2 Tầng (`FIRE_ALERT`)**:
   ```json
   {
     "type": "FIRE_ALERT",
     "alert_id": "alt_88d011e2f334",
     "cam_id": "cam_12a4b8c9e011",
     "cam_name": "Camera Bếp Tầng 1",
     "location_name": "Bếp Tầng 1",
     "sign": "FIRE",
     "confidence": 0.94,
     "still_url": "https://firebasestorage.googleapis.com/v0/b/.../initial_detected.jpg?alt=media&token=...",
     "summary": "Phát hiện dấu hiệu fire tại Bếp Tầng 1",
     "detail": "Mô hình YOLO26n ONNX phát hiện fire với độ tin cậy 0.94.",
     "verification": "VERIFIED",
     "detected_at": "2026-11-07T10:00:00.000Z",
     "escalation_level": 0
   }
   ```
   *(`escalation_level = 0`: Cấp 1 cho Leader/Manager; `escalation_level = 1`: Cấp 2 cho toàn bộ thành viên).*
5. **Đồng bộ Đóng Sự cố / Tắt Còi (`FIRE_ALERT_UPDATED`)**:
   ```json
   {
     "type": "FIRE_ALERT_UPDATED",
     "alert_id": "alt_88d011e2f334",
     "status": "RESOLVED",
     "escalation_level": 1,
     "resolved_by_name": "Nguyễn Minh Anh",
     "resolved_at": "2026-11-07T10:02:00.000Z"
   }
   ```

### 12.2. Kênh WebSocket Song Công Dành Riêng Cho Edge AI (`ADR 0012`)
- **URL**: `ws://<host>/api/v1/internal/edge/ws?edge_id=edg_station_01&secret=<INTERNAL_API_SECRET_KEY>`
- **Bản tin Handshake trả về**: `{"type": "EDGE_CONNECTED_ACK", "edge_device_id": "edg_station_01", "server_time": 1794042000.0}`
- **Bản tin Edge gửi lên**:
  - `{"type": "EDGE_HEARTBEAT", "public_hls_base_url": "https://stream-tunnel.trycloudflare.com", "cameras": ["cam_12a4b8c9e011"], "active_streams": 1}`
  - `{"type": "CAMERA_STATUS", "cam_id": "cam_12a4b8c9e011", "status": "ONLINE", "fps": 25}`
- **Lệnh Điều khiển từ Cloud xuống Edge**:
  - `{"type": "START_LIVE", "cam_id": "cam_12a4b8c9e011"}`
  - `{"type": "KEEPALIVE_LIVE", "cam_id": "cam_12a4b8c9e011"}`
  - `{"type": "STOP_LIVE", "cam_id": "cam_12a4b8c9e011"}`

---

## 13. CỤM 12: MA TRẬN 6 LOẠI THÔNG BÁO ĐẨY FCM DATA MESSAGES

Tất cả các thông báo đẩy Firebase Cloud Messaging đều được gửi với `priority="high"`, `apns-priority="10"` và `content_available=True` để đánh thức thiết bị kể cả khi ứng dụng bị đóng (killed) hoặc khóa màn hình:

| STT | `data.type` | Channel ID (Android) | Âm thanh iOS | Các trường trong `data` Payload |
| :---: | :--- | :--- | :--- | :--- |
| 1 | `FIRE_ALERT` | `fire_alarms` | `alarm.caf` | `type`, `alert_id`, `escalation_level` (`"0"` / `"1"`), `emergency_token` (`"emg_..."`), `action_call` (`"tel:114"`), `action_view` |
| 2 | `FIRE_ALERT_UPDATED` | `fire_alarms` | `alarm.caf` | `type`, `alert_id`, `status` (`"RESOLVED"` / `"FALSE_ALARM"`), `resolved_by_name` |
| 3 | `TEST_ALERT` | `matpho_general` | `default` | `type`, `test_id` |
| 4 | `INVITATION` | `matpho_general` | `default` | `type`, `group_id`, `invitation_id` |
| 5 | `ROLE_CHANGED` | `matpho_general` | `default` | `type`, `group_id` |
| 6 | `CAMERA_OFFLINE` | `matpho_general` | `default` | `type`, `cam_id` |
