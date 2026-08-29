from qdrant_client import AsyncQdrantClient, models

from app.conf.app_config import app_config
from app.models.qdrant.column_info_qdrant import ColumnInfoQdrant

"""
操作qdrant数据库中的字段数据
"""
class ColumnQdrantRepository:
    collection_name = "data-agent-columns_collection"
    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def _ensure_collection(self):
        client = self.client
        collection_name = self.collection_name
        # 创建存储向量的容器  如果已存在先删除
        if await client.collection_exists(collection_name=collection_name):
            await client.delete_collection(collection_name=collection_name)
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=app_config.qdrant.embedding_size,  # 向量的维度
                distance=models.Distance.COSINE  # 余弦相似度匹配
            ),
        )

    # 批量保存多个字段信息向量
    async def insert_column_vectors(self, ids:list[str], payloads:list[ColumnInfoQdrant], vectors:list[list[float]]):

        # 创建集合
        await self._ensure_collection()

        # 需要进行分批批量插入
        batch_size = 30
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i + batch_size]
            batch_payloads = payloads[i:i + batch_size]
            batch_vectors = vectors[i:i + batch_size]
            # 批量插入多个向量
            await self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=batch_ids[i],
                        payload=batch_payloads[i],
                        vector=batch_vectors[i],  # 向量  list[float]
                    )
                    for i in range(len(batch_ids))
                ],
            )

    # 搜索
    async def search(self, keyword_vector:list[float])->list[ColumnInfoQdrant]:

        # 搜索
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=keyword_vector,
            # limit=4,
            score_threshold=0.6  # 只有相似度评分大于等于0.8的点才会被返回
        )

        # print(result.points)
        # for point in result.points:
        #     print(point.payload)
        # 返回列表数据
        return [ColumnInfoQdrant(**point.payload) for point in result.points]