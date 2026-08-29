"""模型服务（API 文档 7 节，设计书 8.1 节）。

- 模型版本记录在 meta 库 model_version 表；
- 激活接口：更新 app_config.llm（内存热切换，get_llm() 签名缓存自动重建）
  并持久化 conf/active_llm.yaml（重启后仍生效，不破坏 app_config.yaml 原注释与默认值）。
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from omegaconf import OmegaConf
from sqlalchemy.ext.asyncio import AsyncSession

from app.conf.app_config import app_config
from app.core.errors import not_found, validation_error
from app.finetune.sample_repo import ModelRepo

# 激活后的 llm 配置持久化文件（位于项目 conf/ 目录）
_ACTIVE_LLM_PATH = Path(__file__).parents[2] / "conf" / "active_llm.yaml"

# 生效流量比例（内存态，单进程 v1）
_active_ratio: dict[str, float] = {}


class ModelService:
    def __init__(self, meta_session: AsyncSession):
        self.session = meta_session
        self.repo = ModelRepo(meta_session)

    async def list_models(self) -> dict:
        models = await self.repo.list_models()
        return {
            "items": [
                {
                    "model_id": m.id, "name": m.name, "type": m.type,
                    "status": m.status, "endpoint": m.endpoint,
                    "is_active": m.is_active,
                    "active_ratio": _active_ratio.get(m.id, 1.0 if m.is_active else 0.0),
                }
                for m in models
            ]
        }

    async def deploy_model(self, model_id: str, gpu_count: int = 1, max_model_len: int = 4096) -> dict:
        model = await self.repo.get_model(model_id)
        if model is None:
            # 未登记时自动登记（finetuned 类型）
            model = await self.repo.create_model(model_id, model_id, "finetuned")
        model.status = "deployed"
        model.endpoint = "http://localhost:8000/v1"
        # commit 前收集返回值（避免 commit 后 ORM 属性过期触发同步 IO）
        result = {"model_id": model.id, "status": model.status, "endpoint": model.endpoint}
        await self.session.commit()
        # v1：vLLM 实际拉起由外部运维完成，此处记录目标 endpoint 与部署状态
        return result

    async def activate_model(self, model_id: str, ratio: float = 1.0) -> dict:
        model = await self.repo.get_model(model_id)
        if model is None:
            raise not_found("模型")
        if model.status != "deployed":
            raise validation_error(f"模型状态 {model.status} 不可激活，请先部署")

        # commit 前收集（避免 commit 后 ORM 属性过期触发同步 IO）
        model_type = model.type
        model_name = model.name
        model_endpoint = model.endpoint or "http://localhost:8000/v1"

        # 1. DB：切换 is_active
        await self.repo.clear_active()
        model.is_active = True
        await self.session.commit()

        # 2. 内存热切换：更新 app_config.llm（get_llm() 检测签名变化自动重建）
        app_config.llm.backend = "finetuned" if model_type == "finetuned" else "api"
        app_config.llm.model_name = model_name
        app_config.llm.base_url = model_endpoint
        if model_type == "api":
            app_config.llm.base_url = ""

        # 3. 持久化：写入 conf/active_llm.yaml（重启后仍生效）
        _ACTIVE_LLM_PATH.write_text(
            OmegaConf.to_yaml(OmegaConf.create({
                "backend": app_config.llm.backend,
                "model_name": app_config.llm.model_name,
                "api_key": app_config.llm.api_key,
                "base_url": app_config.llm.base_url,
            })),
            encoding="utf-8",
        )

        previous = next((m for m in await self.repo.list_models() if m.id != model_id and m.is_active), None)
        _active_ratio[model_id] = ratio
        return {
            "model_id": model.id,
            "active_ratio": ratio,
            "previous_active": previous.id if previous else None,
        }

    async def deactivate_model(self, model_id: Optional[str] = None) -> dict:
        """恢复 app_config.yaml 中的默认 llm 配置（删除 active_llm.yaml 并改回内存值）。"""
        if _ACTIVE_LLM_PATH.exists():
            _ACTIVE_LLM_PATH.unlink()
        # 读取默认 yaml 的 llm 段，直接改回内存配置（get_llm() 检测签名变化自动重建）
        default_data = OmegaConf.load(Path(__file__).parents[2] / "conf" / "app_config.yaml")
        app_config.llm.backend = default_data.llm.backend
        app_config.llm.model_name = default_data.llm.model_name
        app_config.llm.api_key = default_data.llm.api_key
        app_config.llm.base_url = default_data.llm.base_url
        return {"status": "deactivated"}
