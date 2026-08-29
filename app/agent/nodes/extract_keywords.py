from jieba.analyse import extract_tags
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def extract_keywords(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自定义节点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage":"提取关键字"})
    try:
        query = state['query']

        # 定义返回指定词性的元组
        allow_pos = (
            "n",  # 名词: 数据、服务器、表格
            "nr",  # 人名: 张三、李四
            "ns",  # 地名: 北京、上海
            "nt",  # 机构团体名: 政府、学校、某公司
            "nz",  # 其他专有名词: Unicode、哈希算法、诺贝尔奖
            "v",  # 动词: 运行、开发
            "vn",  # 名动词: 工作、研究
            "a",  # 形容词: 美丽、快速
            "an",  # 名形词: 难度、合法性、复杂度
            "eng",  # 英文
            "i",  # 成语
            "l",  # 常用固定短语
        )
        # 使用jieba提取关键字
        keywords:list[str] = extract_tags(query, topK=10, allowPOS=allow_pos)
        # logger.info(f"jiaba分词： {keywords}")
        # 将query添加到keywords中，防止丢失语义
        keywords = list(set(keywords + [query]))

        logger.info(f"提取关键字完成： {keywords}")
        return {"keywords": keywords}
    except Exception as e:
        logger.error(f"提取关键字失败：{str(e)}")
        raise
