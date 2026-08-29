"""统一响应结构（API 文档 1.2 节）。"""
from __future__ import annotations

from typing import Any, Optional

from app.core.context import get_request_id


def ok(data: Any = None, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data, "trace_id": get_request_id()}


def error(code: int, message: str) -> dict:
    return {"code": code, "message": message, "data": None, "trace_id": get_request_id()}
