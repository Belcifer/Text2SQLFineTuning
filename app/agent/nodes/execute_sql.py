from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def execute_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自定义节点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage":"执行SQL"})
    try:
        sql = state["sql"]
        dw_mysql_repo = runtime.context["dw_mysql_repo"]

        result: list = await dw_mysql_repo.execute_sql(sql)
        # 将查询结果与最终SQL输出给调用者（API 文档 2.1 的 result 事件）
        runtime.stream_writer({"result": result, "sql": sql})

        return {}  # 最后一个节点，不需要返回任何数据
    except Exception as e:
        logger.error(f"执行SQL失败：{str(e)}")
        raise
