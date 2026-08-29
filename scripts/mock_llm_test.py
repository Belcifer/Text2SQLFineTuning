"""问数链路全链路测试（mock LLM，检索/编排/校验/执行真实执行）。

- Qdrant 走临时容器端口 10000（脚本内 patch app_config）
- 7 个节点的 get_llm() 被替换为 FakeLLM（按输入键分发各节点输出契约）
- 验证：/query/sync 与 /query(SSE) 全链路不报错
用法：PYTHONPATH=. ./.venv/Scripts/python.exe scripts/mock_llm_test.py
"""
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from app.conf.app_config import app_config

app_config.qdrant.port = 10000

import main as app_module  # noqa: E402
import app.agent.nodes.recall_column as rc  # noqa: E402
import app.agent.nodes.recall_metric as rm  # noqa: E402
import app.agent.nodes.recall_value as rv  # noqa: E402
import app.agent.nodes.filter_metric as fm  # noqa: E402
import app.agent.nodes.filter_table as ft  # noqa: E402
import app.agent.nodes.generate_sql as gs  # noqa: E402
import app.agent.nodes.correct_sql as cs  # noqa: E402

PASS, FAIL = 0, 0
results: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        results.append(f"[PASS] {name}")
    else:
        FAIL += 1
        results.append(f"[FAIL] {name} {detail}")


# 基于"华北地区销售总额"的标准 SQL（dw 库 schema 对应）
_SQL = ("SELECT r.region_name, SUM(o.order_amount) AS 销售总额 FROM fact_order o "
        "JOIN dim_region r ON o.region_id = r.region_id WHERE r.region_name = '华北' GROUP BY r.region_name")


class FakeLLM(Runnable):
    """按节点输入键分发各节点输出契约的伪模型（Runnable 兼容）。"""

    def invoke(self, inputs: dict, config=None):
        return self._respond(inputs)

    async def ainvoke(self, inputs: dict, config=None):
        return self._respond(inputs)

    def _respond(self, inputs):
        text = inputs if isinstance(inputs, str) else str(inputs)
        # correct_sql
        if "待纠正的 SQL" in text or "SQL 执行错误信息" in text:
            return AIMessage(content=_SQL)
        # generate_sql
        if "将用户的自然语言查询转换为语法正确" in text:
            return AIMessage(content=_SQL)
        # filter_table
        if "候选表及字段信息" in text:
            return AIMessage(content='{"fact_order": ["order_amount", "region_id"], "dim_region": ["region_name", "region_id"]}')
        # filter_metric
        if "候选指标信息" in text:
            return AIMessage(content="[]")
        # recall_value
        if "字段取值" in text or "取值候选" in text:
            return AIMessage(content='["华北"]')
        # recall_metric
        if "指标检索关键词" in text or "指标语义扩展" in text:
            return AIMessage(content='["成交总额"]')
        # recall_column（字段召回，兜底）
        return AIMessage(content='["销售额", "地区"]')


def main():
    for mod in (rc, rm, rv, fm, ft, gs, cs):
        mod.get_llm = lambda: FakeLLM()

    with TestClient(app_module.app, raise_server_exceptions=False) as client:
        # 非流式全链路
        r = client.post("/api/v1/query/sync", json={"query": "华北地区销售总额"})
        body = r.json()
        check("POST /query/sync code=0", body["code"] == 0, r.text[:300])
        data = body.get("data", {})
        if body["code"] == 0:
            check("生成SQL非空", bool(data.get("sql")))
            check("执行返回结果", data.get("row_count", -1) >= 1 and data["row_count"] == len(data.get("rows", [])), str(data)[:200])
            stages = data.get("stages", [])
            check("链路阶段完整(11节点)", all(s in stages for s in ["提取关键字", "召回字段", "召回指标", "召回字段值", "合并召回", "过滤指标", "过滤表", "添加额外信息", "生成SQL", "校验SQL", "执行SQL"]), str(stages))

        # 流式 SSE
        r = client.post("/api/v1/query", json={"query": "华北地区销售总额"})
        text = r.text
        check("POST /query SSE", r.status_code == 200 and "event: stage" in text and "event: result" in text and "event: done" in text, text[:300])

        # 澄清分流：query 信息不足时 mock 返回 clarify（FakeLLM 固定返回 SQL，此处直接验证 clarify 事件格式函数）
        from app.services.query_service import _sse
        sse_clarify = _sse("clarify", {"need_clarify": True, "questions": ["请明确时间范围"], "thread_id": "t1"})
        check("clarify 事件格式", "event: clarify" in sse_clarify and "请明确时间范围" in sse_clarify)

    print("\n".join(results))
    print(f"\n===== PASS {PASS} / FAIL {FAIL} =====")


if __name__ == "__main__":
    main()
