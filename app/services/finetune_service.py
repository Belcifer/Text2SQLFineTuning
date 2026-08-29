"""微调服务（API 文档 4/5/6 节）。

请求级 session 由依赖注入提供；后台训练/评估任务使用独立 session，
避免与请求生命周期耦合。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.mysql_client_manager import meta_mysql_client_manager
from app.core.errors import not_found, validation_error
from app.core.log import logger
from app.finetune.exporter import export_samples
from app.finetune.sample_repo import (
    FinetuneEvalRepo,
    FinetuneJobRepo,
    FinetuneRepo,
    TraceRepo,
)
from app.models.mysql.finetune_sample import FinetuneSample


def _sample_to_dict(sample: FinetuneSample) -> dict:
    return {
        "id": sample.id,
        "dataset_id": sample.dataset_id,
        "task": sample.task,
        "source": sample.source,
        "ability_tags": sample.ability_tags,
        "database": sample.database,
        "dialect": sample.dialect,
        "context": sample.context,
        "instruction": sample.instruction,
        "input": sample.input,
        "output": sample.output,
        "meta": sample.meta,
        "created_at": sample.created_at.isoformat() if sample.created_at else None,
    }


class FinetuneService:
    def __init__(self, meta_session: AsyncSession):
        self.session = meta_session
        self.repo = FinetuneRepo(meta_session)
        self.job_repo = FinetuneJobRepo(meta_session)
        self.eval_repo = FinetuneEvalRepo(meta_session)
        self.trace_repo = TraceRepo(meta_session)

    # ==================== 数据集（API 文档 4.1） ====================

    async def create_dataset(self, name: str, description: str, dialect: str) -> dict:
        dataset_id = uuid.uuid4().hex
        # commit 前收集返回值（避免 commit 后 ORM 属性过期触发同步 IO）
        await self.repo.create_dataset(dataset_id, name, description, dialect)
        await self.session.commit()
        return {"dataset_id": dataset_id, "name": name,
                "description": description, "dialect": dialect}

    async def list_datasets(self, page: int = 1, page_size: int = 20) -> dict:
        datasets, total = await self.repo.list_datasets(page, page_size)
        items = [{"dataset_id": d.id, "name": d.name, "description": d.description,
                  "dialect": d.dialect, "created_at": d.created_at.isoformat() if d.created_at else None}
                 for d in datasets]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def get_dataset(self, dataset_id: str) -> dict:
        dataset = await self.repo.get_dataset(dataset_id)
        if dataset is None:
            raise not_found("数据集")
        stats = await self.repo.dataset_stats(dataset_id)
        return {"dataset_id": dataset.id, "name": dataset.name, "description": dataset.description,
                "dialect": dataset.dialect, "stats": stats,
                "created_at": dataset.created_at.isoformat() if dataset.created_at else None}

    # ==================== 样本（API 文档 4.2） ====================

    async def add_samples(self, dataset_id: str, samples: list[dict]) -> dict:
        if await self.repo.get_dataset(dataset_id) is None:
            raise not_found("数据集")
        result = await self.repo.add_samples(dataset_id, samples)
        await self.session.commit()
        return result

    async def list_samples(self, dataset_id: str, task: Optional[str] = None,
                           source: Optional[str] = None, quality: Optional[str] = None,
                           difficulty: Optional[str] = None,
                           page: int = 1, page_size: int = 20) -> dict:
        rows, total = await self.repo.list_samples(dataset_id, task, source, quality, difficulty, page, page_size)
        return {"items": [_sample_to_dict(r) for r in rows], "total": total,
                "page": page, "page_size": page_size}

    async def patch_sample(self, dataset_id: str, sample_id: str, patch: dict) -> dict:
        sample = await self.repo.update_sample(dataset_id, sample_id, patch)
        if sample is None:
            raise not_found("样本")
        result = _sample_to_dict(sample)  # commit 前收集
        await self.session.commit()
        return result

    async def export_dataset(self, dataset_id: str, format_: str = "alpaca",
                             task_filter: Optional[list[str]] = None,
                             train_ratio: float = 0.9, seed: int = 42) -> dict:
        if await self.repo.get_dataset(dataset_id) is None:
            raise not_found("数据集")
        samples: list[dict] = []
        page = 1
        while True:
            rows, total = await self.repo.list_samples(
                dataset_id, quality="passed", page=page, page_size=200)
            samples.extend(_sample_to_dict(r) for r in rows)
            if page * 200 >= total:
                break
            page += 1
        if task_filter:
            samples = [s for s in samples if s["task"] in task_filter]
        if not samples:
            raise validation_error("该数据集没有可导出的样本（quality=passed 为空或 task_filter 无匹配）")
        return export_samples(samples, format_=format_, train_ratio=train_ratio, seed=seed)

    # ==================== trace 上报（API 文档 4.3） ====================

    async def report_traces(self, traces: list[dict]) -> dict:
        for trace in traces:
            await self.trace_repo.add_trace(trace)
        await self.session.commit()
        return {"accepted": len(traces)}

    # ==================== 训练任务（API 文档 5） ====================

    async def submit_job(self, name: str, base_model: str, method: str,
                         datasets: list[dict], hyperparams: dict) -> dict:
        for ds in datasets:
            if await self.repo.get_dataset(ds["dataset_id"]) is None:
                raise not_found(f"数据集 {ds['dataset_id']}")
        job_id = uuid.uuid4().hex
        job = await self.job_repo.create_job(
            job_id, name, base_model, method, datasets, hyperparams)
        await self.session.commit()
        params = {"job_id": job_id, "name": name, "base_model": base_model,
                  "method": method, "datasets": datasets, "hyperparams": hyperparams}
        asyncio.create_task(_run_job_async(job_id, params))
        return {"job_id": job_id, "status": "queued"}

    async def get_job(self, job_id: str) -> dict:
        job = await self.job_repo.get_job(job_id)
        if job is None:
            raise not_found("训练任务")
        return _job_to_dict(job)

    async def list_jobs(self, status: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        jobs, total = await self.job_repo.list_jobs(status, page, page_size)
        return {"items": [_job_to_dict(j) for j in jobs], "total": total,
                "page": page, "page_size": page_size}

    async def cancel_job(self, job_id: str) -> dict:
        job = await self.job_repo.get_job(job_id)
        if job is None:
            raise not_found("训练任务")
        if job.status not in ("queued", "running"):
            raise validation_error(f"当前状态 {job.status} 不允许取消")
        job.status = "cancelled"
        job.finished_at = datetime.utcnow()
        await self.session.commit()
        return {"job_id": job_id, "status": "cancelled"}

    # ==================== 评估（API 文档 6） ====================

    async def submit_evaluation(self, name: str, model: str, eval_set: dict,
                                baseline_model: Optional[str], dimensions: list[str]) -> dict:
        eval_id = uuid.uuid4().hex
        evaluation = await self.eval_repo.create_evaluation(
            eval_id, name, model, eval_set, baseline_model, dimensions)
        await self.session.commit()
        params = {"evaluation_id": eval_id, "name": name, "model": model,
                  "eval_set": eval_set, "baseline_model": baseline_model, "dimensions": dimensions}
        asyncio.create_task(_run_eval_async(eval_id, params))
        return {"evaluation_id": eval_id, "status": "queued"}

    async def get_evaluation(self, eval_id: str) -> dict:
        evaluation = await self.eval_repo.get_evaluation(eval_id)
        if evaluation is None:
            raise not_found("评估任务")
        return {
            "evaluation_id": evaluation.id,
            "status": evaluation.status,
            "model": evaluation.model,
            "baseline": evaluation.baseline_model,
            "report": evaluation.report,
            "passed": evaluation.passed,
            "created_at": evaluation.created_at.isoformat() if evaluation.created_at else None,
            "finished_at": evaluation.finished_at.isoformat() if evaluation.finished_at else None,
        }


def _job_to_dict(job) -> dict:
    return {
        "job_id": job.id,
        "name": job.name,
        "base_model": job.base_model,
        "method": job.method,
        "datasets": job.datasets,
        "hyperparams": job.hyperparams,
        "status": job.status,
        "progress": job.progress,
        "metrics": job.metrics,
        "output": job.output,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


# ==================== 后台任务（独立 session） ====================

async def _load_passed_samples(session: AsyncSession, datasets: list[dict]) -> list[dict]:
    repo = FinetuneRepo(session)
    samples: list[dict] = []
    for ds in datasets:
        page = 1
        while True:
            rows, total = await repo.list_samples(ds["dataset_id"], quality="passed", page=page, page_size=200)
            samples.extend(_sample_to_dict(r) for r in rows)
            if page * 200 >= total:
                break
            page += 1
    return samples


async def _run_job_async(job_id: str, params: dict):
    from app.finetune import trainer

    async with meta_mysql_client_manager.sesion_factory() as session:
        try:
            job_repo = FinetuneJobRepo(session)
            job = await job_repo.get_job(job_id)
            if job is None or job.status == "cancelled":
                return
            job.status = "running"
            job.progress = 0.05
            await session.commit()

            samples = await _load_passed_samples(session, params["datasets"])
            job_params = {**params, "_samples": samples}
            result = await asyncio.to_thread(trainer.run_job, job_params)
            job = await job_repo.get_job(job_id)
            job.status = "success"
            job.progress = 1.0
            job.output = result
            job.finished_at = datetime.utcnow()
        except Exception as e:
            logger.error(f"训练任务失败: {job_id} {str(e)}")
            job = await job_repo.get_job(job_id)
            if job is not None:
                job.status = "failed"
                job.error = str(e)
                job.finished_at = datetime.utcnow()
        await session.commit()


async def _run_eval_async(eval_id: str, params: dict):
    from app.clients.mysql_client_manager import dw_mysql_client_manager
    from app.finetune import evaluator
    from app.finetune.sample_repo import ModelRepo
    from app.repositories.mysql.dw_mysql_repository import DWMysqlRepository

    async with meta_mysql_client_manager.sesion_factory() as session:
        try:
            eval_repo = FinetuneEvalRepo(session)
            evaluation = await eval_repo.get_evaluation(eval_id)
            if evaluation is None:
                return
            evaluation.status = "running"
            await session.commit()

            # 模型推理 endpoint（从模型版本表获取，缺省指向本机 vLLM）
            model = await ModelRepo(session).get_model(params["model"])
            endpoint = (model.endpoint if model and model.endpoint else "http://localhost:8000/v1")

            samples = await _load_passed_samples(session, [params["eval_set"]])
            async with dw_mysql_client_manager.sesion_factory() as dw_session:
                dw_repo = DWMysqlRepository(dw_session)
                result = await evaluator.run_evaluation(
                    params, samples, dw_mysql_repo=dw_repo, llm_endpoint=endpoint,
                    model_name=params["model"])
            evaluation = await eval_repo.get_evaluation(eval_id)
            evaluation.status = "success"
            evaluation.report = result.get("report", {})
            evaluation.passed = result.get("report", {}).get("execution_accuracy", 0.0) >= 0.8
            evaluation.finished_at = datetime.utcnow()
        except Exception as e:
            logger.error(f"评估任务失败: {eval_id} {str(e)}")
            evaluation = await eval_repo.get_evaluation(eval_id)
            if evaluation is not None:
                evaluation.status = "failed"
                evaluation.finished_at = datetime.utcnow()
        await session.commit()
