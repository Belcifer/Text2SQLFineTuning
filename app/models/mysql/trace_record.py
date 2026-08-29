from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mysql.base import Base


class TraceRecord(Base):
    """线上问数链路 trace（设计书 5.6 节，API 文档 4.3 节）。"""

    __tablename__ = "trace_record"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="trace编号")
    thread_id: Mapped[str] = mapped_column(String(64), default="", comment="会话编号")
    query: Mapped[str] = mapped_column(Text, comment="用户问题")
    final_sql: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="最终SQL")
    execution_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="执行错误")
    nodes: Mapped[list] = mapped_column(JSON, default=list, comment="各节点输入输出")
    user_feedback: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment="用户反馈")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
