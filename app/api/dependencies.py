from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import dw_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.conf.meta_config import meta_config
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw_mysql_repository import DWMysqlRepository
from app.repositories.mysql.meta_mysql_repository import MetaMysqlRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.finetune_service import FinetuneService
from app.services.meta_knowledge_service import MetaKnowledgeService
from app.services.model_service import ModelService
from app.services.query_service import QueryService


# ==================== 会话依赖 ====================

async def get_dw_session():
    async with dw_mysql_client_manager.sesion_factory() as session:
        yield session


async def get_meta_session():
    async with meta_mysql_client_manager.sesion_factory() as session:
        yield session


# ==================== 服务依赖 ====================

def get_query_service(
    dw_session: AsyncSession = Depends(get_dw_session),
    meta_session: AsyncSession = Depends(get_meta_session),
) -> QueryService:
    return QueryService(
        dw_mysql_repo=DWMysqlRepository(dw_session),
        meta_mysql_repo=MetaMysqlRepository(meta_session),
        value_es_repo=ValueESRepository(es_client_manager.client),
        column_qdrant_repo=ColumnQdrantRepository(qdrant_client_manager.client),
        metric_qdrant_repo=MetricQdrantRepository(qdrant_client_manager.client),
        embedding_client=embedding_client_manager.client,
    )


def get_finetune_service(
    meta_session: AsyncSession = Depends(get_meta_session),
) -> FinetuneService:
    return FinetuneService(meta_session)


def get_model_service(
    meta_session: AsyncSession = Depends(get_meta_session),
) -> ModelService:
    return ModelService(meta_session)


# ==================== 知识库构建依赖 ====================

def get_build_runner():
    """返回知识库构建执行函数。

    使用独立 session（与请求生命周期解耦），由后台任务调用；
    对应 app/scripts/build_meta_knowledge.py 的服务化封装。
    """

    async def runner() -> dict:
        async with (
            dw_mysql_client_manager.sesion_factory() as dw_session,
            meta_mysql_client_manager.sesion_factory() as meta_session,
        ):
            service = MetaKnowledgeService(
                dw_mysql_repo=DWMysqlRepository(dw_session),
                meta_mysql_repo=MetaMysqlRepository(meta_session),
                value_es_repo=ValueESRepository(es_client_manager.client),
                column_qdrant_repo=ColumnQdrantRepository(qdrant_client_manager.client),
                metric_qdrant_repo=MetricQdrantRepository(qdrant_client_manager.client),
                embedding_client=embedding_client_manager.client,
            )
            await service.build(meta_config)
            await meta_session.commit()
            table_count = len(meta_config.tables)
            column_count = sum(len(t.columns) for t in meta_config.tables)
            sync_count = sum(1 for t in meta_config.tables for c in t.columns if c.sync)
            return {
                "tables": table_count,
                "columns": column_count,
                "metrics": len(meta_config.metrics),
                "values_indexed": sync_count,
            }

    return runner
