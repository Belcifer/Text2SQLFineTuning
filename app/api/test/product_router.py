# 管理商品模块的所有路由的路由器
from fastapi import APIRouter

product_router = APIRouter()

# 通过路由器来注册多个路由
@product_router.get("/product/{id}")
def test_get(id: int):
    print("处理对商品模块/product的GET请求")
    return {"id": id, "name": "product AAAA"}