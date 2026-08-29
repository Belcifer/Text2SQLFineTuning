"""问数微调平台应用入口。

启动：uvicorn main:app --host 0.0.0.0 --port 8000
接口文档：http://localhost:8000/docs （见 docs/API文档.md）
"""
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers.finetune_router import finetune_router
from app.api.routers.knowledge_router import knowledge_router
from app.api.routers.model_router import model_router
from app.api.routers.query_router import query_router
from app.core.context import reset_request_id, set_request_id
from app.core.errors import CODE_INTERNAL, BizError
from app.core.lifespan import lifespan
from app.core.log import logger
from app.core.response import error

app = FastAPI(
    title="问数微调平台",
    description="Text2SQL 问数 Agent + 微调子系统（docs/API文档.md）",
    version="1.0.0",
    lifespan=lifespan,
)

# 开发期跨域（生产按需收紧）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求级 trace_id（贯穿日志与响应）
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    token = set_request_id(uuid.uuid4().hex)
    try:
        return await call_next(request)
    finally:
        reset_request_id(token)


# 统一异常处理（API 文档 1.2/1.3 节）
@app.exception_handler(BizError)
async def biz_error_handler(request: Request, exc: BizError):
    return JSONResponse(status_code=200, content=error(exc.code, exc.message))


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception):
    logger.exception("未捕获异常: %s", exc)
    return JSONResponse(status_code=500, content=error(CODE_INTERNAL, "系统内部错误"))


@app.get("/health")
async def health():
    return {"status": "ok"}


# 注册路由
app.include_router(query_router)
app.include_router(knowledge_router)
app.include_router(finetune_router)
app.include_router(model_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
