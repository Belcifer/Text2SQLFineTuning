from pydantic import BaseModel, Field


class BuildSchema(BaseModel):
    """触发知识库构建请求体（API 文档 3.1 节）。"""

    scope: str = Field("all", description="all | tables | metrics | values")
    reset: bool = Field(True, description="是否先清空 Qdrant/ES 集合与索引重建")
