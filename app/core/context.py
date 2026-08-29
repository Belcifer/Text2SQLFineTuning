import asyncio
from _contextvars import ContextVar, Token
"""
- 理解context对象：
  - 每个协程都有自己的上下文对象，互不干扰，可以向其中独立设置和获取不同变量名的数据
    => 协程1：context对象：{"aa": 数据1， "bb": 数据2}
    => 协程2：context对象：{"aa": 数据3， "bb": 数据4}

- 理解ContextVar对象：
  -  我们可以通过ContextVar对象向当前协程的context对象中设置数据、获取数据和重置数据
  -  context_var = ContextVar("aa", default="") => 协程1和协程2的context对象：{"aa": "abc"}
         => 协程1：context_var.set("1111")  => 协程1的context对象：{"aa": "1111"}
         => 协程2：context_var.set("2222")  => 协程2的context对象：{"aa": "2222"}
         => 协程1：context_var.get()  => "1111"
         => 协程2：context_var.get()  => "2222"
         => 协程1：context_var.reset() => 协程1的context对象: {"aa": "abc"}
"""
class Test:
    pass

_req_context_var = ContextVar("req_id", default="")

# 保存请求id
def set_request_id(req_id: str)->Token:
    return _req_context_var.set(req_id)
# 获取请求id
def get_request_id():
    return _req_context_var.get()
# 重置请求id
def reset_request_id(token: Token):
    _req_context_var.reset(token)

if __name__ == '__main__':
    async def req1():
        print("1----req1", get_request_id())   # ""
        token = set_request_id("abc")
        await asyncio.sleep(1)
        print("2----req1", get_request_id()) # abc
        await asyncio.sleep(1)
        reset_request_id(token)
        print("3----req1", get_request_id())  # ""

    async def req2():
        print("1----req2", get_request_id())  # ""
        token = set_request_id("cba")
        await asyncio.sleep(1)
        print("2----req2", get_request_id())  # cba
        await asyncio.sleep(2)
        print("3----req2", get_request_id())  # cba

    async def test():
        await asyncio.gather(req1(), req2())

    asyncio.run(test())
