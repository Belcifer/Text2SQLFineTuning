from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mysql.base import Base


class FinetuneJob(Base):
    """微调训练任务（API 文档 5 节）。"""

    __tablename__ = "finetune_job"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="任务编号")
    name: Mapped[str] = mapped_column(String(128), comment="任务名称")
    base_model: Mapped[str] = mapped_column(String(128), comment="基座模型")
    method: Mapped[str] = mapped_column(String(32), default="qlora", comment="微调方法")
    datasets: Mapped[list] = mapped_column(JSON, default=list, comment="训练数据集 [{dataset_id, weight}]")
    hyperparams: Mapped[dict] = mapped_column(JSON, default=dict, comment="训练超参")
    # 状态: queued | running | success | failed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True, comment="任务状态")
    progress: Mapped[float] = mapped_column(Float, default=0.0, comment="进度 0~1")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, comment="训练指标 step/loss/eval_loss/lr")
    output: Mapped[dict] = mapped_column(JSON, default=dict, comment="产物 adapter_path/checkpoint")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="结束时间")
