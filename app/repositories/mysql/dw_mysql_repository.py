from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, result

"""
操作mysql数据库中dw库
"""
class DWMysqlRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # 得到指定表中所有字段的类型
    async def get_column_types(self, table_name: str)->dict[str,str]:
        sql = f"show columns from {table_name}"
        result = await self.session.execute(text(sql))
        return { row.Field:row.Type for row in result.all()}


    # 得到指定表中的指定字段的指定数量的值
    async def get_clumn_values(self, table_name:str, column_name: str, limit:int=10)->list:
        sql = f"select distinct {column_name} from {table_name} limit {limit}"
        result = await self.session.execute(text(sql))
        return result.scalars().all()

    # 获取数据库名称和版本
    async def get_db_info(self)->dict[str,str]:
        result = await self.session.execute(text("select version()"))
        version: str = result.scalar()
        dialect = self.session.get_bind().dialect.name
        return {"version": version, "dialect": dialect}

    # 校验SQL语法是否正确， 不正确抛出错误
    async def validate_sql(self, sql: str):
        await self.session.execute(text(f"explain {sql}"))

    # 执行指定的查询的SQL
    async def execute_sql(self, sql:str)->list:
        result = await self.session.execute(text(sql))

        # return result.mappings().all()  # [rowMapping, rowMapping]
        return [dict(item) for item in result.mappings().all()]