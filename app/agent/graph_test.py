import asyncio
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

from app.repositories.es.value_es_repository import ValueESRepository

"""
langgraph相关重要概念
    状态图：StateGraph的实例
    节点：实现特定功能的函数
    状态：包含多个可变数据的对象，在图的各个节点上传递
    边： 它是A->B2个节点的连线, A执行后执行B，且将最新的状态数据传递给B
节点函数的参数：
    state: 状态对象   自定义类型
    runtime: Runtime  运行时对象，包含:
        stream_writer: 向调用者输出自定义数据的函数
        store:实现跨会话长期记忆的对象，默认是保存在内存中
        context: 包含固定数据或依赖的外部模块的对象   自定义类型
    config：ConfigRunnable 保存配置的对象，比如执行时指定的thread_id
stream_mode:
    updates: 外部得到是节点返回的更新
    values: 外部得到是节点返回后合并后的state值
    custom: 外部得到是stream_writer指定的自定义数据
"""

# 自定义state类型
# 包含一些可变的数据   在节点之间不断传递
class Mystate(TypedDict):
    query:str
    keywords:list[str]
    sql: str
    error:str

# 自定义Context类型
# 包含一些固定的数据或依赖模块
class MyContext(TypedDict):
    db_name: str
    value_es_repo: ValueESRepository

# 定义节点
# 实现特定功能的函数
def extract_keywords(state: Mystate, runtime: Runtime[MyContext], config: RunnableConfig):

    # 向调用者输出自定义数据
    runtime.stream_writer("提取关键字")

    db_name = runtime.context["db_name"]
    print(f'db_name={db_name}', flush=True)
    print(runtime)
    print(config)

    query = state['query']

    keywords = ["你", "是", "谁"]

    print(f"提取关键字 query={query}, keywords={keywords}")

    # 返回更新， 不要直接更新state中的状态数据
    return {"keywords": keywords}  # 返回后框架后自动合并到state中

def generate_sql(state: Mystate, runtime: Runtime):

    runtime.stream_writer("生成SQL")

    sql = "select * from xxx"
    print('generate_sql', state)
    print(f"生成sql: {sql}")

    return {"sql": sql}

# 创建状态图
state_graph = StateGraph(
    state_schema = Mystate,  # 指定状态类型
    context_schema=MyContext # 指定上下文类型
)

# 添加节点
state_graph.add_node("extract_keywords", extract_keywords)
state_graph.add_node("generate_sql", generate_sql)

# 添加边
state_graph.add_edge(START, "extract_keywords")
state_graph.add_edge("extract_keywords", "generate_sql")
state_graph.add_edge("generate_sql", END)

# 编译图
compiled_graph = state_graph.compile()

if __name__ == '__main__':
    async def test():
        state = Mystate(query="你是谁？")
        context = MyContext(db_name="dw")
        async for chunk in compiled_graph.astream(
                input=state,  # 指定状态对象
                context=context, # 指定context对象
                stream_mode="custom",
                config={"thread_id": 'abc'}
        ):
            print('----', chunk)


    asyncio.run(test())