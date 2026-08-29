from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mysql.base import Base


class FinetuneEvaluation(Base):
    """离线评估任务（API 文档 6 节，设计书第 7 章）。"""

    __tablename__ = "finetune_evaluation"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="评估编号")
    name: Mapped[str] = mapped_column(String(128), comment="评估名称")
    model: Mapped[str] = mapped_column(String(128), comment="被评估模型")
    eval_set: Mapped[dict] = mapped_column(JSON, default=dict, comment="评测集 {dataset_id}")
    baseline_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="基线模型")
    dimensions: Mapped[list] = mapped_column(JSON, default=list, comment="评估维度")
    # 状态: queued | running | success | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True, comment="评估状态")
    report: Mapped[dict] = mapped_column(JSON, default=dict, comment="评估报告")
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, comment="是否达标")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="结束时间")
