from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import get_llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.models.qdrant.column_info_qdrant import ColumnInfoQdrant
from app.prompt.prompt_loader import load_prompt

"""
1. 对提问利用大模型进行语义化关键字提取
2. 与jiaba分词的关键进行去重合并   keywords
3. 生成keywords向量列表：keyword_vectors
3. 遍历每个keyword_vectors,去qdrant中搜索匹配的字段信息列表
4. 对得到字段信息列表进行去重合并  recall_columns: list[ColumnInfoQdrant]
5. 返回数据recall_columns

"""
async def recall_column(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自定义节点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage": "召回字段"})
    try:
        query = state["query"]
        keywords = state["keywords"]
        column_qdrant_repo = runtime.context["column_qdrant_repo"]
        embedding_client = runtime.context["embedding_client"]

        # 1. 对提问利用大模型进行语义化关键字提取
        prompt_template = PromptTemplate(
            template=load_prompt("extend_keywords_for_column_recall"),
            input_variables=["query"]
        )
        parser = JsonOutputParser()
        chain = prompt_template | get_llm() | parser
        result = await chain.ainvoke({"query": query})  # list[keyword, keyword]
        logger.info(f"recall_column llm keywords={result}")

        # 2. 与jiaba分词的关键进行去重合并   keywords
        keywords = list(set(result + keywords))
        logger.info(f"recall_column  keywords={keywords}")

        # 3. 生成keywords向量列表：keyword_vectors
        keyword_vectors: list[list[float]] = await embedding_client.aembed_documents(keywords)
        # print('-++++', keyword_vectors)
        column_infos_dict: dict[str, ColumnInfoQdrant] = {}
        # 3. 遍历每个keyword_vectors,去qdrant中搜索匹配的字段信息列表
        for keyword_vector in keyword_vectors:
            column_infos: list[ColumnInfoQdrant] = await column_qdrant_repo.search(keyword_vector)
            # 4. 对得到字段信息列表进行去重合并  recall_columns: list[ColumnInfoQdrant]
            for column_info in column_infos:
                column_id = column_info["id"]
                # column_infos_dict[column_id]: 当字典没有这个key时，会报错
                # if not column_infos_dict[column_id]:
                # if column_infos_dict[column_id] is None:
                if column_id not in column_infos_dict:
                    column_infos_dict[column_id] = column_info

        recall_columns:list[ColumnInfoQdrant] = list(column_infos_dict.values())
        logger.info(f"召回字段成功： {recall_columns}")

        # 5. 返回数据recall_columns
        return {"recall_columns": recall_columns}
    except Exception as e:
        logger.error(f"召回字段失败：{e}")
        raise
