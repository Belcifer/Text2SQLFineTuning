from fastapi import APIRouter, Request
from fastapi.params import Depends
from starlette.responses import StreamingResponse

from app.api.dependencies import get_query_service
from app.api.schemas.query_schema import FollowupSchema, QuerySchema
from app.core.response import ok
from app.services.query_service import QueryService, query_session_store

# 问数查询路由（API 文档 2 节）
query_router = APIRouter()


@query_router.post("/api/v1/query")
async def query(params: QuerySchema, service: QueryService = Depends(get_query_service)):
    """SSE 流式问数（event: stage/clarify/result/done/error）。"""
    return StreamingResponse(
        service.stream(params.query, params.thread_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@query_router.post("/api/v1/query/sync")
async def query_sync(params: QuerySchema, service: QueryService = Depends(get_query_service)):
    """非流式问数（一次性返回 SQL 与结果）。"""
    return ok(await service.search_sync(params.query, params.thread_id))


@query_router.post("/api/v1/query/followup")
async def query_followup(params: FollowupSchema, request: Request,
                         service: QueryService = Depends(get_query_service)):
    """澄清追问（复用 thread_id 会话），响应按 Accept 头区分流式/非流式。"""
    merged = query_session_store.merge_query(params.thread_id, "", params.query)
    if "text/event-stream" in request.headers.get("accept", ""):
        return StreamingResponse(
            service.stream(merged, params.thread_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return ok(await service.search_sync(merged, params.thread_id))
