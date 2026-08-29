import asyncio
import random
from typing import Optional

from qdrant_client import AsyncQdrantClient, models

from app.conf.app_config import QdrantConfig, app_config

"""
用来操作qdrant数据库的客户端管理器模块
"""
class QdrantClientManager:
    def __init__(self, config: QdrantConfig):
        self.config = config
        self.client:Optional[AsyncQdrantClient] = None
    def _get_url(self):
        return f"http://{self.config.host}:{self.config.port}"

    def init_client(self):
        self.client = AsyncQdrantClient(self._get_url())

    async def close(self):
        await self.client.close()

qdrant_client_manager = QdrantClientManager(app_config.qdrant)

if __name__ == '__main__':
    async def test():
        qdrant_client_manager.init_client()
        client = qdrant_client_manager.client
        collection_name = "my_collection"

        # 创建存储向量的容器   如果不存在才创建  项目运行时
        # if not await client.collection_exists(collection_name=collection_name):
        #     await client.create_collection(
        #         collection_name=collection_name,
        #         vectors_config=models.VectorParams(
        #             size=1024, #  向量的维度
        #             distance=models.Distance.COSINE  # 余弦相似度匹配
        #         ),
        #     )
        # 创建存储向量的容器  如果已存在先删除
        if await client.collection_exists(collection_name=collection_name):
            await client.delete_collection(collection_name=collection_name)
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=1024, #  向量的维度
                distance=models.Distance.COSINE  # 余弦相似度匹配
            ),
        )

        # 批量插入多个向量
        await client.upsert(
            collection_name=collection_name,
            points=[
                models.PointStruct(
                    id=i,
                    payload={
                        "color": "red" if i%2==0 else "blue",
                    },
                    vector=[random.random() for _ in range(1024)], # 向量  list[float]
                )
                for i in range(10)
            ],
        )

        # 搜索
        result = await client.query_points(
            collection_name=collection_name,
            query=[random.random() for _ in range(1024)],
            limit=4,
            query_filter=models.Filter( # 根据payload进行过滤
                must=[models.FieldCondition(key="color", match=models.MatchValue(value="red"))]
            ),
            score_threshold=0.6  # 只有相似度评分大于等于0.8的点才会被返回
        )

        print(result.points)
        for point in result.points:
            print(point.payload)

        await qdrant_client_manager.close()


    asyncio.run(test())

