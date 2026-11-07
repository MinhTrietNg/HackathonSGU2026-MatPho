"""
Camera & Watch Area Models and DTOs for Mắt Phố
Phase 4: Quản lý camera, thùng rác 30 ngày, thăm dò RTSP & Stream HLS
"""

from typing import Optional, List, Any
from pydantic import BaseModel, Field
from .common import CameraStatus


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


class CameraUpdateRequest(BaseModel):
    cam_name: Optional[str] = Field(None, min_length=2, max_length=100)
    device_name: Optional[str] = None
    subgroup_id: Optional[str] = None
    rtsp_url: Optional[str] = Field(None, description="URL RTSP mới khi cập nhật cấu hình hoặc thêm lại RTSP (Màn I8)")
    watch_area: Optional[WatchAreaModel] = None
    is_active: Optional[bool] = None
    is_ai_enabled: Optional[bool] = None


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
