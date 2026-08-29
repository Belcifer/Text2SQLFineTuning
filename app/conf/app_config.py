"""
解析、读取app_config.yaml的模块
"""
from dataclasses import dataclass
from pathlib import Path

from omegaconf import OmegaConf


# ==================== 日志配置模型 ====================
@dataclass
class File:
    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class Console:
    enable: bool
    level: str

@dataclass
class LoggingConfig:
    file: File
    console: Console


# ==================== database配置模型 ====================

@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str

# ==================== Qdrant 配置模型 ====================

@dataclass
class QdrantConfig:
    host: str
    port: int
    embedding_size: int


# ==================== Embedding 配置模型 ====================

@dataclass
class EmbeddingConfig:
    host: str
    port: int
    model: str


# ==================== ES 配置模型 ====================

@dataclass
class ESConfig:
    host: str
    port: int
    index_name: str


# ==================== LLM 配置模型 ====================

@dataclass
class LLMConfig:
    backend: str  # 推理后端: api(官方API) | finetuned(vLLM OpenAI兼容)
    model_name: str
    api_key: str
    base_url: str  # backend=finetuned 时必填


# ==================== 微调子系统配置模型 ====================

@dataclass
class TraceConfig:
    enable: bool  # 是否采集线上trace（设计书 5.6）


@dataclass
class FinetuneConfig:
    trace: TraceConfig
    sample_dir: str  # 样本与导出文件的存储目录
    base_model: str  # 微调基座模型
    default_hyperparams: dict  # 训练默认超参（设计书 6.2）


# ==================== 应用总配置模型 ====================

@dataclass
class AppConfig:
    logging: LoggingConfig
    db_meta: DBConfig
    db_dw: DBConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig
    finetune: FinetuneConfig

# 配置文件的路径
_yaml_path = Path(__file__).parents[2] / "conf" / "app_config.yaml"
# 加载配置文件
_yaml_data = OmegaConf.load(_yaml_path)

# 若存在 conf/active_llm.yaml（由模型激活接口写入），用其覆盖 llm 段（设计书 8.1 热切换）
_active_llm_path = Path(__file__).parents[2] / "conf" / "active_llm.yaml"
if _active_llm_path.exists():
    _active_llm_data = OmegaConf.load(_active_llm_path)
    _yaml_data = OmegaConf.merge(_yaml_data, OmegaConf.create({"llm": _active_llm_data}))

# 转换为指定类型的对象
app_config: AppConfig = OmegaConf.to_object(OmegaConf.merge(AppConfig, _yaml_data))

if __name__ == '__main__':
    print(app_config)
    print(app_config.logging.file.level)