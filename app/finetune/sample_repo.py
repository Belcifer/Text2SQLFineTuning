"""微调子系统持久层（设计书附录 sample_repo.py，API 文档 4/5/6/7 章）。

基于 meta 库（meta_mysql_client_manager 的 session）读写微调相关表。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finetune.sample_schema import validate_sample
from app.models.mysql.finetune_dataset import FinetuneDataset
from app.models.mysql.finetune_evaluation import FinetuneEvaluation
from app.models.mysql.finetune_job import FinetuneJob
from app.models.mysql.finetune_sample import FinetuneSample
from app.models.mysql.model_version import ModelVersion
from app.models.mysql.trace_record import TraceRecord


# ==================== 数据集与样本 ====================

class FinetuneRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ---- 数据集 ----
    async def create_dataset(self, dataset_id: str, name: str, description: str, dialect: str) -> FinetuneDataset:
        dataset = FinetuneDataset(id=dataset_id, name=name, description=description, dialect=dialect)
        self.session.add(dataset)
        return dataset

    async def get_dataset(self, dataset_id: str) -> Optional[FinetuneDataset]:
        return await self.session.get(FinetuneDataset, dataset_id)

    async def list_datasets(self, page: int = 1, page_size: int = 20) -> tuple[list[FinetuneDataset], int]:
        total = (await self.session.execute(select(func.count(FinetuneDataset.id)))).scalar() or 0
        result = await self.session.execute(
            Select(FinetuneDataset).order_by(FinetuneDataset.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return result.scalars().all(), total

    async def delete_dataset(self, dataset_id: str) -> bool:
        dataset = await self.get_dataset(dataset_id)
        if dataset is None:
            return False
        await self.session.delete(dataset)
        return True

    # ---- 样本 ----
    async def add_samples(self, dataset_id: str, samples: list[dict]) -> dict:
        """批量导入样本，执行质量校验（设计书 5.4 四重校验的纯逻辑部分）。

        返回 {"imported": n, "rejected": m, "reject_reasons": [{"id","reason"}]}
        """
        imported = 0
        reject_reasons: list[dict] = []
        for sample in samples:
            errors = validate_sample(sample)
            if errors:
                reject_reasons.append({"id": sample.get("id"), "reason": "; ".join(errors)})
                continue
            meta = dict(sample.get("meta") or {})
            meta["quality"] = "passed"
            self.session.add(FinetuneSample(
                id=sample["id"],
                dataset_id=dataset_id,
                task=sample["task"],
                source=sample.get("source", "synthetic"),
                ability_tags=sample.get("ability_tags", []),
                database=sample.get("database", "mysql"),
                dialect=sample.get("dialect", "mysql 8.0"),
                context=sample.get("context", {}),
                instruction=sample.get("instruction", ""),
                input=sample["input"],
                output=sample["output"],
                meta=meta,
            ))
            imported += 1
        return {"imported": imported, "rejected": len(reject_reasons), "reject_reasons": reject_reasons}

    async def list_samples(
        self,
        dataset_id: str,
        task: Optional[str] = None,
        source: Optional[str] = None,
        quality: Optional[str] = None,
        difficulty: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FinetuneSample], int]:
        query = Select(FinetuneSample).where(FinetuneSample.dataset_id == dataset_id)
        count_query = select(func.count(FinetuneSample.id)).where(FinetuneSample.dataset_id == dataset_id)
        if task:
            query = query.where(FinetuneSample.task == task)
            count_query = count_query.where(FinetuneSample.task == task)
        if source:
            query = query.where(FinetuneSample.source == source)
            count_query = count_query.where(FinetuneSample.source == source)
        if quality:
            query = query.where(FinetuneSample.meta["quality"].as_string() == quality)
            count_query = count_query.where(FinetuneSample.meta["quality"].as_string() == quality)
        if difficulty:
            query = query.where(FinetuneSample.meta["difficulty"].as_string() == difficulty)
            count_query = count_query.where(FinetuneSample.meta["difficulty"].as_string() == difficulty)
        total = (await self.session.execute(count_query)).scalar() or 0
        result = await self.session.execute(
            query.order_by(FinetuneSample.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return result.scalars().all(), total

    async def get_sample(self, dataset_id: str, sample_id: str) -> Optional[FinetuneSample]:
        return await self.session.get(FinetuneSample, sample_id)

    async def update_sample(self, dataset_id: str, sample_id: str, patch: dict) -> Optional[FinetuneSample]:
        sample = await self.session.get(FinetuneSample, sample_id)
        if sample is None or sample.dataset_id != dataset_id:
            return None
        if "output" in patch:
            sample.output = patch["output"]
        if "meta" in patch:
            meta = dict(sample.meta or {})
            meta.update(patch["meta"])
            sample.meta = meta
        return sample

    async def dataset_stats(self, dataset_id: str) -> dict:
        total = (await self.session.execute(
            select(func.count(FinetuneSample.id)).where(FinetuneSample.dataset_id == dataset_id)
        )).scalar() or 0
        rows = (await self.session.execute(
            Select(FinetuneSample.task, func.count(FinetuneSample.id))
            .where(FinetuneSample.dataset_id == dataset_id)
            .group_by(FinetuneSample.task)
        )).all()
        by_task = {task: count for task, count in rows}
        passed = (await self.session.execute(
            select(func.count(FinetuneSample.id)).where(
                FinetuneSample.dataset_id == dataset_id,
                FinetuneSample.meta["quality"].as_string() == "passed",
            )
        )).scalar() or 0
        return {"total": total, "by_task": by_task, "quality_passed": passed, "quality_rejected": total - passed}


# ==================== 训练任务 / 评估 / 模型 / trace ====================

class FinetuneJobRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_job(self, job_id: str, name: str, base_model: str, method: str,
                         datasets: list, hyperparams: dict) -> FinetuneJob:
        job = FinetuneJob(id=job_id, name=name, base_model=base_model, method=method,
                          datasets=datasets, hyperparams=hyperparams)
        self.session.add(job)
        return job

    async def get_job(self, job_id: str) -> Optional[FinetuneJob]:
        return await self.session.get(FinetuneJob, job_id)

    async def list_jobs(self, status: Optional[str] = None, page: int = 1, page_size: int = 20) -> tuple[list[FinetuneJob], int]:
        query = Select(FinetuneJob)
        count_query = select(func.count(FinetuneJob.id))
        if status:
            query = query.where(FinetuneJob.status == status)
            count_query = count_query.where(FinetuneJob.status == status)
        total = (await self.session.execute(count_query)).scalar() or 0
        result = await self.session.execute(
            query.order_by(FinetuneJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return result.scalars().all(), total


class FinetuneEvalRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_evaluation(self, eval_id: str, name: str, model: str, eval_set: dict,
                                baseline_model: Optional[str], dimensions: list) -> FinetuneEvaluation:
        evaluation = FinetuneEvaluation(
            id=eval_id, name=name, model=model, eval_set=eval_set,
            baseline_model=baseline_model, dimensions=dimensions,
        )
        self.session.add(evaluation)
        return evaluation

    async def get_evaluation(self, eval_id: str) -> Optional[FinetuneEvaluation]:
        return await self.session.get(FinetuneEvaluation, eval_id)


class ModelRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_models(self) -> list[ModelVersion]:
        result = await self.session.execute(Select(ModelVersion).order_by(ModelVersion.created_at.desc()))
        return result.scalars().all()

    async def get_model(self, model_id: str) -> Optional[ModelVersion]:
        return await self.session.get(ModelVersion, model_id)

    async def create_model(self, model_id: str, name: str, type_: str, status: str = "offline") -> ModelVersion:
        model = ModelVersion(id=model_id, name=name, type=type_, status=status)
        self.session.add(model)
        return model

    async def clear_active(self):
        """将所有模型置为非生效，用于激活切换。"""
        active = (await self.session.execute(
            Select(ModelVersion).where(ModelVersion.is_active.is_(True))
        )).scalars().all()
        for model in active:
            model.is_active = False


class TraceRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_trace(self, trace: dict):
        self.session.add(TraceRecord(
            id=trace["trace_id"],
            thread_id=trace.get("thread_id", ""),
            query=trace.get("query", ""),
            final_sql=trace.get("final_sql"),
            execution_error=trace.get("execution_error"),
            nodes=trace.get("nodes", []),
            user_feedback=trace.get("user_feedback"),
            created_at=datetime.utcnow(),
        ))
