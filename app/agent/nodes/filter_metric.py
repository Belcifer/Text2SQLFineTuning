import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import get_llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt

"""
1. 利用大模型对指标进行过滤   [指标名1， 指标名2]
2. 对metric_infos进行过滤
3. 返回过滤后的metric_infos
"""
async def filter_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自宝定义点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage":"过滤指标"})
    try:
        metric_infos = state["metric_infos"]
        query = state["query"]

        # 1. 利用大模型对指标进行过滤   [指标名1， 指标名2]
        prompt_template = PromptTemplate(
            template=load_prompt("filter_metric_info"),
            input_variables=["query", "metric_infos"]
        )
        parser = JsonOutputParser()
        chain = prompt_template | get_llm() | parser
        result = await chain.ainvoke({
            "query": query,
            "metric_infos": yaml.dump(
                metric_infos,
                allow_unicode=True, # 保留中文原文，不转换为unicode编码  ‘\u5317\u4eac’
                sort_keys=False, # 不要对数据中的字典中的属性进行排序，保持原来的顺序
            )
        })  # list[keyword, keyword]
        logger.info(f"filter_metric llm names={result}")


        # 2. 对metric_infos进行过滤
        for metric in metric_infos[:]:  # 浅拷贝
            metric_name = metric["name"]
            if metric_name not in result:
                metric_infos.remove(metric)  # 过滤指标

        logger.info(f"完成过滤指标：{metric_infos}")
        # 3. 返回过滤后的metric_infos
        return {"metric_infos": metric_infos}
    except Exception as e:
        logger.error(f"过滤指标失败：{str(e)}")
        raise
