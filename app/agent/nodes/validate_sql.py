from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自定义节点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage": "校验SQL"})
    try:
        sql = state['sql']
        dw_mysql_repo = runtime.context["dw_mysql_repo"]

        await dw_mysql_repo.validate_sql(sql)

        # raise Exception("SQL中的关键字有可能有问题")

        logger.info("校验SQL成功")

        return {"error": None}
    except Exception as e:
        logger.error(f"校验SQL失败：{str(e)}")
        return {"error": f"校验SQL失败： {str(e)}"}
