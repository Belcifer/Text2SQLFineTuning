"""线上 trace 采集（设计书 5.6 节，API 文档 4.3 节）。

由 QueryService 在主链路旁路调用：采集开关关闭时不执行任何操作；
采集使用独立 session，采集失败只记日志，绝不影响主链路查询结果。
"""
from __future__ import annotations

import uuid
from typing import Optional

from app.clients.mysql_client_manager import meta_mysql_client_manager
from app.conf.app_config import app_config
from app.core.log import logger
from app.finetune.sample_repo import TraceRepo


def trace_enabled() -> bool:
    return bool(app_config.finetune.trace.enable)


class TraceCollector:
    """组装一次问数链路为 trace 并异步落库（独立 session，旁路执行）。"""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or meta_mysql_client_manager.sesion_factory

    def new_trace_id(self) -> str:
        return uuid.uuid4().hex

    def start_trace(self, query: str, thread_id: str = "") -> dict:
        """创建一次链路的 trace 骨架。"""
        return {
            "trace_id": self.new_trace_id(),
            "thread_id": thread_id,
            "query": query,
            "final_sql": None,
            "execution_error": None,
            "nodes": [],
            "user_feedback": None,
        }

    def add_node(self, trace: dict, node: str, payload: dict):
        """记录一个节点的输入输出（可选字段）。"""
        trace["nodes"].append({"node": node, **payload})

    def finish(self, trace: dict, final_sql: Optional[str] = None, execution_error: Optional[str] = None):
        trace["final_sql"] = final_sql
        trace["execution_error"] = execution_error

    async def persist(self, trace: dict):
        """旁路落库（独立 session），失败不影响主链路。"""
        if not trace_enabled():
            return
        try:
            async with self._session_factory() as session:
                await TraceRepo(session).add_trace(trace)
                await session.commit()
            logger.info(f"trace 采集成功: {trace['trace_id']}")
        except Exception as e:
            logger.error(f"trace 采集失败: {str(e)}")
