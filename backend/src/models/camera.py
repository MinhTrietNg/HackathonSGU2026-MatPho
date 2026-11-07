"""
Camera & Watch Area Models and DTOs for Mắt Phố
Phase 4: Quản lý camera, thùng rác 30 ngày, thăm dò RTSP & Stream HLS
"""

from typing import Optional, List, Any, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from .common import CameraStatus, AIMode


DayOfWeekLiteral = Literal["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


class AIScheduleItemModel(BaseModel):
    from_time: str = Field(
        ...,
        alias="from",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$",
        description="Giờ bắt đầu nghỉ theo định dạng 24h (HH:mm hoặc HH:mm:ss)",
    )
    to_time: str = Field(
        ...,
        alias="to",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$",
        description="Giờ kết thúc nghỉ theo định dạng 24h (HH:mm hoặc HH:mm:ss)",
    )
    days: List[int] = Field(
        ...,
        min_length=1,
        max_length=7,
        description="Các thứ trong tuần theo chuẩn ISO-8601: 1 = Thứ Hai ... 7 = Chủ Nhật",
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("to_time")
    @classmethod
    def validate_different_times(cls, v: str, info) -> str:
        start = info.data.get("from_time")
        if start and start[:5] == v[:5]:
            raise ValueError("Giờ kết thúc ('to') không được trùng với giờ bắt đầu ('from').")
        return v

    @field_validator("days")
    @classmethod
    def validate_days_iso(cls, v: List[int]) -> List[int]:
        for d in v:
            if not (1 <= d <= 7):
                raise ValueError("Mỗi ngày trong 'days' phải nằm trong khoảng từ 1 (Thứ 2) đến 7 (Chủ nhật).")
        if len(v) != len(set(v)):
            raise ValueError("Các ngày trong mảng 'days' không được trùng lặp.")
        return sorted(v)


class AIScheduleSlotModel(BaseModel):
    slot_id: Optional[str] = Field(default=None, description="Mã định danh khung giờ nghỉ (slot_1, slot_2)")
    start_time: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="Giờ bắt đầu nghỉ (HH:MM)")
    end_time: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="Giờ kết thúc nghỉ (HH:MM)")
    days: List[DayOfWeekLiteral] = Field(..., min_length=1, max_length=7, description="Các thứ áp dụng: T2..T7, CN")

    @field_validator("end_time")
    @classmethod
    def validate_start_end_different(cls, v: str, info) -> str:
        start = info.data.get("start_time")
        if start and start == v:
            raise ValueError("Giờ kết thúc (end_time) không được trùng với giờ bắt đầu (start_time).")
        return v


class CameraAIConfigUpdateRequest(BaseModel):
    ai_mode: AIMode = Field(..., description="ALWAYS | SCHEDULE | OFF")
    schedules: Optional[List[AIScheduleSlotModel]] = Field(
        default_factory=list,
        max_length=2,
        description="Tối đa 2 khung giờ nghỉ AI (chỉ áp dụng khi ai_mode = SCHEDULE)",
    )


class WatchAreaModel(BaseModel):
    left: float = Field(..., ge=0.0, le=1.0, description="Tọa độ cạnh trái chuẩn hóa [0.0, 1.0]")
    top: float = Field(..., ge=0.0, le=1.0, description="Tọa độ cạnh trên chuẩn hóa [0.0, 1.0]")
    width: float = Field(..., ge=0.0, le=1.0, description="Chiều rộng vùng quét chuẩn hóa [0.0, 1.0]")
    height: float = Field(..., ge=0.0, le=1.0, description="Chiều cao vùng quét chuẩn hóa [0.0, 1.0]")


class CameraModel(BaseModel):
    cam_id: str = Field(..., description="Khóa chính Camera (cam_xxx)")
    group_id: str = Field(..., description="Mã Group Lớn sở hữu camera")
    subgroup_id: str = Field(..., description="Mã khu vực/vị trí lắp đặt (sub_xxx)")
    subgroup_name: Optional[str] = Field("Khu vực chung", description="Snapshot tên khu vực hiển thị tức thời trên UI")
    cam_name: str = Field(..., min_length=1, max_length=100, description="Tên camera người dùng đặt")
    device_name: Optional[str] = Field(None, max_length=100, description="Tên thiết bị phần cứng (I4, I5)")
    edge_device_id: Optional[str] = Field(None, description="Mã định danh thiết bị Edge tại hiện trường (edg_xxx)")
    rtsp_url: str = Field(..., description="Luồng RTSP nạp vào MediaMTX (chứa tài khoản/mật khẩu camera)")
    live_stream_url: Optional[str] = Field(None, description="Đường dẫn phát HLS Port 8888 (null đối với NOTIFIER)")
    watch_area: Optional[WatchAreaModel] = Field(None, description="Tọa độ vùng quét AI do người dùng khoanh ở màn I5")
    notified_names: Optional[List[str]] = Field(default_factory=list, description="Danh sách tên thành viên nhận cảnh báo (E2/I8)")
    created_by: Optional[str] = Field(default="usr_system", description="UID người thêm camera")
    is_active: bool = Field(default=True, description="Bật/Tắt nạp luồng vào MediaMTX")
    is_ai_enabled: bool = Field(default=True, description="Bật/Tắt gửi frame vào FireWatch AI")
    ai_schedule: List[AIScheduleItemModel] = Field(default_factory=list, description="Lịch nghỉ AI theo giờ (màn H7-H15)")
    thumbnail_url: Optional[str] = Field(None, description="URL ảnh thumbnail mới nhất của camera")
    ai_mode: AIMode = Field(default=AIMode.ALWAYS, description="Chế độ AI: ALWAYS | SCHEDULE | OFF (Màn H7-H15)")
    ai_schedules: List[AIScheduleSlotModel] = Field(default_factory=list, description="Danh sách khung giờ nghỉ AI (Tối đa 2 khung)")
    status: CameraStatus = Field(default=CameraStatus.ONLINE, description="Trạng thái: ONLINE | OFFLINE | SIGNAL_LOST | CONNECTING | DISABLED | DELETED")
    is_deleted: bool = Field(default=False, description="Cờ xóa mềm (Soft Delete)")
    deleted_at: Optional[Any] = Field(None, description="Thời điểm đưa vào thùng rác")
    purge_at: Optional[Any] = Field(None, description="Thời điểm thanh lọc vĩnh viễn (sau 30 ngày)")
    last_seen_at: Optional[Any] = Field(None, description="Thời điểm mất tín hiệu gần nhất (signalLostSince)")
    created_at: Optional[Any] = Field(None, description="Thời điểm thêm camera")
    updated_at: Optional[Any] = Field(None, description="Thời điểm cập nhật cấu hình gần nhất")


class CameraCreateRequest(BaseModel):
    group_id: str
    subgroup_id: Optional[str] = None
    cam_name: str = Field(..., min_length=2, max_length=100)
    device_name: Optional[str] = None
    edge_device_id: Optional[str] = None
    rtsp_url: str
    watch_area: Optional[WatchAreaModel] = None
    is_active: Optional[bool] = True
    is_ai_enabled: Optional[bool] = True
    ai_schedule: Optional[List[AIScheduleItemModel]] = None
    thumbnail_url: Optional[str] = None


class CameraUpdateRequest(BaseModel):
    cam_name: Optional[str] = Field(None, min_length=2, max_length=100)
    device_name: Optional[str] = None
    subgroup_id: Optional[str] = None
    rtsp_url: Optional[str] = Field(None, description="URL RTSP mới khi cập nhật cấu hình hoặc thêm lại RTSP (Màn I8)")
    watch_area: Optional[WatchAreaModel] = None
    is_active: Optional[bool] = None
    is_ai_enabled: Optional[bool] = None
    ai_schedule: Optional[List[AIScheduleItemModel]] = None
    thumbnail_url: Optional[str] = None


class CameraThumbnailUploadRequest(BaseModel):
    image_base64: str = Field(..., description="Chuỗi base64 của ảnh thumbnail (PNG hoặc JPEG)")


class CameraThumbnailResponse(BaseModel):
    status: str = "ok"
    cam_id: str
    thumbnail_url: str
    updated_at: str


class CameraProbeRequest(BaseModel):
    rtsp_url: str = Field(..., description="URL RTSP cần thăm dò kiểm tra kết nối")
    edge_device_id: Optional[str] = Field(None, description="Mã thiết bị Edge để ủy quyền probe trong LAN (edg_xxx)")


class CameraProbeResponse(BaseModel):
    device_name: str
    resolution: str
    fps: int
    preview_snapshot_url: str


class CameraStreamResponse(BaseModel):
    cam_id: str
    status: str
    stream_type: str = "HLS"
    stream_url: str
