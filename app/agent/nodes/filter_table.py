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
1. 利用大模型对表和字段进行过滤
    {
        "表名1":["字段1", "字段2", "..."],
        "表名2":["字段1", "字段2", "..."]
    }
2. 对table_infos进行表和字段的过滤
3. 返回过滤后的table_infos
"""
async def filter_table(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自宝定义点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage":"过滤表"})
    try:
        table_infos = state["table_infos"]
        query = state["query"]

        # 1. 利用大模型对表和字段进行过滤
        prompt_template = PromptTemplate(
            template=load_prompt("filter_table_info"),
            input_variables=["query", "table_infos"]
        )
        parser = JsonOutputParser()
        chain = prompt_template | get_llm() | parser
        result = await chain.ainvoke({
            "query": query,
            "table_infos": yaml.dump(
                table_infos,
                allow_unicode=True, # 保留中文原文，不转换为unicode编码  ‘\u5317\u4eac’
                sort_keys=False, # 不要对数据中的字典中的属性进行排序，保持原来的顺序
            )
        })  # list[keyword, keyword]
        logger.info(f"filter_table llm tables={result}")
        '''
        {
            "表名1":["字段1", "字段2", "..."],
            "表名2":["字段1", "字段2", "..."]
        }
        '''

        # 2. 对table_infos进行表和字段的过滤
        for table in table_infos[:]:  # 浅拷贝
            table_name = table["name"]
            if table_name not in result:
                table_infos.remove(table)  # 过滤表
            else:
                columns = table["columns"]
                for column in columns[:]:
                    column_name = column["name"]
                    if (column_name not in result[table_name]):
                        columns.remove(column) # 过滤字段
        logger.info(f"完成过滤表和字段：{table_infos}")
        # 3. 返回过滤后的table_infos
        return {"table_infos": table_infos}
    except Exception as e:
        logger.error(f"过滤表失败：{str(e)}")
        raise
