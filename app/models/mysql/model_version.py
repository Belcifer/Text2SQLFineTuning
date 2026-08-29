from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mysql.base import Base


class ModelVersion(Base):
    """模型版本（API 文档 7 节，设计书 8 章）。"""

    __tablename__ = "model_version"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="模型编号")
    name: Mapped[str] = mapped_column(String(128), comment="模型名称")
    # 类型: api | finetuned
    type: Mapped[str] = mapped_column(String(16), comment="模型类型")
    # 状态: online | deploying | deployed | offline | failed
    status: Mapped[str] = mapped_column(String(16), default="offline", comment="模型状态")
    endpoint: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, comment="推理服务地址")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, comment="当前是否生效")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
