from fastapi import APIRouter
from fastapi.params import Depends

from app.api.dependencies import get_model_service
from app.api.schemas.model_schema import ActivateSchema, DeploySchema
from app.core.response import ok
from app.services.model_service import ModelService

# 模型管理路由（API 文档 7 节）
model_router = APIRouter()


@model_router.get("/api/v1/models")
async def list_models(service: ModelService = Depends(get_model_service)):
    return ok(await service.list_models())


@model_router.post("/api/v1/models/{model_id}/deploy")
async def deploy_model(model_id: str, params: DeploySchema,
                       service: ModelService = Depends(get_model_service)):
    return ok(await service.deploy_model(model_id, params.gpu_count, params.max_model_len))


@model_router.post("/api/v1/models/{model_id}/activate")
async def activate_model(model_id: str, params: ActivateSchema,
                         service: ModelService = Depends(get_model_service)):
    return ok(await service.activate_model(model_id, params.ratio))
