from pydantic import BaseModel, Field


class DeploySchema(BaseModel):
    """部署模型请求体（API 文档 7.2 节）。"""

    gpu_count: int = Field(1, description="GPU 数量")
    max_model_len: int = Field(4096, description="最大序列长度")


class ActivateSchema(BaseModel):
    """切换生效模型请求体（API 文档 7.3 节）。"""

    ratio: float = Field(1.0, description="流量比例 0~1，1 为全量切换")
