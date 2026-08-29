from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import get_llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.models.qdrant.metric_info_qdrant import MetricInfoQdrant
from app.prompt.prompt_loader import load_prompt

"""
1. 对提问利用大模型进行语义化关键字提取
2. 与jiaba分词的关键进行去重合并   keywords
3. 生成keywords向量列表：keyword_vectors
3. 遍历每个keyword_vectors,去qdrant中搜索匹配的指标信息列表
4. 对得到指标信息列表进行去重合并  recall_metrics: list[MetricInfoQdrant]
5. 返回数据recall_metrics

"""
async def recall_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自定义节点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage": "召回指标"})
    try:
        query = state["query"]
        keywords = state["keywords"]
        metric_qdrant_repo = runtime.context["metric_qdrant_repo"]
        embedding_client = runtime.context["embedding_client"]

        # 1. 对提问利用大模型进行语义化关键字提取
        prompt_template = PromptTemplate(
            template=load_prompt("extend_keywords_for_metric_recall"),
            input_variables=["query"]
        )
        parser = JsonOutputParser()
        chain = prompt_template | get_llm() | parser
        result = await chain.ainvoke({"query": query})  # list[keyword, keyword]
        logger.info(f"recall_metric llm keywords={result}")

        # 2. 与jiaba分词的关键进行去重合并   keywords
        keywords = list(set(result + keywords))
        logger.info(f"recall_metric  keywords={keywords}")

        # 3. 生成keywords向量列表：keyword_vectors
        keyword_vectors: list[list[float]] = await embedding_client.aembed_documents(keywords)
        # print('-++++', keyword_vectors)
        metric_infos_dict: dict[str, MetricInfoQdrant] = {}
        # 3. 遍历每个keyword_vectors,去qdrant中搜索匹配的指标信息列表
        for keyword_vector in keyword_vectors:
            metric_infos: list[MetricInfoQdrant] = await metric_qdrant_repo.search(keyword_vector)
            # 4. 对得到指标信息列表进行去重合并  recall_metrics: list[MetricInfoQdrant]
            for metric_info in metric_infos:
                metric_id = metric_info["id"]
                # metric_infos_dict[metric_id]: 当字典没有这个key时，会报错
                # if not metric_infos_dict[metric_id]:
                # if metric_infos_dict[metric_id] is None:
                if metric_id not in metric_infos_dict:
                    metric_infos_dict[metric_id] = metric_info

        recall_metrics:list[MetricInfoQdrant] = list(metric_infos_dict.values())
        logger.info(f"召回指标成功： {recall_metrics}")

        # 5. 返回数据recall_metrics
        return {"recall_metrics": recall_metrics}
    except Exception as e:
        logger.error(f"召回指标失败：{e}")
        raise
