import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import get_llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def correct_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自定义节点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage":"校正SQL"})
    try:
        query = state["query"]
        table_infos = state["table_infos"]
        metric_infos = state["metric_infos"]
        date_info = state["date_info"]
        db_info = state["db_info"]
        sql = state["sql"]
        error = state["error"]

        prompt_template = PromptTemplate(
            template=load_prompt("correct_sql"),
            input_variables=["query", "table_infos", "metric_infos", "db_info", "date_info", 'sql', 'error']
        )
        parser = StrOutputParser()
        chain = prompt_template | get_llm() | parser
        sql = await chain.ainvoke({
            "query": query,
            "table_infos": yaml.dump(table_infos,allow_unicode=True,  sort_keys=False),
            "metric_infos": yaml.dump(metric_infos,allow_unicode=True,  sort_keys=False),
            "date_info": yaml.dump(date_info,allow_unicode=True,  sort_keys=False),
            "db_info": yaml.dump(db_info,allow_unicode=True,  sort_keys=False),
            "sql": sql,
            "error": error
        })

        logger.info(f"完成校正生成SQL: {sql}")

        return {"sql": sql}
    except Exception as e:
        logger.error(f"校正生成SQL失败：{str(e)}")
        raise
