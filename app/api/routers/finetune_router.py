from typing import Optional

from fastapi import APIRouter, Query
from fastapi.params import Depends

from app.api.dependencies import get_finetune_service
from app.api.schemas.finetune_schema import (
    DatasetCreateSchema,
    EvalCreateSchema,
    ExportSchema,
    JobCreateSchema,
    SamplePatchSchema,
    SamplesImportSchema,
    TracesReportSchema,
)
from app.conf.app_config import app_config
from app.core.errors import validation_error
from app.core.response import ok
from app.services.finetune_service import FinetuneService

# 微调子系统路由（API 文档 4/5/6 节）
finetune_router = APIRouter()


# ==================== 数据集（4.1） ====================

@finetune_router.post("/api/v1/finetune/datasets")
async def create_dataset(params: DatasetCreateSchema, service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.create_dataset(params.name, params.description, params.dialect))


@finetune_router.get("/api/v1/finetune/datasets")
async def list_datasets(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
                        service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.list_datasets(page, page_size))


@finetune_router.get("/api/v1/finetune/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.get_dataset(dataset_id))


# ==================== 样本（4.2） ====================

@finetune_router.post("/api/v1/finetune/datasets/{dataset_id}/samples")
async def import_samples(dataset_id: str, params: SamplesImportSchema,
                         service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.add_samples(dataset_id, params.samples))


@finetune_router.get("/api/v1/finetune/datasets/{dataset_id}/samples")
async def list_samples(dataset_id: str,
                       task: Optional[str] = Query(None),
                       source: Optional[str] = Query(None),
                       quality: Optional[str] = Query(None),
                       difficulty: Optional[str] = Query(None),
                       page: int = Query(1, ge=1),
                       page_size: int = Query(20, ge=1, le=200),
                       service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.list_samples(dataset_id, task, source, quality, difficulty, page, page_size))


@finetune_router.patch("/api/v1/finetune/datasets/{dataset_id}/samples/{sample_id}")
async def patch_sample(dataset_id: str, sample_id: str, params: SamplePatchSchema,
                       service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.patch_sample(dataset_id, sample_id, params.model_dump(exclude_none=True)))


# ==================== 导出（4.4） ====================

@finetune_router.post("/api/v1/finetune/datasets/{dataset_id}/export")
async def export_dataset(dataset_id: str, params: ExportSchema,
                         service: FinetuneService = Depends(get_finetune_service)):
    train_ratio = params.split.get("train", 0.9) if params.split else 0.9
    return ok(await service.export_dataset(dataset_id, params.format, params.task_filter,
                                           float(train_ratio), params.seed))


# ==================== trace（4.3） ====================

@finetune_router.post("/api/v1/finetune/traces")
async def report_traces(params: TracesReportSchema, service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.report_traces(params.traces))


# ==================== 训练任务（5） ====================

@finetune_router.post("/api/v1/finetune/jobs")
async def submit_job(params: JobCreateSchema, service: FinetuneService = Depends(get_finetune_service)):
    base_model = params.base_model or app_config.finetune.base_model
    hyperparams = params.hyperparams or dict(app_config.finetune.default_hyperparams)
    return ok(await service.submit_job(params.name, base_model, params.method,
                                       params.datasets, hyperparams))


@finetune_router.get("/api/v1/finetune/jobs")
async def list_jobs(status: Optional[str] = Query(None), page: int = Query(1, ge=1),
                    page_size: int = Query(20, ge=1, le=200),
                    service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.list_jobs(status, page, page_size))


@finetune_router.get("/api/v1/finetune/jobs/{job_id}")
async def get_job(job_id: str, service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.get_job(job_id))


@finetune_router.post("/api/v1/finetune/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.cancel_job(job_id))


@finetune_router.get("/api/v1/finetune/jobs/{job_id}/metrics")
async def job_metrics(job_id: str, service: FinetuneService = Depends(get_finetune_service)):
    job = await service.get_job(job_id)
    metrics = job.get("metrics") or {}
    return ok({"loss": metrics.get("loss", []), "eval_loss": metrics.get("eval_loss", [])})


# ==================== 评估（6） ====================

@finetune_router.post("/api/v1/finetune/evaluations")
async def submit_evaluation(params: EvalCreateSchema,
                            service: FinetuneService = Depends(get_finetune_service)):
    if "dataset_id" not in params.eval_set:
        raise validation_error("eval_set 必须包含 dataset_id")
    return ok(await service.submit_evaluation(params.name, params.model, params.eval_set,
                                              params.baseline_model, params.dimensions))


@finetune_router.get("/api/v1/finetune/evaluations/{evaluation_id}")
async def get_evaluation(evaluation_id: str, service: FinetuneService = Depends(get_finetune_service)):
    return ok(await service.get_evaluation(evaluation_id))
