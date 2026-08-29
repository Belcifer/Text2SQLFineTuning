# 技术点1: 处理不同类型的请求
# 技术点2：获取不同类型的参数
# 技术点3：使用路由器
# 技术点4：SSE流式响应
# 技术点5：应用生命周期
# 技术点6：请求中间件
# 技术点7：依赖注入
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.params import Depends
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import StreamingResponse

from app.api.test.order_router import order_router
from app.api.test.product_router import product_router
from app.clients.es_client_manager import es_client_manager
from app.models.es.value_info_es import ValueInfoES
from app.repositories.es.value_es_repository import ValueESRepository


# 技术点5：生命周期
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("在应用启动时执行一次，一般执行初始化逻辑，如：初始化客户端")
    es_client_manager.init_client()
    yield
    print("在应用结束前执行一次，一般执行收尾逻辑，如：关闭客户端")
    await es_client_manager.close()
app = FastAPI(lifespan=lifespan)

# 技术点7：依赖注入

# 用来进行根据提交问题来搜索ES中对应的字段值列表
# 依赖注入： 需要的依赖对象通过声明的方式让框架自动注入进来  depedency inject  DI
# 产生依赖对象的函数， 每次处理请求都会执行
def get_value_es_repo():
    print("get_value_es_repo()")
    return ValueESRepository(es_client_manager.client)

@app.get("/di")
async def test_di(keyword: str, value_es_repo:ValueESRepository=Depends(get_value_es_repo)):
    print("处理对/di的GET请求")
    # 从ES中搜索
    value_infos:list[ValueInfoES] = await value_es_repo.search(keyword)
    return value_infos


# 技术点6：中间件
@app.middleware("http")
async def test_middleware(request: Request, call_next):  # 回调函数
    print("处理请求（路由函数执行）前执行， 生成请求id，并保存起来")
    response = await call_next(request)
    print("处理请求（路由函数执行）后执行")
    return response

# 技术点4：SSE流式响应
async def fake_stream():
    for i in range(10):
        yield f'data:{{"message": f"abc{i}"}} \n\n'
        await asyncio.sleep(1)

# 测试手动执行异步生成器函数
async def test_call_async_generator():
    async for chunk in fake_stream():    # astream
        print("----", chunk)

@app.get("/sse")
def test_sse():
    print("处理对/sse的get请求")
    return StreamingResponse(fake_stream(), media_type="text/event-stream")

# 技术点3：使用路由器
# 项目中有商品模块（5），订单模块（6）
app.include_router(product_router, prefix="/v1")
app.include_router(order_router, prefix="/v2")


# 技术点2：获取不同类型的参数
'''
- 3种携带文本参数的方式
  - query参数：请求路径？后面的参数，如：/xxx?sex=male&height=18
  - path参数：看似像路径，与路由路径占位对应的部分，如：路由路径：/xxx/{id}，请求：/xxx/2
  - body参数：请求体参数，一般是json格式，如：{"name": "tom", "age": 12}
- 路由函数接收3种不同的参数
  - 接收 body参数：BaseModel子类型的形参
  - 接收path参数：与路由路径中占位同名的形参
  - 接收query参数：其它形参
'''
class BodyParams(BaseModel):
    name: str
    age: int

@app.post("/params/{id}")
def test_params(body_params: BodyParams, id: int, sex:str, height: int):
    print("处理对/params的POST请求", body_params, id, sex, height)
    return {"id": id, "name": body_params.name, "age": body_params.age, "sex": sex, "height": height}


# 技术点1: 处理不同类型的请求
@app.get("/xxx")
def test_get():
    print("处理对/xxx的GET请求")
    return {"message": "GET请求的响应数据。。。"}

@app.post("/xxx")
def test_post():
    print("处理对/xxx的POST请求")
    return {"message": "POST请求的响应数据。。。"}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)

    # asyncio.run(test_call_async_generator())