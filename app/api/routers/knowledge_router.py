from fastapi import APIRouter
from fastapi.params import Depends

from app.api.dependencies import get_build_runner
from app.api.schemas.knowledge_schema import BuildSchema
from app.core.errors import not_found
from app.core.response import ok
from app.services.knowledge_service import knowledge_service

# 知识库构建路由（API 文档 3 节）
knowledge_router = APIRouter()


@knowledge_router.post("/api/v1/knowledge/build")
async def build(params: BuildSchema, runner=Depends(get_build_runner)):
    """触发知识库构建（后台异步执行）。"""
    record = await knowledge_service.start_build(runner, scope=params.scope, reset=params.reset)
    return ok({"build_id": record["build_id"], "status": record["status"]})


@knowledge_router.get("/api/v1/knowledge/build/{build_id}")
async def build_status(build_id: str):
    """查询构建状态。"""
    record = knowledge_service.get_status(build_id)
    if record is None:
        raise not_found("构建任务")
    return ok({
        "build_id": record["build_id"],
        "status": record["status"],
        "progress": record["progress"],
        "detail": record["detail"],
    })
