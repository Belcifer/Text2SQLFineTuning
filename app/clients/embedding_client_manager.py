import asyncio
from typing import Optional

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.conf.app_config import EmbeddingConfig, app_config

"""
用来生成向量的客户端管理器模块
"""
class EmbeddingClientManager:
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.client: Optional[HuggingFaceEndpointEmbeddings] = None

    def init_client(self):
        self.client = HuggingFaceEndpointEmbeddings(model=f"http://{self.config.host}:{self.config.port}")

embedding_client_manager = EmbeddingClientManager(app_config.embedding)

if __name__ == '__main__':
    async def test():
        embedding_client_manager.init_client()

        # 生成一个文件向量
        result = await embedding_client_manager.client.aembed_query("hello")
        print(len(result),result)

        # 批量生成多个文本向量
        result = await embedding_client_manager.client.aembed_documents(["hello", "world"])
        print(result)
        print(len(result))


    asyncio.run(test())