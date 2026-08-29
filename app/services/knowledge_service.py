"""知识库构建服务（API 文档 3 节）。

将 MetaKnowledgeService.build 包装为后台异步任务，支持按 build_id 轮询状态。
状态保存在内存（单进程 v1）；多实例部署时建议替换为 Redis/DB。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Awaitable, Callable, Optional

from app.core.log import logger


class KnowledgeService:
    def __init__(self):
        self._builds: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def start_build(self, runner: Callable[[], Awaitable[dict]],
                          scope: str = "all", reset: bool = True) -> dict:
        """提交构建任务，立即返回 build 状态骨架。

        runner: 由依赖层组装的可执行构建函数，返回统计 dict：
                {"tables": n, "columns": n, "metrics": n, "values_indexed": n}
        """
        build_id = uuid.uuid4().hex
        record = {
            "build_id": build_id,
            "status": "running",
            "progress": 0.0,
            "detail": {"scope": scope, "reset": reset, "error": None},
        }
        async with self._lock:
            self._builds[build_id] = record
        asyncio.create_task(self._run(build_id, runner, scope, reset))
        return record

    def get_status(self, build_id: str) -> Optional[dict]:
        return self._builds.get(build_id)

    async def _run(self, build_id: str, runner, scope: str, reset: bool):
        record = self._builds[build_id]
        try:
            detail = await runner()
            record.update({"status": "success", "progress": 1.0, "detail": detail})
            logger.info(f"知识库构建成功: {build_id}")
        except Exception as e:
            logger.error(f"知识库构建失败: {build_id} {str(e)}")
            record.update({"status": "failed", "detail": {"error": str(e)}})


# 全局单例（构建状态跨请求共享）
knowledge_service = KnowledgeService()
