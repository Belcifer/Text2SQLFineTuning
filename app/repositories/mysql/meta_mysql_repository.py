from sqlalchemy import Select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mysql.column_info_mysql import ColumnInfoMySQL
from app.models.mysql.column_metric_mysql import ColumnMetricMySQL
from app.models.mysql.metric_info_mysql import MetricInfoMySQL
from app.models.mysql.table_info_mysql import TableInfoMySQL

"""
操作mysql数据库中的meta库
"""
class MetaMysqlRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # 向table_info表插入多条数据
    def save_table_infos(self, table_infos:list[TableInfoMySQL]):
        self.session.add_all(table_infos)

    # 向column_info表插入多条数据
    def save_column_infos(self, column_infos:list[ColumnInfoMySQL]):
        self.session.add_all(column_infos)

    # 向metric_info表插入多条数据
    def save_metric_infos(self, metric_infos:list[MetricInfoMySQL]):
        self.session.add_all(metric_infos)

    # 向column_metric表插入多条数据
    def save_column_metrics(self, column_metrics:list[ColumnMetricMySQL]):
        self.session.add_all(column_metrics)

    # 根据字段id查字段信息
    async def get_column_info_by_id(self, column_id: str) ->ColumnInfoMySQL:
        return await self.session.get(ColumnInfoMySQL, column_id)

    # 根据表id查表信息
    async def get_table_info_by_id(self, table_id: str) ->TableInfoMySQL:
        return await self.session.get(TableInfoMySQL, table_id)

    # 查询指定表的主键和外键字段信息列表
    async def get_key_column_infos(self, table_id: str) ->list[ColumnInfoMySQL]:
        result = await self.session.execute(
            Select(ColumnInfoMySQL)
            .where(ColumnInfoMySQL.table_id==table_id)
            .where(ColumnInfoMySQL.role.in_(["primary_key", 'foreign_key']))

        )

        return result.scalars().all()

    # 清空元数据表（知识库重建前置，避免主键冲突）
    async def clear_meta_tables(self):
        await self.session.execute(delete(ColumnMetricMySQL))
        await self.session.execute(delete(ColumnInfoMySQL))
        await self.session.execute(delete(MetricInfoMySQL))
        await self.session.execute(delete(TableInfoMySQL))
