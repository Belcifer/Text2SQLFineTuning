"""功能测试（除模型微调外）：覆盖 API 文档 2-7 章不依赖 Qdrant 的接口。

依赖：本地 MySQL（conf/app_config.yaml），自动自清理测试数据。
运行：PYTHONPATH=. ./.venv/Scripts/python.exe scripts/functional_test.py
"""
import asyncio
import time

from fastapi.testclient import TestClient
from sqlalchemy import delete

import main as app_module
from app.clients.mysql_client_manager import meta_mysql_client_manager
from app.conf.meta_config import meta_config
from app.finetune.synthesizer import synthesize_sql_generation
from app.models.mysql.finetune_dataset import FinetuneDataset
from app.models.mysql.finetune_sample import FinetuneSample
from app.models.mysql.model_version import ModelVersion
from app.models.mysql.trace_record import TraceRecord

PASS, FAIL = 0, 0
results: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        results.append(f"[PASS] {name}")
    else:
        FAIL += 1
        results.append(f"[FAIL] {name} {detail}")


async def _cleanup(ds_ids: list[str]):
    meta_mysql_client_manager.init_client()
    try:
        async with meta_mysql_client_manager.sesion_factory() as session:
            for ds_id in ds_ids:
                await session.execute(delete(FinetuneSample).where(FinetuneSample.dataset_id == ds_id))
                await session.execute(delete(FinetuneDataset).where(FinetuneDataset.id == ds_id))
            await session.execute(delete(ModelVersion).where(ModelVersion.id == "func-m"))
            await session.execute(delete(TraceRecord).where(TraceRecord.query == "功能测试问题"))
            await session.commit()
    finally:
        await meta_mysql_client_manager.close()


def main():
    ds_ids: list[str] = []
    with TestClient(app_module.app, raise_server_exceptions=False) as client:
        # ============ A. 基础 ============
        r = client.get("/health")
        check("GET /health", r.status_code == 200 and r.json()["status"] == "ok")
        r = client.get("/openapi.json")
        check("GET /openapi.json", r.status_code == 200)

        # ============ B. 数据集/样本（MySQL） ============
        r = client.post("/api/v1/finetune/datasets",
                        json={"name": "func-test-ds", "description": "t", "dialect": "mysql"})
        check("POST 创建数据集", r.status_code == 200 and r.json()["code"] == 0, r.text)
        ds_id = r.json()["data"]["dataset_id"]
        ds_ids.append(ds_id)

        r = client.get("/api/v1/finetune/datasets")
        check("GET 数据集列表", r.json()["code"] == 0 and r.json()["data"]["total"] >= 1)

        # 用合成样本导入（应全部通过质量校验）
        samples = synthesize_sql_generation(meta_config)[:5]
        r = client.post(f"/api/v1/finetune/datasets/{ds_id}/samples", json={"samples": samples})
        data = r.json()["data"]
        check("POST 导入样本", r.json()["code"] == 0 and data["imported"] == 5 and data["rejected"] == 0, r.text)

        # 导入含写操作的危险样本 → 应被拒绝
        bad = dict(samples[0])
        bad["id"] = "bad-sample-1"
        bad["output"] = "DELETE FROM fact_order;"
        r = client.post(f"/api/v1/finetune/datasets/{ds_id}/samples", json={"samples": [bad]})
        check("POST 危险样本被拒", r.json()["code"] == 0 and r.json()["data"]["rejected"] == 1, r.text)

        r = client.get(f"/api/v1/finetune/datasets/{ds_id}")
        check("GET 数据集详情含统计", r.json()["data"]["stats"]["total"] == 5 and r.json()["data"]["stats"]["by_task"]["sql_generation"] == 5, r.text)

        r = client.get(f"/api/v1/finetune/datasets/{ds_id}/samples?task=sql_generation&quality=passed")
        check("GET 样本分页过滤", r.json()["data"]["total"] == 5 and len(r.json()["data"]["items"]) == 5)

        sid = samples[0]["id"]
        r = client.patch(f"/api/v1/finetune/datasets/{ds_id}/samples/{sid}",
                         json={"meta": {"annotator": "human", "quality": "passed", "difficulty": "hard"}})
        check("PATCH 标注样本", r.json()["code"] == 0 and r.json()["data"]["meta"]["difficulty"] == "hard", r.text)

        r = client.post(f"/api/v1/finetune/datasets/{ds_id}/export",
                        json={"format": "alpaca", "task_filter": ["sql_generation"], "split": {"train": 0.8, "eval": 0.2}})
        check("POST 导出训练格式", r.json()["code"] == 0 and r.json()["data"]["sample_count"]["train"] > 0, r.text)

        # 缺失接口的资源 → 统一 40400
        r = client.get("/api/v1/finetune/datasets/not-exist")
        check("不存在数据集 → 40400", r.json()["code"] == 40400)
        r = client.post("/api/v1/finetune/jobs",
                        json={"name": "j1", "datasets": [{"dataset_id": "not-exist", "weight": 1.0}]})
        check("不存在数据集提交训练 → 40400", r.json()["code"] == 40400)

        # ============ C. trace 上报 ============
        r = client.post("/api/v1/finetune/traces", json={"traces": [{
            "trace_id": "func-trace-1", "thread_id": "t1", "query": "功能测试问题",
            "final_sql": "SELECT 1", "nodes": [{"node": "generate_sql"}],
        }]})
        check("POST trace 上报", r.json()["code"] == 0 and r.json()["data"]["accepted"] == 1, r.text)

        # ============ D. 模型管理 ============
        r = client.post("/api/v1/models/func-m/deploy", json={})
        check("POST 部署模型", r.json()["code"] == 0 and r.json()["data"]["status"] == "deployed", r.text)
        r = client.post("/api/v1/models/func-m/activate", json={"ratio": 1.0})
        check("POST 激活模型（热切换）", r.json()["code"] == 0 and r.json()["data"]["active_ratio"] == 1.0, r.text)
        r = client.get("/api/v1/models")
        items = r.json()["data"]["items"]
        check("GET 模型列表含生效标记", any(m["model_id"] == "func-m" and m["is_active"] for m in items))

        # 恢复默认 llm 配置（删除 active_llm.yaml）
        from app.conf.app_config import app_config
        r2 = asyncio.run(_deactivate())
        check("恢复默认 llm 后端", r2["status"] == "deactivated" and app_config.llm.backend == "api")

        # ============ E. 评估接口（提交即查，后台任务无 vLLM 会置 failed） ============
        r = client.post("/api/v1/finetune/evaluations",
                        json={"name": "func-eval", "model": "func-m",
                              "eval_set": {"dataset_id": ds_id}, "dimensions": ["ex"]})
        check("POST 提交评估", r.json()["code"] == 0 and r.json()["data"]["status"] in ("queued", "running"), r.text)
        eval_id = r.json()["data"]["evaluation_id"]
        time.sleep(1.0)
        r = client.get(f"/api/v1/finetune/evaluations/{eval_id}")
        check("GET 评估状态（无vLLM预期failed）", r.json()["code"] == 0 and r.json()["data"]["status"] in ("failed", "running"), r.text)

        # ============ F. 训练任务接口（只验证提交与状态机，不执行训练） ============
        r = client.post("/api/v1/finetune/jobs",
                        json={"name": "func-job", "base_model": "Qwen/Qwen2.5-Coder-14B-Instruct",
                              "datasets": [{"dataset_id": ds_id, "weight": 1.0}],
                              "hyperparams": {"epochs": 1}})
        check("POST 提交训练任务", r.json()["code"] == 0 and r.json()["data"]["status"] == "queued", r.text)
        job_id = r.json()["data"]["job_id"]
        r = client.post(f"/api/v1/finetune/jobs/{job_id}/cancel")
        check("POST 取消训练任务", r.json()["code"] == 0 and r.json()["data"]["status"] == "cancelled", r.text)
        r = client.post(f"/api/v1/finetune/jobs/{job_id}/cancel")
        check("重复取消 → 42200", r.json()["code"] == 42200)

    asyncio.run(_cleanup(ds_ids))
    print("\n".join(results))
    print(f"\n===== PASS {PASS} / FAIL {FAIL} =====")


async def _deactivate():
    from app.services.model_service import ModelService
    meta_mysql_client_manager.init_client()
    try:
        async with meta_mysql_client_manager.sesion_factory() as session:
            return await ModelService(session).deactivate_model()
    finally:
        await meta_mysql_client_manager.close()


if __name__ == "__main__":
    main()
