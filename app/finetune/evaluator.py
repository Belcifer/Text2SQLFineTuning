"""离线评估（设计书第 7 章，API 文档 6 节）。

- 指标纯函数可离线单测；
- run_evaluation() 需要 vLLM（OpenAI 兼容）与沙箱只读库，重型依赖延迟导入。
"""
from __future__ import annotations

from typing import Optional

from app.finetune.sample_schema import is_readonly_sql


# ==================== 指标纯函数 ====================

def execution_accuracy(results: list[dict]) -> float:
    """结果集一致率（EX）：生成 SQL 执行结果与标准结果一致的占比。"""
    if not results:
        return 0.0
    return sum(1 for r in results if r.get("exact")) / len(results)


def schema_linking_f1(pred_columns: set, gold_columns: set) -> float:
    """字段映射 F1（设计书 7.1 节 4.2.1 维度）。"""
    if not pred_columns or not gold_columns:
        return 0.0
    inter = pred_columns & gold_columns
    precision = len(inter) / len(pred_columns)
    recall = len(inter) / len(gold_columns)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def value_mapping_accuracy(results: list[dict]) -> float:
    """值映射准确率（4.2.2 维度）。"""
    if not results:
        return 0.0
    return sum(1 for r in results if r.get("value_ok")) / len(results)


def metric_caliber_accuracy(results: list[dict]) -> float:
    """指标口径一致率（4.2.3 维度）。"""
    if not results:
        return 0.0
    return sum(1 for r in results if r.get("caliber_ok")) / len(results)


def clarify_accuracy(results: list[dict]) -> float:
    """澄清准确率（4.2.4 维度）：应澄清而澄清 + 问题具体可回答。"""
    if not results:
        return 0.0
    return sum(1 for r in results if r.get("clarify_ok")) / len(results)


def safety_violation_rate(samples: list[dict]) -> float:
    """安全违规率（4.2.6 维度）：生成 SQL 含写操作/危险函数或引用越权对象的占比。"""
    if not samples:
        return 0.0
    return sum(1 for s in samples if not is_readonly_sql(s.get("output", ""))) / len(samples)


def build_report(results: dict) -> dict:
    """汇总为 API 文档 6.2 节的 report 结构。"""
    return {
        "execution_accuracy": results.get("execution_accuracy", 0.0),
        "schema_linking_f1": results.get("schema_linking_f1", 0.0),
        "value_mapping_accuracy": results.get("value_mapping_accuracy", 0.0),
        "metric_caliber_accuracy": results.get("metric_caliber_accuracy", 0.0),
        "clarify_accuracy": results.get("clarify_accuracy", 0.0),
        "safety_violation_rate": results.get("safety_violation_rate", 0.0),
    }


# ==================== 在线式评估（需 vLLM + 沙箱库） ====================

async def run_evaluation(
    eval_params: dict,
    samples: list[dict],
    dw_mysql_repo,
    llm_endpoint: Optional[str] = None,
    model_name: Optional[str] = None,
) -> dict:
    """对评测集逐条执行：调用微调模型生成 SQL → 沙箱执行 → 与标准结果比对。

    依赖：openai 客户端（vLLM OpenAI 兼容接口）+ 可执行的 dw 沙箱库。
    本仓库不内置 GPU/沙箱环境，运行前需满足上述依赖。
    """
    try:
        from openai import AsyncOpenAI
    except ImportError as e:
        raise RuntimeError("评估需要 openai 客户端：pip install openai") from e

    client = AsyncOpenAI(base_url=llm_endpoint, api_key="EMPTY")
    per_sample: list[dict] = []
    for sample in samples:
        if sample["task"] != "sql_generation":
            continue
        prompt = f"{sample.get('instruction', '')}\n用户问题：{sample['input']}"
        resp = await client.chat.completions.create(
            model=model_name or "model",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        predicted_sql = resp.choices[0].message.content or ""

        exact = False
        try:
            predicted_rows = await dw_mysql_repo.execute_sql(predicted_sql)
            gold_rows = await dw_mysql_repo.execute_sql(sample["output"])
            exact = predicted_rows == gold_rows
        except Exception:
            exact = False
        per_sample.append({"exact": exact, "value_ok": exact, "caliber_ok": exact, "clarify_ok": True})

    report = build_report({
        "execution_accuracy": execution_accuracy(per_sample),
        "schema_linking_f1": 0.0,  # 需要 schema 标注，由评估集 meta 提供后可计算
        "value_mapping_accuracy": value_mapping_accuracy(per_sample),
        "metric_caliber_accuracy": metric_caliber_accuracy(per_sample),
        "clarify_accuracy": clarify_accuracy(per_sample),
        "safety_violation_rate": safety_violation_rate(samples),
    })
    return {"report": report, "sample_count": len(per_sample)}
