from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import get_llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.models.es.value_info_es import ValueInfoES
from app.models.qdrant.column_info_qdrant import ColumnInfoQdrant
from app.prompt.prompt_loader import load_prompt

"""
1. 对提问利用大模型进行语义化关键字提取
2. 与jiaba分词的关键进行去重合并   keywords
3. 遍历每个keyword,去es中搜索匹配的字段值信息列表
4. 对得到字段值信息列表进行去重合并  recall_values: list[ValueInfoES]
5. 返回数据recall_values

"""
async def recall_value(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自定义节点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage": "召回字段值"})
    try:
        query = state["query"]
        keywords = state["keywords"]
        value_es_repo = runtime.context["value_es_repo"]

        # 1. 对提问利用大模型进行语义化关键字提取
        prompt_template = PromptTemplate(
            template=load_prompt("extend_keywords_for_value_recall"),
            input_variables=["query"]
        )
        parser = JsonOutputParser()
        chain = prompt_template | get_llm() | parser
        result = await chain.ainvoke({"query": query})  # list[keyword, keyword]
        logger.info(f"recall_value llm keywords={result}")

        # 2. 与jiaba分词的关键进行去重合并   keywords
        keywords = list(set(result + keywords))
        logger.info(f"recall_value  keywords={keywords}")


        value_infos_dict: dict[str, ValueInfoES] = {}
        # 3. 遍历每个keyword,去es中搜索匹配的字段值信息列表
        for keyword in keywords:
            value_infos: list[ValueInfoES] = await value_es_repo.search(keyword)
            # 4. 对得到字段值信息列表进行去重合并  recall_values: list[ValueInfoES]
            for value_info in value_infos:
                value_id = value_info["id"]

                if value_id not in value_infos_dict:
                    value_infos_dict[value_id] = value_info

        recall_values:list[ValueInfoES] = list(value_infos_dict.values())
        logger.info(f"召回字段值成功： {recall_values}")

        # 4. 返回数据recall_values
        return {"recall_values": recall_values}
    except Exception as e:
        logger.error(f"召回字段值失败：{e}")
        raise
