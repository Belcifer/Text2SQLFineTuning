import uuid
from pydoc import text

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from pygments.lexers import tal

from app.conf.meta_config import MetaConfig, TableConfig, MetricConfig
from app.core.log import logger
from app.models.es.value_info_es import ValueInfoES
from app.models.mysql.column_info_mysql import ColumnInfoMySQL
from app.models.mysql.column_metric_mysql import ColumnMetricMySQL
from app.models.mysql.metric_info_mysql import MetricInfoMySQL
from app.models.mysql.table_info_mysql import TableInfoMySQL
from app.models.qdrant.column_info_qdrant import ColumnInfoQdrant
from app.models.qdrant.metric_info_qdrant import MetricInfoQdrant
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw_mysql_repository import DWMysqlRepository
from app.repositories.mysql.meta_mysql_repository import MetaMysqlRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


class MetaKnowledgeService:
    def __init__(
        self,
        dw_mysql_repo: DWMysqlRepository,
        meta_mysql_repo: MetaMysqlRepository,
        value_es_repo: ValueESRepository,
        column_qdrant_repo: ColumnQdrantRepository,
        metric_qdrant_repo: MetricQdrantRepository,
        embedding_client: HuggingFaceEndpointEmbeddings
    ):
        self.dw_mysql_repo = dw_mysql_repo
        self.meta_mysql_repo = meta_mysql_repo
        self.value_es_repo = value_es_repo
        self.column_qdrant_repo = column_qdrant_repo
        self.metric_qdrant_repo = metric_qdrant_repo
        self.embedding_client = embedding_client

    """
    1. 处理表和字段相关元数据
    1.1. 将表信息和字段信息保存meta库
    1.2. 将字段信息保存到qdrant库建立向量索引
    1.3. 将字段值信息保存到ES库建立全文索引
    2. 处理指标相关元数据
    2.1. 将指标信息保存到meta库
    2.2. 将指标信息保存到qdrant建立向量索引
    """
    async def build(self, config: MetaConfig):
        # 0. 清空 meta 库旧数据（支持重复构建，Qdrant/ES 由 _ensure 重建）
        await self.meta_mysql_repo.clear_meta_tables()
        # 1.处理表和字段相关元数据
        # 1.1.将表信息和字段信息保存meta库
        column_infos: list[ColumnInfoMySQL] = await self._save_table_infos_to_meta(config.tables)
        logger.info("完成将表信息和字段信息保存meta库")
        # 1.2.将字段信息保存到qdrant库建立向量索引
        await self._save_column_infos_to_qdrant(column_infos)
        logger.info("完成将字段信息保存到qdrant库建立向量索引")
        # 1.3.将字段值信息保存到ES库建立全文索引
        await self._save_value_infos_to_es(column_infos, config.tables)
        logger.info("完成将字段值信息保存到ES库建立全文索引")
        # 2.处理指标相关元数据
        # 2.1.将指标信息保存到meta库
        metric_infos: list[MetricInfoMySQL] = self._save_metric_infos_to_meta(config.metrics)
        logger.info("完成将指标信息保存到meta库")
        # 2.2.将指标信息保存到qdrant建立向量索引
        await self._save_metric_infos_to_qdrant(metric_infos)
        logger.info("完成将指标信息保存到qdrant建立向量索引")

    async def _save_table_infos_to_meta(self, tables: list[TableConfig])->list[ColumnInfoMySQL]:
        # 收集表信息列表与字段信息列表
        table_infos: list[TableInfoMySQL] = []
        column_infos: list[ColumnInfoMySQL] = []
        for table in tables:
            table_infos.append(TableInfoMySQL(
                id=table.name,
                name=table.name,
                role=table.role,
                description=table.description
            ))
            # 获取指定表中所有字段的类型  dict[字段名:字段类型]
            column_types = await self.dw_mysql_repo.get_column_types(table.name)
            for column in table.columns:
                # 获取指定表中的指定字段的前10个值
                examples = await self.dw_mysql_repo.get_clumn_values(table.name, column.name)
                column_infos.append(ColumnInfoMySQL(
                    id=f"{table.name}.{column.name}",
                    name=column.name,
                    type=column_types[column.name],
                    role=column.role,
                    examples= examples,
                    description=column.description,
                    alias=column.alias,
                    table_id=table.name
                ))

        # 将信息列表保存到meta中
        self.meta_mysql_repo.save_table_infos(table_infos)
        self.meta_mysql_repo.save_column_infos(column_infos)

        return column_infos

    async def _save_column_infos_to_qdrant(self, column_infos: list[ColumnInfoMySQL]):
        #遍历column_infos来收集数据 list[(id,payload（ColumnInfoQdrant对象）,text（name/description/alia）)]
        temp_data_list: list[dict] = []
        for column in column_infos:
            column_info_qdrant = ColumnInfoQdrant(
                id=column.id,
                name=column.name,
                type=column.type,
                role=column.role,
                examples=column.examples,
                description=column.description,
                alias=column.alias,
                table_id=column.table_id
            )
            # name
            temp_data_list.append({
                "id": uuid.uuid4(),
                "payload": column_info_qdrant,
                "text": column_info_qdrant['name']
            })
            # description
            temp_data_list.append({
                "id": uuid.uuid4(),
                "payload": column_info_qdrant,
                "text": column_info_qdrant['description']
            })

            # alias
            for alia in column.alias:
                temp_data_list.append({
                    "id": uuid.uuid4(),
                    "payload": column_info_qdrant,
                    "text": alia
                })
        # 取出所有的id
        ids:list[str] = [item["id"] for item in temp_data_list]
        # 取出所有payload
        payloads: list[ColumnInfoQdrant] = [item["payload"] for item in temp_data_list]
        # 取出所有text
        texts: list[str] = [item["text"] for item in temp_data_list]

        # 将texts批量生成向量  (需要分批处理)
        batch_size = 10
        vectors:list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_vectors:list[list[float]] = await self.embedding_client.aembed_documents(batch_texts)
            vectors.extend(batch_vectors)

        # 将数据保存到qdrant库中
        await self.column_qdrant_repo.insert_column_vectors(ids, payloads, vectors)



    async def _save_value_infos_to_es(self, column_infos:list[ColumnInfoMySQL], tables: list[TableConfig]):

        # 将所有字段是否需要建立ES标识收集起来：dict[column_id，true/false]
        colunn_sync_dict: dict[str, bool] = {}
        for table in tables:
            for column in table.columns:
                colunn_sync_dict[f"{table.name}.{column.name}"] = column.sync

        # 收集字段值信息列表
        value_infos: list[ValueInfoES] = []
        for column in column_infos:
            # 判断是否需要进行索引
            if colunn_sync_dict[column.id]:
                # 查询得到所有字段值
                values = await self.dw_mysql_repo.get_clumn_values(column.table_id, column.name, 100000)
                # print(column.name, len(values))
                for value in values:
                    value_infos.append(ValueInfoES(
                        id=f"{column.id}.{value}",
                        value=value,
                        type=column.type,
                        column_id=column.id,
                        column_name=column.name,
                        table_id=column.table_id,
                        table_name=column.table_id
                    ))

        # 保存数据到es中
        await self.value_es_repo.insert_value_infos(value_infos)



    def _save_metric_infos_to_meta(self, metrics:list[MetricConfig])->list[MetricInfoMySQL]:
        metric_infos: list[MetricInfoMySQL] = []
        column_metrics: list[ColumnMetricMySQL] = []

        for metric in metrics:
            metric_infos.append(MetricInfoMySQL(
                id=metric.name,
                name=metric.name,
                description=metric.description,
                relevant_columns=metric.relevant_columns,
                alias=metric.alias
            ))
            for column_id in metric.relevant_columns:
                column_metrics.append(ColumnMetricMySQL(
                    metric_id=metric.name,
                    column_id=column_id
                ))


        self.meta_mysql_repo.save_metric_infos(metric_infos)
        self.meta_mysql_repo.save_column_metrics(column_metrics)

        return metric_infos



    async def _save_metric_infos_to_qdrant(self, metric_infos: list[MetricInfoMySQL]):
        # 遍历metric_infos来收集数据 list[(id,payload（MetricInfoQdrant对象）,text（name/description/alia）)]
        temp_data_list: list[dict] = []
        for metric in metric_infos:
            metric_info_qdrant = MetricInfoQdrant(
                id=metric.id,
                name=metric.name,
                relevant_columns=metric.relevant_columns,
                description=metric.description,
                alias=metric.alias
            )
            # name
            temp_data_list.append({
                "id": uuid.uuid4(),
                "payload": metric_info_qdrant,
                "text": metric_info_qdrant['name']
            })
            # description
            temp_data_list.append({
                "id": uuid.uuid4(),
                "payload": metric_info_qdrant,
                "text": metric_info_qdrant['description']
            })

            # alias
            for alia in metric.alias:
                temp_data_list.append({
                    "id": uuid.uuid4(),
                    "payload": metric_info_qdrant,
                    "text": alia
                })
        # 取出所有的id
        ids: list[str] = [item["id"] for item in temp_data_list]
        # 取出所有payload
        payloads: list[MetricInfoQdrant] = [item["payload"] for item in temp_data_list]
        # 取出所有text
        texts: list[str] = [item["text"] for item in temp_data_list]

        # 将texts批量生成向量  (需要分批处理)
        batch_size = 10
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_vectors: list[list[float]] = await self.embedding_client.aembed_documents(batch_texts)
            vectors.extend(batch_vectors)

        # 将数据保存到qdrant库中
        await self.metric_qdrant_repo.insert_metric_vectors(ids, payloads, vectors)