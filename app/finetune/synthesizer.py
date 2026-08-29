"""训练数据合成（设计书 5.3/5.4 节，数据来源 A：知识库模板合成）。

以 conf/meta_config.yaml 为事实底座，确定性生成六类子任务样本：
- 不依赖外部 LLM（v1 模板版），保证可运行、可回归；
- 产出样本统一走 sample_schema.validate_sample 校验后入库。
"""
from __future__ import annotations

import uuid

from app.conf.meta_config import MetaConfig, MetricConfig, TableConfig

_DATE_INFO = {"date": "2025-01-01", "weekday": "Wednesday", "quarter": "Q1"}
_DB_INFO = {"version": "8.0.0", "dialect": "mysql"}

# 维度字段 → 问题中的口语标签（用于问题模板）
_DIM_LABELS = {
    "region_name": "地区", "province": "省份", "country": "国家",
    "customer_name": "客户", "gender": "性别", "member_level": "会员等级",
    "product_name": "商品", "category": "品类", "brand": "品牌",
    "year": "年份", "quarter": "季度", "month": "月份", "day": "日期",
}


def _new_id() -> str:
    return uuid.uuid4().hex


def _to_table_info(table: TableConfig) -> dict:
    """meta_config 的表 → 设计书 5.2 的 table_infos 结构。"""
    columns = [
        {
            "name": col.name, "type": "varchar(64)", "role": col.role,
            "description": col.description, "alias": list(col.alias),
            "examples": [],
        }
        for col in table.columns
    ]
    primary_keys = [c["name"] for c in columns if c["role"] == "primary_key"]
    foreign_keys = {
        c["name"]: f"{table.name}.{c['name']}"
        for c in columns if c["role"] == "foreign_key"
    }
    return {
        "table": table.name, "role": table.role, "description": table.description,
        "columns": columns, "primary_keys": primary_keys, "foreign_keys": foreign_keys,
    }


def _to_metric_info(metric: MetricConfig) -> dict:
    return {
        "name": metric.name, "description": metric.description,
        "relevant_columns": list(metric.relevant_columns), "alias": list(metric.alias),
    }


def _context(table_infos: list[dict], metric_infos: list[dict] | None = None,
             value_infos: list[dict] | None = None, extra: dict | None = None) -> dict:
    context = {
        "table_infos": table_infos,
        "metric_infos": metric_infos or [],
        "value_infos": value_infos or [],
        "date_info": _DATE_INFO,
        "db_info": _DB_INFO,
    }
    if extra:
        context.update(extra)
    return context


def _fact_and_dims(tables: list[TableConfig]) -> tuple[TableConfig, list[TableConfig]]:
    fact = next((t for t in tables if t.role == "fact"), tables[0])
    dims = [t for t in tables if t.role == "dim"]
    return fact, dims


def _metric_agg(metric: MetricConfig, fact: TableConfig) -> str:
    """按指标定义生成聚合表达式（设计书 4.2.3；AOV 类取 金额/去重订单数 口径约定）。"""
    measures = [c for c in fact.columns if c.role == "measure"]
    relevant = [c for c in measures if f"{fact.name}.{c.name}" in metric.relevant_columns]
    if len(relevant) >= 2:
        return f"SUM(o.{relevant[0].name}) / COUNT(DISTINCT o.{measures[0].name})" if measures else f"SUM(o.{relevant[0].name})"
    col = relevant[0].name if relevant else measures[0].name
    return f"SUM(o.{col})"


def _metric_alias(metric: MetricConfig) -> str:
    return metric.alias[0] if metric.alias else metric.name


def _time_cond(query_hint: str, date_dim: TableConfig) -> tuple[str, str]:
    """根据问题时间提示生成 WHERE 条件；返回 (条件SQL, 问题片段)。"""
    if "2025" in query_hint:
        return "d.year = 2025", "2025年"
    if "去年" in query_hint:
        return "d.year = YEAR(CURDATE()) - 1", "去年"
    if "3月" in query_hint:
        return "d.month = 3", "3月"
    return "", ""


def synthesize_sql_generation(config: MetaConfig) -> list[dict]:
    """sql_generation：指标 × 维度 × 时间 组合（设计书 4.2.5/4.2.6）。"""
    samples: list[dict] = []
    fact, dims = _fact_and_dims(config.tables)
    table_infos = [_to_table_info(t) for t in config.tables]
    metric_infos = [_to_metric_info(m) for m in config.metrics]
    date_dim = next((t for t in dims if t.name == "dim_date"), None)

    for metric in config.metrics:
        agg = _metric_agg(metric, fact)
        m_alias = _metric_alias(metric)
        # 纯指标样本（无维度，可测 SQL 的基础形态）
        base_question = f"{m_alias}是多少"
        sql = f"SELECT {agg} AS {metric.name} FROM {fact.name} o"
        samples.append(_sql_sample(base_question, sql, table_infos, metric_infos))
        # 指标 × 维度 × 时间
        for dim in dims:
            if dim.name == "dim_date":
                continue
            for col in dim.columns:
                if col.role != "dimension" or col.name not in _DIM_LABELS:
                    continue
                label = _DIM_LABELS[col.name]
                for hint in ("", "2025年", "去年"):
                    time_cond, hint_text = _time_cond(hint, date_dim) if date_dim else ("", "")
                    question = f"{hint_text}各{label}{m_alias}"
                    sql = (f"SELECT {col.name}, {agg} AS {metric.name} FROM {fact.name} o "
                           f"JOIN {dim.name} d ON o.{_fk_to(dim, fact)} = d.{_pk_of(dim)}")
                    if time_cond:
                        sql += f" JOIN {date_dim.name} d2 ON o.date_id = d2.date_id WHERE {time_cond}"
                    sql += f" GROUP BY {col.name}"
                    samples.append(_sql_sample(question, sql, table_infos, metric_infos))
    return samples


def _pk_of(table: TableConfig) -> str:
    for col in table.columns:
        if col.role == "primary_key":
            return col.name
    return f"{table.name}_id"


def _fk_to(dim: TableConfig, fact: TableConfig) -> str:
    """fact 表中指向 dim 的外键列名（按命名约定 dim_xxx → xxx_id）。"""
    dim_name = dim.name.removeprefix("dim_")
    for col in fact.columns:
        if col.role == "foreign_key" and dim_name in col.name:
            return col.name
    return f"{dim_name}_id"


def _sql_sample(question: str, sql: str, table_infos: list[dict], metric_infos: list[dict]) -> dict:
    return {
        "id": _new_id(),
        "task": "sql_generation",
        "source": "synthetic",
        "ability_tags": ["4.2.5", "4.2.6"],
        "database": "mysql",
        "dialect": "mysql 8.0",
        "context": _context(table_infos, metric_infos),
        "instruction": "将用户问题转换为只读 SQL 语句。仅允许使用上下文数据表信息中真实存在的表与字段名称。",
        "input": question,
        "output": sql,
        "meta": {"difficulty": "medium", "has_join": True, "has_clarify": False, "annotator": "auto"},
    }


def synthesize_schema_linking(config: MetaConfig, sql_samples: list[dict] | None = None) -> list[dict]:
    """schema_linking：从 sql_generation 样本推导用到的表与字段（设计书 4.2.1）。"""
    samples: list[dict] = []
    table_infos = [_to_table_info(t) for t in config.tables]
    for sql_sample in (sql_samples or synthesize_sql_generation(config))[:60]:
        question = sql_sample["input"]
        sql = sql_sample["output"]
        # 从 SQL 中解析用到的表与列（简单规则）
        used = {}
        for table_info in table_infos:
            table = table_info["table"]
            if table in sql:
                used_cols = [c["name"] for c in table_info["columns"] if f".{c['name']}" in sql or c["name"] in sql]
                if used_cols:
                    used[table] = used_cols
        samples.append({
            "id": _new_id(),
            "task": "schema_linking",
            "source": "synthetic",
            "ability_tags": ["4.2.1"],
            "database": "mysql",
            "dialect": "mysql 8.0",
            "context": _context(table_infos, []),
            "instruction": "从候选表及字段信息中，选择回答用户问题所必需的表和字段。输出 JSON 对象。",
            "input": question,
            "output": _json_output(used),
            "meta": {"difficulty": "medium", "has_join": True, "annotator": "auto"},
        })
    return samples


def _json_output(obj: dict) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


def synthesize_value_standardization(config: MetaConfig) -> list[dict]:
    """value_standardization：字段别名 → 标准名/标准值 映射（设计书 4.2.2）。"""
    samples: list[dict] = []
    table_infos = [_to_table_info(t) for t in config.tables]
    for table in config.tables:
        for col in table.columns:
            if not col.alias:
                continue
            value = col.name
            aliases = list(col.alias)
            question = f"统计{aliases[0]}的销售额"
            output = {
                "mapping": {alias: value for alias in aliases},
                "standard_values": [value],
                "need_clarify": [],
            }
            samples.append({
                "id": _new_id(),
                "task": "value_standardization",
                "source": "synthetic",
                "ability_tags": ["4.2.2"],
                "database": "mysql",
                "dialect": "mysql 8.0",
                "context": _context(
                    table_infos, [],
                    value_infos=[{"column_id": f"{table.name}.{col.name}", "value": value, "aliases": aliases}],
                ),
                "instruction": "将用户问题中的别名、简称、口语表达映射为字段的标准值；无法确定时标记为需澄清。输出 JSON 对象。",
                "input": question,
                "output": _json_output(output),
                "meta": {"difficulty": "easy", "has_clarify": False, "annotator": "auto"},
            })
    return samples


def synthesize_metric_resolution(config: MetaConfig) -> list[dict]:
    """metric_resolution：指标别名 → 指标 + 口径（设计书 4.2.3）。"""
    samples: list[dict] = []
    fact, _ = _fact_and_dims(config.tables)
    table_infos = [_to_table_info(t) for t in config.tables]
    metric_infos = [_to_metric_info(m) for m in config.metrics]
    for metric in config.metrics:
        alias = _metric_alias(metric)
        output = {
            "selected_metrics": [metric.name],
            "caliber": {metric.name: {"formula": _metric_agg(metric, fact), "time_grain": "自然日"}},
        }
        samples.append({
            "id": _new_id(),
            "task": "metric_resolution",
            "source": "synthetic",
            "ability_tags": ["4.2.3"],
            "database": "mysql",
            "dialect": "mysql 8.0",
            "context": _context(table_infos, metric_infos),
            "instruction": "从候选指标中选择用户问题实际用到的指标，并给出指标口径。输出 JSON 对象。",
            "input": f"{alias}是多少",
            "output": _json_output(output),
            "meta": {"difficulty": "easy", "has_clarify": False, "annotator": "auto"},
        })
    return samples


def synthesize_clarification(config: MetaConfig) -> list[dict]:
    """clarification：信息不完整样本 → 澄清问题（设计书 4.2.4/4.4 节）。"""
    samples: list[dict] = []
    fact, _ = _fact_and_dims(config.tables)
    table_infos = [_to_table_info(t) for t in config.tables]
    for metric in config.metrics:
        alias = _metric_alias(metric)
        output = {
            "need_clarify": True,
            "questions": [
                f"您关心的指标是{alias}还是其他指标？",
                "请明确统计的时间范围（如本月、近三个月、2025年）。",
            ],
        }
        samples.append({
            "id": _new_id(),
            "task": "clarification",
            "source": "synthetic",
            "ability_tags": ["4.2.4"],
            "database": "mysql",
            "dialect": "mysql 8.0",
            "context": _context(table_infos, [_to_metric_info(metric)]),
            "instruction": "判断用户问题是否缺少时间范围、统计粒度、指标口径或筛选条件；若缺失，输出具体可回答的澄清问题；否则输出可直接执行的 SQL。输出 JSON 对象。",
            "input": f"看一下{fact.name}的销售情况",
            "output": _json_output(output),
            "meta": {"difficulty": "hard", "has_clarify": True, "annotator": "auto"},
        })
    return samples


def synthesize_sql_correction(config: MetaConfig) -> list[dict]:
    """sql_correction：错误 SQL + 错误信息 → 正确 SQL（设计书 4.2.6）。"""
    samples: list[dict] = []
    fact, dims = _fact_and_dims(config.tables)
    table_infos = [_to_table_info(t) for t in config.tables]
    metric_infos = [_to_metric_info(m) for m in config.metrics]
    date_dim = next((t for t in dims if t.name == "dim_date"), None)
    for metric in config.metrics:
        agg = _metric_agg(metric, fact)
        alias = _metric_alias(metric)
        question = f"2025年各地区{alias}"
        correct_sql = (
            f"SELECT r.region_name, {agg} AS {metric.name} FROM {fact.name} o "
            f"JOIN dim_region r ON o.region_id = r.region_id "
            f"JOIN {date_dim.name} d ON o.date_id = d.date_id WHERE d.year = 2025 GROUP BY r.region_name"
        )
        wrong_sql = (
            f"SELECT region_name, {agg} FROM {fact.name} WHERE year = 2025 GROUP BY region_name"
        )
        samples.append({
            "id": _new_id(),
            "task": "sql_correction",
            "source": "synthetic",
            "ability_tags": ["4.2.6"],
            "database": "mysql",
            "dialect": "mysql 8.0",
            "context": _context(table_infos, metric_infos, extra={
                "sql": wrong_sql,
                "error": "Unknown column 'year' in 'where clause'",
            }),
            "instruction": "根据上下文与错误信息，对已有 SQL 进行最小必要修正，保持业务语义不变，输出只读且语法正确的 SQL 语句。",
            "input": question,
            "output": correct_sql,
            "meta": {"difficulty": "hard", "has_join": True, "annotator": "auto"},
        })
    return samples


def synthesize_all(config: MetaConfig) -> list[dict]:
    """合成六类样本并返回（调用方负责去重与入库）。"""
    sql_samples = synthesize_sql_generation(config)
    samples: list[dict] = []
    samples += sql_samples
    samples += synthesize_schema_linking(config, sql_samples)
    samples += synthesize_value_standardization(config)
    samples += synthesize_metric_resolution(config)
    samples += synthesize_clarification(config)
    samples += synthesize_sql_correction(config)
    return samples


if __name__ == "__main__":
    from app.conf.meta_config import meta_config

    all_samples = synthesize_all(meta_config)
    print(f"合成样本总数: {len(all_samples)}")
    from collections import Counter
    print(Counter(s["task"] for s in all_samples))
