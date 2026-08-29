from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState, ColumnInfoState, TableInfoState, MetricInfoState
from app.core.log import logger
from app.models.mysql.column_info_mysql import ColumnInfoMySQL
from app.models.mysql.table_info_mysql import TableInfoMySQL
from app.models.qdrant.column_info_qdrant import ColumnInfoQdrant
from app.models.qdrant.metric_info_qdrant import MetricInfoQdrant

"""
1.收集一个最完整的字段信息列表 去重合并 dict[column_id,ColumnlnfoQdrant]
1.1.收集召回的字段信息列表
1.2.收集召回的指标信息列表联的字段信息列表
1.3.收集召回的字段值信息列表对应的字段信息列表=》将字段值保存到字段的值的样例列表中
1.4.收集相表的主键和外键字段信息列表
2.根据收集所有字段信息列表生成:带字段信息列表的表信息列表
2.1.对收集的字段信息列表进行按表id进行分组:dict[table_id, list[ColumnlnfoQdrant]]
2.2.生成带字段信息列表的表信息列表 -》table_infos:list[TablelnfoState]
    根据表id查询meta得到表信息
    根据当前字段信息列表·生成ColumnlnfoState类型的字段状态信息列表
"""
async def merge_retrieved_info(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    # 自定义节点输出给外部调用者 =》最终在浏览器端显示
    runtime.stream_writer({"stage": "合并召回"})
    try:
        recall_columns = state["recall_columns"]
        recall_metrics = state["recall_metrics"]
        recall_values = state["recall_values"]
        meta_mysql_repo = runtime.context["meta_mysql_repo"]

        # 1.收集一个最完整的字段信息列表 去重合并 dict[column_id,ColumnlnfoQdrant]
        # 1.1.收集召回的字段信息列表
        column_infos_dict: dict[str, ColumnInfoQdrant] = {item['id']:item for item in recall_columns}
        # 1.2.收集召回的指标信息列表联的字段信息列表
        for metric in recall_metrics:
            for column_id in metric['relevant_columns']:
                # 只有字典集合不存在才处理
                if column_id not in column_infos_dict:
                    # 根据字段id查询得到对应的字段信息对象
                    column_info_mysql =  await meta_mysql_repo.get_column_info_by_id(column_id)
                    column_infos_dict[column_id] = _convert_column_info_mysql_to_qdrant(column_info_mysql)
        # 1.3.收集召回的字段值信息列表对应的字段信息列表=》将字段值保存到字段的值的样例列表中
        for value_info in recall_values:
            column_id = value_info["column_id"]
            # 只有字典集合不存在才处理
            if column_id not in column_infos_dict:
                # 根据字段id查询得到对应的字段信息对象
                column_info_mysql = await meta_mysql_repo.get_column_info_by_id(column_id)
                column_infos_dict[column_id] = _convert_column_info_mysql_to_qdrant(column_info_mysql)
                # 如果字段值没有在字段信息对象的examples中，添加进去
                value = value_info["value"]
                if value not in column_infos_dict[column_id]["examples"]:
                    column_infos_dict[column_id]["examples"].append(value)


        # 2.根据收集所有字段信息列表生成:带字段信息列表的表信息列表
        table_infos: list[TableInfoState] = []
        # 2.1.对收集的字段信息列表进行按表id进行分组:dict[table_id, list[ColumnlnfoQdrant]]
        table_column_infos_dict: dict[str,list[ColumnInfoQdrant]] = {}
        for column_info in column_infos_dict.values():
            table_id = column_info["table_id"]
            if table_id not in table_column_infos_dict:
                table_column_infos_dict[table_id] = []
            table_column_infos_dict[table_id].append(column_info)

        # 2.2.生成带字段信息列表的表信息列表 -》table_infos:list[TablelnfoState]
        for table_id, column_infos in table_column_infos_dict.items():
            # 1.4.收集相表的主键和外键字段信息列表
            key_column_infos_mysql: list[ColumnInfoMySQL] = await meta_mysql_repo.get_key_column_infos(table_id)
            for key_column_info in key_column_infos_mysql:
                # 只有前面没有收集到过，才添加
                if key_column_info.id not in column_infos_dict:
                    column_infos.append(_convert_column_info_mysql_to_qdrant(key_column_info))
            # 根据表id查询meta得到表信息
            table_info_mysql: TableInfoMySQL = await meta_mysql_repo.get_table_info_by_id(table_id)
            # 根据当前字段信息列表·生成ColumnlnfoState类型的字段状态信息列表
            columns: list[ColumnInfoState] = [_convert_column_info_qdrant_to_state(item) for item in column_infos]
            table_infos.append(TableInfoState(
                name=table_info_mysql.name,
                role=table_info_mysql.role,
                description=table_info_mysql.description,
                columns=columns
            ))

        # 处理指标列表
        metric_infos: list[MetricInfoState] = [
            _convert_metric_info_qdrant_to_state(item)
            for item in recall_metrics
        ]

        logger.info(f"合并召回： table_infos={table_infos}")
        logger.info(f"合并召回： metric_infos={metric_infos}")

        return {"table_infos": table_infos, "metric_infos": metric_infos}
    except Exception as e:
        logger.error(f"合并召回失败：{str(e)}")
        raise

# 将qdrant格式的指标信息对象转换为state格式的
def _convert_metric_info_qdrant_to_state(recall_metric:MetricInfoQdrant):
    return MetricInfoState(
        name=recall_metric['name'],
        description=recall_metric["description"],
        relevant_columns=recall_metric["relevant_columns"],
        alias=recall_metric["alias"]
    )

# 将qdrant格式的字段信息转换为state格式的
def _convert_column_info_qdrant_to_state(column:ColumnInfoQdrant)->ColumnInfoState:
    return ColumnInfoState(
        name=column['name'],
        type=column['type'],
        role=column["role"],
        examples=column["examples"],
        description=column["description"],
        alias=column["alias"]
    )

# 将mysql格式的字段信息转换为qdrant格式的
def _convert_column_info_mysql_to_qdrant(column_info_mysql:ColumnInfoMySQL)->ColumnInfoQdrant:
    return ColumnInfoQdrant(
        id=column_info_mysql.id,
        name=column_info_mysql.name,
        description=column_info_mysql.description,
        role=column_info_mysql.role,
        type=column_info_mysql.type,
        examples=column_info_mysql.examples,
        table_id=column_info_mysql.table_id,
        alias=column_info_mysql.alias
    )