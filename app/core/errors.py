"""统一业务异常与错误码（API 文档 1.2/1.3 节）。"""
from __future__ import annotations


# ==================== 错误码 ====================
CODE_OK = 0
CODE_PARAM = 40000          # 参数校验失败
CODE_AUTH = 40100           # 认证失败 / 无权限
CODE_NOT_FOUND = 40400      # 资源不存在
CODE_CONFLICT = 40900       # 状态冲突（重复提交、状态机不允许）
CODE_VALIDATION = 42200     # 业务校验失败（如样本质量校验不通过）
CODE_RATE_LIMIT = 42900     # 频率限制
CODE_INTERNAL = 50000       # 系统内部错误


class BizError(Exception):
    """业务异常：携带错误码，由全局异常处理器转为统一响应结构。"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


def param_error(message: str) -> BizError:
    return BizError(CODE_PARAM, message)


def not_found(resource: str = "资源") -> BizError:
    return BizError(CODE_NOT_FOUND, f"{resource}不存在")


def conflict(message: str) -> BizError:
    return BizError(CODE_CONFLICT, message)


def validation_error(message: str) -> BizError:
    return BizError(CODE_VALIDATION, message)


class ClarifyRequired(Exception):
    """模型判定信息不充分，需要向用户澄清（设计书 4.4 节）。

    由 generate_sql 节点抛出，QueryService 捕获后转为 SSE 的 clarify 事件。
    """

    def __init__(self, questions: list[str]):
        super().__init__("; ".join(questions))
        self.questions = questions
