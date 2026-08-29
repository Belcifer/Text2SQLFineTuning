"""问数查询服务（API 文档 2 节）。

将 LangGraph Agent 的 custom 流转换为统一的 SSE 事件序列：
stage / clarify / result / done / error。
支持非流式（sync）、澄清追问（followup，thread_id 会话）与 trace 旁路采集。
"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator, Optional

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.agent.context import DataAgentContext
from app.agent.graph import compiled_graph
from app.agent.state import DataAgentState
from app.core.errors import ClarifyRequired
from app.core.log import logger
from app.finetune.data_collector import TraceCollector
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw_mysql_repository import DWMysqlRepository
from app.repositories.mysql.meta_mysql_repository import MetaMysqlRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


class QuerySessionStore:
    """内存会话存储（单进程 v1）：thread_id → 累积问题。

    多实例部署时建议替换为 Redis/DB 实现。
    """

    def __init__(self):
        self._store: dict[str, str] = {}

    def merge_query(self, thread_id: str, base_query: str, followup: str) -> str:
        """将澄清补充并入原问题，返回重跑用的问题文本。"""
        if not thread_id:
            return followup
        prev = self._store.get(thread_id) or base_query
        merged = f"{prev}；补充：{followup}" if prev else followup
        self._store[thread_id] = merged
        return merged


# 全局会话存储
query_session_store = QuerySessionStore()


class QueryService:
    def __init__(
        self,
        dw_mysql_repo: DWMysqlRepository,
        meta_mysql_repo: MetaMysqlRepository,
        value_es_repo: ValueESRepository,
        column_qdrant_repo: ColumnQdrantRepository,
        metric_qdrant_repo: MetricQdrantRepository,
        embedding_client: HuggingFaceEndpointEmbeddings,
    ):
        self.dw_mysql_repo = dw_mysql_repo
        self.meta_mysql_repo = meta_mysql_repo
        self.value_es_repo = value_es_repo
        self.column_qdrant_repo = column_qdrant_repo
        self.metric_qdrant_repo = metric_qdrant_repo
        self.embedding_client = embedding_client

    def _build_context(self) -> DataAgentContext:
        return DataAgentContext(
            dw_mysql_repo=self.dw_mysql_repo,
            meta_mysql_repo=self.meta_mysql_repo,
            value_es_repo=self.value_es_repo,
            column_qdrant_repo=self.column_qdrant_repo,
            metric_qdrant_repo=self.metric_qdrant_repo,
            embedding_client=self.embedding_client,
        )

    async def _events(self, query: str) -> AsyncIterator[tuple[str, dict]]:
        """执行图，产出 (event, data) 序列（API 文档 2.1 事件协议）。"""
        state = DataAgentState(query=query)
        context = self._build_context()
        final_sql = None
        execution_error = None
        try:
            async for chunk in compiled_graph.astream(
                input=state,
                context=context,
                stream_mode="custom",
            ):
                if "stage" in chunk:
                    yield "stage", chunk
                elif "result" in chunk:
                    final_sql = chunk.get("sql") or final_sql
                    yield "result", chunk
                elif "clarify" in chunk:
                    yield "clarify", chunk
        except ClarifyRequired as e:
            # 信息不足：澄清事件（设计书 4.4）
            yield "clarify", {"need_clarify": True, "questions": e.questions}
            return
        except Exception as e:
            logger.error(f"搜索失败： {str(e)}")
            execution_error = str(e)
            yield "error", {"code": 50000, "message": str(e)}
            return
        yield "done", {"final_sql": final_sql, "execution_error": execution_error}

    # ---- SSE 流式 ----
    async def stream(self, query: str, thread_id: str = "") -> AsyncIterator[str]:
        """SSE 文本流：event: stage|clarify|result|done|error + data: JSON。"""
        collector = TraceCollector()
        trace = collector.start_trace(query, thread_id)
        started = time.time()
        try:
            async for event, data in self._events(query):
                if event == "stage":
                    yield _sse(event, data)
                elif event == "clarify":
                    data["thread_id"] = thread_id
                    yield _sse(event, data)
                    collector.finish(trace, execution_error="clarify_required")
                elif event == "result":
                    data["latency_ms"] = int((time.time() - started) * 1000)
                    yield _sse(event, data)
                elif event == "done":
                    yield _sse(event, data)
                elif event == "error":
                    yield _sse(event, data)
        finally:
            await collector.persist(trace)

    # ---- 非流式 ----
    async def search_sync(self, query: str, thread_id: str = "") -> dict:
        """收集全部事件，返回一次性结果（API 文档 2.2 节）。"""
        collector = TraceCollector()
        trace = collector.start_trace(query, thread_id)
        started = time.time()
        stages: list[str] = []
        sql: Optional[str] = None
        rows: list = []
        need_clarify = False
        questions: list[str] = []
        try:
            async for event, data in self._events(query):
                if event == "stage":
                    stages.append(data.get("stage", ""))
                elif event == "result":
                    sql = data.get("sql")
                    rows = data.get("result", [])
                elif event == "clarify":
                    need_clarify = True
                    questions = data.get("questions", [])
                elif event == "error":
                    raise RuntimeError(data.get("message", "搜索失败"))
        finally:
            collector.finish(trace, final_sql=sql)
            await collector.persist(trace)

        columns = list(rows[0].keys()) if rows else []
        return {
            "sql": sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "need_clarify": need_clarify,
            "questions": questions,
            "stages": stages,
            "latency_ms": int((time.time() - started) * 1000),
        }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
