from langchain.chat_models import init_chat_model

from app.conf.app_config import app_config

"""
LLM 客户端工厂（docs/微调优化设计书.md 8.1 节）

根据 app_config.llm.backend 选择推理后端：
- api:       官方 API（默认，如 deepseek-chat）
- finetuned: 微调模型（vLLM 等 OpenAI 兼容接口）

节点统一通过 get_llm() 获取当前生效的模型；配置变化时自动重建，
从而支持运行期热切换（/api/v1/models/{id}/activate 后无需重启）。
"""


def _build_llm():
    cfg = app_config.llm
    if cfg.backend == "finetuned":
        # 微调模型：vLLM 提供的 OpenAI 兼容接口
        return init_chat_model(
            model=cfg.model_name,
            model_provider="openai",
            base_url=cfg.base_url,
            api_key=cfg.api_key or "EMPTY",
            temperature=0,
        )
    # 官方 API
    return init_chat_model(
        model=cfg.model_name,
        api_key=cfg.api_key,
        temperature=0,
    )


# 当前生效模型的缓存（配置签名 + 实例）
_cached_signature: tuple | None = None
_cached_llm = None


def get_llm():
    """获取当前生效的 LLM 实例，配置变化时自动重建（热切换）。"""
    global _cached_signature, _cached_llm
    cfg = app_config.llm
    signature = (cfg.backend, cfg.model_name, cfg.base_url, cfg.api_key)
    if _cached_llm is None or _cached_signature != signature:
        _cached_llm = _build_llm()
        _cached_signature = signature
    return _cached_llm


# 兼容旧引用：模块级 llm 在首次 get_llm() 后可用（新代码请使用 get_llm()）
def __getattr__(name):
    if name == "llm":
        return get_llm()
    raise AttributeError(name)


if __name__ == '__main__':
    result = get_llm().invoke("你是谁？")
    print(result.content)
