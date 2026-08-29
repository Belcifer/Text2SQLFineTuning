import json

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import get_llm
from app.agent.state import DataAgentState
from app.core.errors import ClarifyRequired
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def generate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自定义节点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage":"生成SQL"})
    try:
        query = state["query"]
        table_infos = state["table_infos"]
        metric_infos = state["metric_infos"]
        date_info = state["date_info"]
        db_info = state["db_info"]

        prompt_template = PromptTemplate(
            template=load_prompt("generate_sql"),
            input_variables=["query", "table_infos", "metric_infos", "db_info", "date_info"]
        )
        parser = StrOutputParser()
        chain = prompt_template | get_llm() | parser
        raw = await chain.ainvoke({
            "query": query,
            "table_infos": yaml.dump(table_infos,allow_unicode=True,  sort_keys=False),
            "metric_infos": yaml.dump(metric_infos,allow_unicode=True,  sort_keys=False),
            "date_info": yaml.dump(date_info,allow_unicode=True,  sort_keys=False),
            "db_info": yaml.dump(db_info,allow_unicode=True,  sort_keys=False),
        })

        # 澄清分流（设计书 4.4 节）：输出为 {need_clarify:true, questions:[...]} 时
        # 经 stream_writer 抛出 clarify 事件并中断链路，等待用户补充。
        try:
            parsed = json.loads(raw)
            if parsed.get("need_clarify"):
                runtime.stream_writer({"clarify": parsed})
                raise ClarifyRequired(parsed.get("questions", []))
        except json.JSONDecodeError:
            pass  # 正常 SQL 文本输出

        sql = raw.strip()
        logger.info(f"完成生成SQL: {sql}")

        return {"sql": sql}
    except Exception as e:
        logger.error(f"生成SQL失败：{str(e)}")
        raise
