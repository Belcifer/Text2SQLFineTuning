"""统一样本 schema 与质量校验（设计书 5.2/5.4 节）。

样本是 JSON 对象，任务类型由 task 字段区分，六类子任务与 7 类 LLM 调用点一一对应
（设计书 4.7 节）：
- sql_generation          → generate_sql 节点
- sql_correction          → correct_sql 节点
- schema_linking          → recall_column / filter_table 节点
- value_standardization   → recall_value 节点
- metric_resolution       → recall_metric / filter_metric 节点
- clarification           → generate_sql 前置判定（设计书 4.4 节）
"""
from __future__ import annotations

import re

# ==================== 枚举常量 ====================

TASKS = (
    "sql_generation",
    "sql_correction",
    "schema_linking",
    "value_standardization",
    "metric_resolution",
    "clarification",
)

SOURCES = ("synthetic", "trace", "human", "open")

QUALITIES = ("passed", "rejected")

# 危险写操作关键字（SQL 只读校验，设计书 4.2.6 节）
_WRITE_KEYWORDS = (
    r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b", r"\bCREATE\b",
    r"\bALTER\b", r"\bTRUNCATE\b", r"\bGRANT\b", r"\bREVOKE\b", r"\bREPLACE\b",
    r"\bMERGE\b", r"\bLOAD\b", r"\bCALL\b", r"\bRENAME\b", r"\bLOCK\b",
)
_WRITE_PATTERN = re.compile("|".join(_WRITE_KEYWORDS), re.IGNORECASE)

# SQL 子任务（output 必须是纯 SQL）
SQL_TASKS = ("sql_generation", "sql_correction")


def is_readonly_sql(sql: str) -> bool:
    """宽松校验 SQL 是否只读：不含写操作关键字即为通过。

    注意：这是样本质量门槛（设计书 5.4 四重校验之一），
    线上执行仍依赖数据库只读账号兜底。
    """
    return not _WRITE_PATTERN.search(sql or "")


def validate_sample(sample: dict) -> list[str]:
    """校验一条样本，返回错误列表（为空表示通过，quality 置为 passed）。"""
    errors: list[str] = []

    task = sample.get("task")
    if task not in TASKS:
        errors.append(f"task 非法: {task!r}，允许值 {TASKS}")

    source = sample.get("source")
    if source not in SOURCES:
        errors.append(f"source 非法: {source!r}，允许值 {SOURCES}")

    if not sample.get("input"):
        errors.append("input 不能为空")

    if not sample.get("output"):
        errors.append("output 不能为空")

    context = sample.get("context") or {}
    if "table_infos" not in context:
        errors.append("context.table_infos 缺失")

    # SQL 类任务的输出必须是只读 SQL 文本
    if task in SQL_TASKS and not is_readonly_sql(sample.get("output", "")):
        errors.append("output 包含写操作关键字，违反只读约束")

    # meta.quality 校验
    meta = sample.get("meta") or {}
    if "quality" in meta and meta["quality"] not in QUALITIES:
        errors.append(f"meta.quality 非法: {meta['quality']!r}")

    return errors


def build_instruction(task: str, context: dict) -> str:
    """按任务类型生成统一指令（与 prompt/*.prompt 风格一致，训练/推理共用）。"""
    table_count = len(context.get("table_infos") or [])
    metric_count = len(context.get("metric_infos") or [])
    if task == "sql_generation":
        return ("将用户问题转换为只读 SQL 语句。仅允许使用上下文数据表信息中真实存在的表与字段名称，"
                f"禁止编造。当前提供 {table_count} 张表、{metric_count} 个指标定义。")
    if task == "sql_correction":
        return ("根据上下文与错误信息，对已有 SQL 进行最小必要修正，保持业务语义不变，"
                "输出只读且语法正确的 SQL 语句。")
    if task == "schema_linking":
        return ("从候选表及字段信息中，选择回答用户问题所必需的表和字段，"
                "仅允许从候选中选择，输出 JSON 对象 {表名: [字段名, ...]}。")
    if task == "value_standardization":
        return ("将用户问题中出现的别名、简称、口语表达映射为字段的标准值；"
                "无法确定时标记为需澄清。输出 JSON 对象。")
    if task == "metric_resolution":
        return ("从候选指标中选择用户问题实际用到的指标，并给出指标口径（聚合函数/分子/分母/去重/时间口径）。"
                "输出 JSON 对象。")
    if task == "clarification":
        return ("判断用户问题是否缺少时间范围、统计粒度、指标口径或筛选条件；"
                "若缺失，输出具体可回答的澄清问题；否则输出可直接执行的 SQL。输出 JSON 对象。")
    return ""
