from datetime import datetime

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState, DateInfoState, DBInfoState
from app.core.log import logger


async def add_extra_context(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自定义节点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage":"添加额外信息"})
    try:
        dw_mysql_repo = runtime.context["dw_mysql_repo"]

        # 1. 得到当前日期信息
        today = datetime.today()
        date = today.strftime("%Y-%m-%d")
        weekday = today.strftime("%A")
        quarter = f"Q{(today.month+2)//3}"
        # 1 2 3  ->1
        date_info = DateInfoState(
            date=date,
            weekday=weekday,
            quarter=quarter
        )

        # 2. 得到数据库信息
        db_info_dict = await dw_mysql_repo.get_db_info()
        db_info: DBInfoState = DBInfoState(**db_info_dict)

        logger.info(f"完成添加额外信息 date_info={date_info}, db_info={db_info}")

        # 3.返回日期和数据库信息
        return {"date_info": date_info, "db_info": db_info}
    except Exception as e:
        logger.error(f"添加额外信息失败：{str(e)}")
        raise
