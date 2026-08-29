from elasticsearch import AsyncElasticsearch

from app.models.es.value_info_es import ValueInfoES

"""
操作ES数据库中的字段值数据
"""
class ValueESRepository:
    index_name = "data-agent-values_index"
    mappings = {
        "dynamic": False,
        "properties": {
            "id": {"type": "keyword", "index": False},
            "value": {"type": "text", "analyzer": "ik_max_word", "index": True},
            "type": {"type": "keyword", "index": False},
            "column_id": {"type": "keyword", "index": False},
            "column_name": {"type": "keyword", "index": False},
            "table_id": {"type": "keyword", "index": False},
            "table_name": {"type": "keyword", "index": False},
        }
    }
    def __init__(self, client: AsyncElasticsearch):
        self.client = client

    async def _ensure_index(self):
        client = self.client
        index_name = self.index_name
        mappings = self.mappings

        # 创建索引  如果索引存在, 先删除  => 方便测试
        if await client.indices.exists(index=index_name):
            await client.indices.delete(index=index_name)
        await client.indices.create(
            index=index_name,
            mappings=mappings,
        )


    # 保存/插入多个文档(字段值信息列表)
    async def insert_value_infos(self, value_infos: list[ValueInfoES]):

        client = self.client
        index_name = self.index_name

        # 创建索引
        await self._ensure_index()

        # 分批处理
        batch_size = 50
        for i in range(0, len(value_infos), batch_size):
            # 得到当前批次的数据
            batch_value_infos = value_infos[i:i + batch_size]
            # 对当前批次数据批量插入多个文档
            operations = []
            for value_info in batch_value_infos:
                operations.append({
                    "index": {
                        "_index": index_name
                    }
                })
                operations.append(value_info)

            await client.bulk(
                operations=operations,
            )

    async def search(self, keyword: str)->list[ValueInfoES]:
        result = await self.client.search(
            index=self.index_name,
            query={
                "match": {
                    "value": keyword
                }
            },
        )
        # print(result)
        # print(result['hits']['hits'][0]['_source'])

        return [ValueInfoES(**item['_source']) for item in result['hits']['hits']]