from pydantic import BaseModel, Field


class QuerySchema(BaseModel):
    """发起问数请求体（API 文档 2.1 节）。"""

    query: str = Field(..., description="用户自然语言问题")
    thread_id: str = Field("", description="会话ID，用于跨轮澄清上下文与记忆")
    dialect: str = Field("mysql", description="目标方言")
    db: str = Field("dw", description="目标业务库")
    max_retry: int = Field(2, description="SQL校验/纠错最大重试次数")


class FollowupSchema(BaseModel):
    """澄清追问请求体（API 文档 2.3 节）。"""

    thread_id: str = Field("", description="会话ID（复用原会话）")
    query: str = Field(..., description="用户补充的信息")
