from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mysql.base import Base


class FinetuneSample(Base):
    """微调训练样本，统一 schema 见设计书 5.2 节（API 文档 4.2 节）。"""

    __tablename__ = "finetune_sample"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="样本编号")
    dataset_id: Mapped[str] = mapped_column(String(64), index=True, comment="所属数据集编号")
    # 子任务类型: sql_generation | sql_correction | schema_linking |
    #           value_standardization | metric_resolution | clarification
    task: Mapped[str] = mapped_column(String(32), index=True, comment="子任务类型")
    # 来源: synthetic | trace | human | open
    source: Mapped[str] = mapped_column(String(16), default="synthetic", comment="样本来源")
    ability_tags: Mapped[list] = mapped_column(JSON, default=list, comment="能力标签，如[\"4.2.5\"]")
    database: Mapped[str] = mapped_column(String(32), default="mysql", comment="目标数据库")
    dialect: Mapped[str] = mapped_column(String(32), default="mysql 8.0", comment="SQL方言")
    # 检索上下文: table_infos / metric_infos / value_infos / date_info / db_info
    context: Mapped[dict] = mapped_column(JSON, default=dict, comment="上下文信息")
    instruction: Mapped[str] = mapped_column(Text, default="", comment="指令")
    input: Mapped[str] = mapped_column(Text, comment="用户问题")
    output: Mapped[str] = mapped_column(Text, comment="标准输出(SQL文本或JSON)")
    # 标注元信息: difficulty / annotator / quality / has_join / has_clarify
    meta: Mapped[dict] = mapped_column(JSON, default=dict, comment="标注元信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
