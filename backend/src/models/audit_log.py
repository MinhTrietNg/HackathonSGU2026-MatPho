"""
Audit Log Model for Mắt Phố (Phase 6)
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from .common import AuditAction


class AuditLogModel(BaseModel):
    log_id: str = Field(..., description="Khóa chính bản ghi kiểm toán (log_xxx)")
    group_id: str = Field(..., description="Mã Group Lớn xảy ra hành động")
    actor_id: str = Field(..., description="UID người thực hiện hành động kiểm toán")
    action: AuditAction = Field(..., description="Hành động bảo mật được ghi vết")
    target_entity: str = Field(..., description="Đối tượng bị tác động (ví dụ: 'camera:cam_01', 'alert:alt_02')")
    details: Dict[str, Any] = Field(default_factory=dict, description="Dữ liệu chi tiết trước/sau khi thay đổi")
    created_at: Optional[Any] = Field(None, description="Thời điểm ghi nhận hành động (bất biến)")
