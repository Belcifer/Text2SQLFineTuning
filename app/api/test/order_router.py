# 管理订单模块的所有路由的路由器
from fastapi import APIRouter

order_router = APIRouter()

# 通过路由器来注册多个路由
@order_router.get("/order/{id}")
def test_get(id: int):
    print("处理对订单模块/order的GET请求")
    return {"id": id, "name": "order BBBB"}