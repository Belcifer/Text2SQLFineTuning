"""初始化 meta 库表结构（幂等，create_all 仅创建缺失的表）。

覆盖：主链路表 + 微调子系统表（设计书附录目录变更清单）。
用法：PYTHONPATH=. ./.venv/Scripts/python.exe scripts/create_tables.py
"""
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from app.conf.app_config import app_config
from app.models.mysql.base import Base

# 导入全部模型以注册到 Base.metadata（无业务作用，仅副作用）
import app.models.mysql.column_info_mysql  # noqa: F401
import app.models.mysql.column_metric_mysql  # noqa: F401
import app.models.mysql.finetune_dataset  # noqa: F401
import app.models.mysql.finetune_evaluation  # noqa: F401
import app.models.mysql.finetune_job  # noqa: F401
import app.models.mysql.finetune_sample  # noqa: F401
import app.models.mysql.metric_info_mysql  # noqa: F401
import app.models.mysql.model_version  # noqa: F401
import app.models.mysql.table_info_mysql  # noqa: F401
import app.models.mysql.trace_record  # noqa: F401


async def main():
    cfg = app_config.db_meta
    url = f"mysql+asyncmy://{cfg.user}:{cfg.password}@{cfg.host}:{cfg.port}/{cfg.database}?charset=utf8mb4"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        tables = sorted(Base.metadata.tables.keys())
        print(f"建表完成（幂等），共 {len(tables)} 张：")
        for name in tables:
            print(" -", name)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
