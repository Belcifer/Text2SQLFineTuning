"""API 冒烟检查（需本地 MySQL，配置见 conf/app_config.yaml）。

验证：路由注册齐全、统一响应结构、业务错误码、建表后的读写链路。
自清理：运行结束删除冒烟数据集，不留脏数据。
"""
import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import delete

import main as app_module
from app.clients.mysql_client_manager import meta_mysql_client_manager
from app.models.mysql.finetune_dataset import FinetuneDataset
from app.models.mysql.model_version import ModelVersion

EXPECTED_ROUTES = {
    "POST /api/v1/query",
    "POST /api/v1/query/sync",
    "POST /api/v1/query/followup",
    "POST /api/v1/knowledge/build",
    "GET /api/v1/knowledge/build/{build_id}",
    "POST /api/v1/finetune/datasets",
    "GET /api/v1/finetune/datasets",
    "POST /api/v1/finetune/datasets/{dataset_id}/samples",
    "POST /api/v1/finetune/datasets/{dataset_id}/export",
    "POST /api/v1/finetune/traces",
    "POST /api/v1/finetune/jobs",
    "GET /api/v1/finetune/jobs/{job_id}",
    "POST /api/v1/finetune/evaluations",
    "GET /api/v1/finetune/evaluations/{evaluation_id}",
    "GET /api/v1/models",
    "POST /api/v1/models/{model_id}/deploy",
    "POST /api/v1/models/{model_id}/activate",
}


async def _cleanup(ds_id: str):
    meta_mysql_client_manager.init_client()
    try:
        async with meta_mysql_client_manager.sesion_factory() as session:
            await session.execute(delete(FinetuneDataset).where(FinetuneDataset.id == ds_id))
            await session.execute(delete(ModelVersion).where(ModelVersion.id == "smoke-m"))
            await session.commit()
    finally:
        await meta_mysql_client_manager.close()


def main():
    ds_id = None
    with TestClient(app_module.app, raise_server_exceptions=False) as client:
        assert client.get("/health").json() == {"status": "ok"}, "health 失败"
        routes = {f"{sorted(r.methods)[0]} {r.path}" for r in app_module.app.routes if hasattr(r, "methods")}
        missing = EXPECTED_ROUTES - routes
        assert not missing, f"缺少路由: {missing}"

        r = client.post("/api/v1/finetune/datasets",
                        json={"name": "smoke-ds", "description": "t", "dialect": "mysql"})
        assert r.status_code == 200 and r.json()["code"] == 0, f"创建数据集失败: {r.text}"
        ds_id = r.json()["data"]["dataset_id"]

        r = client.get("/api/v1/knowledge/build/not-exist")
        assert r.json()["code"] == 40400, f"统一错误结构异常: {r.text}"

        r = client.post("/api/v1/models/smoke-m/deploy", json={})
        assert r.json()["data"]["status"] == "deployed", f"部署失败: {r.text}"

    if ds_id:
        asyncio.run(_cleanup(ds_id))
    print("api smoke OK")


if __name__ == "__main__":
    main()
