import asyncio
from typing import Optional

from sqlalchemy import text, Select

from app.conf.app_config import DBConfig, app_config
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession, async_sessionmaker

from app.models.mysql.table_info_mysql import TableInfoMySQL

"""
用来操作mysql数据的客户端管理器模块
"""
class MysqlClientManager:
    def __init__(self, config: DBConfig):
        self.config = config
        self.client: Optional[AsyncEngine] = None  # AsyncEngine|None
        self.sesion_factory: Optional[async_sessionmaker] = None

    def _get_url(self):
        return f"mysql+asyncmy://{self.config.user}:{self.config.password}@{self.config.host}/{self.config.database}?charset=utf8mb4"

    def init_client(self):
        self.client = create_async_engine(
            self._get_url(),
            pool_size=10, # 连接池的大小  初始化创建的常驻连接的个数，默认是5个
            max_overflow=5, # 最大创建的临时连接数  默认是10个
            # 当常驻连接用满时，创建临时连接
            # 临时连接也满了，等待指定的时间，在这个时间内
                # 如果有常用驻连接返回，直接使用，如果临时连接释放了，创建一个新的临时连接
                # 否则报错
        )
        self.sesion_factory = async_sessionmaker(
            bind=self.client,
            autobegin=True,  # 自动开启事务
            autoflush=True  # 自动刷新   将未提交的更新刷新到暂存区, 后面的查询就能得到它
        )

    async def close(self):
        await self.client.dispose()

# 创建针对dw库的客户端管理器
dw_mysql_client_manager = MysqlClientManager(app_config.db_dw)
# 创建针对meta库的客户端管理器
meta_mysql_client_manager = MysqlClientManager(app_config.db_meta)

if __name__ == '__main__':
    async def test():
        # 初始化创建客户端
        dw_mysql_client_manager.init_client()
        # client = dw_mysql_client_manager.client

        # 创建会话对象
        # async with AsyncSession(
        #     bind=client,
        #     autobegin=True, # 自动开启事务
        #     autoflush=True # 自动刷新   将未提交的更新刷新到暂存区, 后面的查询就能得到它
        # ) as session:
        assert dw_mysql_client_manager.sesion_factory
        async with dw_mysql_client_manager.sesion_factory() as session:

            # 执行SQL查询
            sql = "select * from dim_customer limit 2"
            result = await session.execute(text(sql))
            """
            result.all(): 返回[row, row, row]  row对象是包含当前行字段值的可遍历的对象
            result.mappings().all(): 返回[rowMapping, rowMapping, rowMapping]  rowMapping对象是包含当前行字段名和字段值的可遍历的对象
            result.scalars().all(): 返回[val, val, val]  val是查询的第一个字段的值
            """
            # 读取查询得到的所有数据
            # rows = result.all()
            # for row in rows:
            #     print(row, type(row))
            #     for val in row:
            #         print(val)
            # print(rows[0].customer_name)
            # print(rows[0]['customer_name'])  不可用

            # rows = result.mappings().all()
            # for row in rows:
            #     print(row, type(row))
            #     for key, val in row.items():
            #         print(key, val)
            # print(rows[0].customer_name)
            # print(rows[0]['customer_name'])

            rows = result.scalars().all()
            for val in rows:
                print(val)



        # 关闭客户端
        await dw_mysql_client_manager.close()


    # 测试ORM的插入和查询
    async def test_orm():
        meta_mysql_client_manager.init_client()

        assert meta_mysql_client_manager.sesion_factory
        async with meta_mysql_client_manager.sesion_factory() as session:
            # 插入一条数据
            table_info1 = TableInfoMySQL(
                id="dim_customer1",
                name="dim_customer1",
                role="dim",
                description="客户信息表1"
            )
            session.add(table_info1)

            # 插入多条数据
            table_info2 = TableInfoMySQL(
                id="dim_customer2",
                name="dim_customer2",
                role="dim",
                description="客户信息表2"
            )
            table_info3 = TableInfoMySQL(
                id="dim_customer3",
                name="dim_customer3",
                role="dim",
                description="客户信息表3"
            )
            session.add_all([table_info2, table_info3])

            # 提交
            await session.commit()

            # 查询一条数据
            table_info = await session.get(TableInfoMySQL, "dim_customer1")
            print(table_info, table_info.description)
            # 查询多条数据
            result = await session.execute(Select(TableInfoMySQL).limit(2))
            table_infos: list[TableInfoMySQL] = result.scalars().all()
            print(table_infos)
            print(table_infos[0].description)


        await meta_mysql_client_manager.close()

        # 测试ORM的插入和查询


    # 测试ORM的更新和删除
    async def test_orm2():
        meta_mysql_client_manager.init_client()

        assert meta_mysql_client_manager.sesion_factory
        async with meta_mysql_client_manager.sesion_factory() as session:
            # 更新数据
            table_info = await session.get(TableInfoMySQL, "dim_customer1")
            table_info.description = 'aaa'

            # 删除数据
            await session.delete(table_info)
            # 提交事务
            await session.commit()

        await meta_mysql_client_manager.close()

    # asyncio.run(test())
    # asyncio.run(test_orm())
    asyncio.run(test_orm2())