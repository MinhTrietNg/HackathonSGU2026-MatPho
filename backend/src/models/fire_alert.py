"""
Fire Alert & Timeline Models for Mắt Phố (Phase 6 & FireWatch AI 18-field contract)
"""

from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from .common import AlertStatus, AlertVerification, SignType


class StepTimelineModel(BaseModel):
    kind: str = Field(..., description="Mã loại bước: DETECTED | IMAGE_SENT | AI_VERIFIED | ALERT_TRIGGERED | CALLED_114 | RESOLVED")
    at: str = Field(..., description="Thời điểm ghi nhận bước (chuỗi ISO-8601 UTC)")
    label: str = Field(..., description="Nhãn mô tả hành động hiển thị trên timeline giao diện (G4, G5)")


class TimelineSnapshotModel(BaseModel):
    snapshot_id: str = Field(..., description="Mã định danh ảnh snapshot (snap_xxx)")
    image_url: str = Field(..., description="Token-based Download URL tải ảnh CDN từ Firebase Storage")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Độ tin cậy của mô hình tại thời điểm chụp frame")
    timestamp: str = Field(..., description="Mốc thời gian chụp frame")
    bbox: List[float] = Field(default_factory=list, description="Tọa độ hộp nhận diện bounding box [x1, y1, x2, y2]")
    boxes: List[Dict[str, Any]] = Field(default_factory=list, description="Danh sách các box kèm xyxy và xyxyn")
    frame_w: Optional[int] = Field(1920, description="Chiều rộng khung gốc")
    frame_h: Optional[int] = Field(1080, description="Chiều cao khung gốc")


class AIEventBoxModel(BaseModel):
    cls: str = Field("fire", description="fire | smoke")
    conf: float = Field(0.8, ge=0.0, le=1.0, description="Độ tự tin nhận diện")
    xyxy: List[float] = Field(default_factory=list, description="Tọa độ pixel [x1, y1, x2, y2] trên khung gốc")
    xyxyn: List[float] = Field(default_factory=list, description="Tọa độ chuẩn hóa [x1, y1, x2, y2] tỉ lệ 0.0 - 1.0")


class AIVLMResultModel(BaseModel):
    is_fire: Optional[bool] = None
    is_smoke: Optional[bool] = None
    confidence: Optional[float] = None
    description_vi: Optional[str] = None
    fire_type: Optional[str] = None


class AIVerifierModel(BaseModel):
    status: Optional[str] = None
    needs_human_check: bool = False
    latency_ms: Optional[int] = None
    reason: Optional[str] = None


class FireAlertModel(BaseModel):
    alert_id: str = Field(..., description="Khóa chính sự cố cháy (alt_xxx)")
    event_id: Optional[str] = Field(None, description="Mã sự cố duy nhất từ khối AI")
    event_ids: List[str] = Field(default_factory=list, description="Mọi event_id của FireWatch đã ghép vào sự cố này (FireWatch chạy lại, bùng lại)")
    group_id: str = Field(..., description="Mã Group Lớn nhận cảnh báo còi hú")
    subgroup_id: Optional[str] = Field(default="sub_general", description="Mã khu vực/vị trí xảy ra cháy (sub_xxx)")
    subgroup_name: Optional[str] = Field(default="Khu vực chung", description="Snapshot tên khu vực hiển thị pop-up")
    location_name: Optional[str] = Field(None, description="Snapshot tên vị trí ngắn gọn (FE: alert.locationName)")
    cam_id: str = Field(..., description="Mã camera đã phát hiện ngọn lửa")
    cam_name: Optional[str] = Field(default="Camera", description="Snapshot tên thiết bị ghi nhận cháy")
    summary: Optional[str] = Field(default="Phát hiện cảnh báo", max_length=150, description="Tóm tắt ngắn sự cố hiển thị card (F2, G1)")
    detail: Optional[str] = Field(default="", max_length=500, description="Chi tiết phân tích sự cố của mô hình AI")
    call_script: Optional[str] = Field(None, max_length=255, description="Kịch bản tóm tắt đọc nhanh cho tổng đài 114 ở màn F7")
    sign: SignType = Field(default=SignType.BOTH, description="Dấu hiệu nhận biết: FIRE | SMOKE | BOTH")
    check_count: int = Field(default=1, ge=1, description="Số lần AI kiểm tra xác minh trước khi báo")
    fire_image_url: Optional[str] = Field(default="", description="Ảnh bằng chứng khởi tạo ban đầu (Token-based CDN URL)")
    still_url: Optional[str] = Field(None, description="Alias của fire_image_url (FE: evidence.stillUrl)")
    snapshot_status: str = Field(default="PENDING", description="Trạng thái ảnh lịch sử: PENDING | READY")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Độ tin cậy AI phát hiện ban đầu (0.0 -> 1.0)")
    status: AlertStatus = Field(default=AlertStatus.NEW, description="Trạng thái: NEW | CONFIRMED | FALSE_ALARM | RESOLVED | SUPPRESSED | DISMISSED")
    verification: AlertVerification = Field(default=AlertVerification.VERIFIED, description="Thẩm định: VERIFIED | UNVERIFIED | SUPPRESSED | CONFIRMED_NOT_FIRE | CONFIRMED_FIRE")
    ai_status: Optional[str] = Field("open", description="Trạng thái từ AI: open | ended")
    severity: Optional[str] = Field("WARNING", description="WARNING | CRITICAL")
    fire_type: Optional[str] = Field(None, description="UNCONTROLLED | CONTROLLED | UNKNOWN")
    started_at: Optional[Any] = Field(None, description="Mốc thời gian phát hiện từ AI")
    last_seen_ts: Optional[Any] = Field(None, description="Mốc thời gian gần nhất AI còn thấy lửa")
    frame_ts: Optional[Any] = Field(None, description="Mốc thời gian của frame chụp snapshot")
    frame_w: Optional[int] = Field(1920, description="Chiều rộng khung hình gốc")
    frame_h: Optional[int] = Field(1080, description="Chiều cao khung hình gốc")
    boxes: List[Dict[str, Any]] = Field(default_factory=list, description="Danh sách các box phát hiện kèm xyxy & xyxyn")
    bbox: List[float] = Field(default_factory=list, description="Tọa độ box chính [x1, y1, x2, y2]")
    vlm: Optional[Dict[str, Any]] = Field(None, description="Metadata từ mô hình VLM")
    verifier: Optional[Dict[str, Any]] = Field(None, description="Metadata từ Verifier bền vững")
    steps: List[StepTimelineModel] = Field(default_factory=list, description="Timeline các bước diễn biến phát hiện")
    timeline_snapshots: List[TimelineSnapshotModel] = Field(default_factory=list, description="Mảng chứa duy nhất bức ảnh lịch sử ban đầu")
    called_114_at: Optional[Any] = Field(None, description="Thời điểm người dùng bấm nút Gọi 114 trên App (F2, F5)")
    escalation_level: int = Field(default=0, ge=0, le=2, description="Cấp độ leo thang còi báo động (0: Leader/Manager, 1: Toàn bộ thành viên)")
    next_escalation_at: Optional[Any] = Field(None, description="Thời điểm còi hú tự động leo thang nếu chưa ai xác nhận (sau 60s)")
    resolved_by: Optional[str] = Field(None, description="UID người bấm nút 'Đã xử lý' tại hiện trường")
    resolved_by_name: Optional[str] = Field(None, description="Họ tên người xử lý sự cố (F5, máy khác)")
    resolved_at: Optional[Any] = Field(None, description="Thời điểm đóng sự cố an toàn")
    resolution_note: Optional[str] = Field(None, max_length=500, description="Ghi chú hiện trường sau khi dập tắt")
    detected_at: Optional[Any] = Field(None, description="Thời điểm phát hiện lửa ban đầu")
    created_at: Optional[Any] = Field(None, description="Thời điểm tạo bản ghi sự cố")
    updated_at: Optional[Any] = Field(None, description="Thời điểm cập nhật timeline/status gần nhất")


class AIFireEventPayload(BaseModel):
    # Cấu trúc 18 trường chuẩn của FireWatch AI
    type: Optional[str] = Field("created", description="created | updated")
    event_id: Optional[str] = Field(None, description="Khóa sự cố duy nhất từ AI")
    camera_id: Optional[str] = Field(None, description="Mã camera định danh phía AI")
    cam_id: Optional[str] = Field(None, description="Mã camera chuẩn của hệ thống (do EAG gắn)")
    status: Optional[str] = Field("open", description="open | ended")
    severity: Optional[str] = Field("WARNING", description="WARNING | CRITICAL")
    fire_type: Optional[str] = Field(None, description="Phân loại đám cháy")
    started_at: Optional[str] = Field(None, description="Thời điểm bắt đầu phát hiện")
    last_seen_ts: Optional[str] = Field(None, description="Thời điểm gần nhất còn thấy lửa")
    frame_ts: Optional[Any] = Field(None, description="Mốc thời gian frame chụp")
    frame_w: Optional[int] = Field(1920, description="Chiều rộng khung gốc")
    frame_h: Optional[int] = Field(1080, description="Chiều cao khung gốc")
    boxes: List[AIEventBoxModel] = Field(default_factory=list, description="Danh sách box")
    verification: Optional[str] = Field("UNVERIFIED", description="VERIFIED | UNVERIFIED | SUPPRESSED")
    vlm: Optional[AIVLMResultModel] = Field(None, description="Kết quả mô hình VLM")
    verifier: Optional[AIVerifierModel] = Field(None, description="Thông số verifier bền vững")
    luot_xac_minh: Optional[int] = Field(1, description="Số lượt thẩm định")
    snapshot_path: Optional[str] = Field(None, description="Đường dẫn file ảnh trên Edge")
    snapshot_base64: Optional[str] = Field(None, description="Chuỗi ảnh JPEG Base64")

    # Các trường tương thích ngược với API cũ
    class_name: Optional[str] = Field("fire", description="fire | smoke | both")
    confidence: Optional[float] = Field(None, description="Độ tự tin nhận diện")
    timestamp: Optional[float] = Field(None, description="Epoch timestamp từ camera")
    bbox: List[float] = Field(default_factory=list, description="Tọa độ [x1, y1, x2, y2]")
    image_base64: Optional[str] = Field(None, description="Alias cũ của snapshot_base64")


class AISnapshotUploadPayload(BaseModel):
    event_id: str = Field(..., description="Mã sự cố tương ứng")
    cam_id: Optional[str] = Field(None, description="Mã camera chuẩn")
    camera_id: Optional[str] = Field(None, description="Mã camera phía AI")
    frame_ts: Optional[Any] = Field(None, description="Mốc thời gian chụp frame")
    frame_w: Optional[int] = Field(1920, description="Chiều rộng khung gốc")
    frame_h: Optional[int] = Field(1080, description="Chiều cao khung gốc")
    boxes: List[AIEventBoxModel] = Field(default_factory=list, description="Danh sách bounding box")
    snapshot_base64: str = Field(..., description="Chuỗi Base64 ảnh JPEG gốc không vẽ box")


class AIVerifyingPayload(BaseModel):
    cam_id: str = Field(..., description="Mã camera")
    sign: str = Field("FIRE", description="Dấu hiệu: FIRE | SMOKE | BOTH")
    confidence: float = Field(0.65, ge=0.0, le=1.0)
    message: str = Field("Đang xác minh tín hiệu nghi vấn...", description="Thông điệp hiển thị viền vàng E2")
    steps: List[Dict[str, Any]] = Field(default_factory=list, description="Các bước xác minh [step1, step2]")


class AISuppressedPayload(BaseModel):
    cam_id: str = Field(..., description="Mã camera")
    alert_id: Optional[str] = None
    summary: str = Field("Không phải cháy", description="Tiêu đề Toast E4")
    detail: str = Field("AI kết luận: Ánh đèn phản chiếu hoặc vật thể bình thường.", description="Chi tiết Toast E4")


class ResolveAlertRequest(BaseModel):
    resolution_note: Optional[str] = "Đã dập tắt / xử lý tại hiện trường"
