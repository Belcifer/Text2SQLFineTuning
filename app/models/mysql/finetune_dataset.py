from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mysql.base import Base


class FinetuneDataset(Base):
    """微调数据集（API 文档 4.1 节）。"""

    __tablename__ = "finetune_dataset"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="数据集编号")
    name: Mapped[str] = mapped_column(String(128), comment="数据集名称")
    description: Mapped[str] = mapped_column(Text, comment="数据集描述")
    dialect: Mapped[str] = mapped_column(String(32), default="mysql", comment="目标方言")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
