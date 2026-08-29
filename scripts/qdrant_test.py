"""知识库构建 + 问数链路测试（需 Qdrant/ES/Embedding/MySQL/LLM 外部服务）。

流程：临时将 conf/app_config.yaml 的 qdrant.port 指向临时容器端口(10000)，
      启动真实 uvicorn，用 httpx 长超时调用；finally 停止服务并还原 yaml。
用法：PYTHONPATH=. ./.venv/Scripts/python.exe scripts/qdrant_test.py
"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml

CONF_PATH = Path(__file__).parents[1] / "conf" / "app_config.yaml"
QDRANT_PORT = 10000
UVICORN_PORT = 8011
BASE = f"http://127.0.0.1:{UVICORN_PORT}"

PASS, FAIL = 0, 0
results: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        results.append(f"[PASS] {name}")
    else:
        FAIL += 1
        results.append(f"[FAIL] {name} {detail}")


def _patch_yaml():
    with CONF_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    orig = data["qdrant"]["port"]
    data["qdrant"]["port"] = QDRANT_PORT
    with CONF_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return orig


def _restore_yaml(orig: int):
    with CONF_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["qdrant"]["port"] = orig
    with CONF_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


async def main():
    orig_port = _patch_yaml()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
         "--port", str(UVICORN_PORT)],
        cwd=str(Path(__file__).parents[1]),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # 等待服务就绪
        async with httpx.AsyncClient(timeout=10) as hc:
            for _ in range(40):
                try:
                    r = await hc.get(f"{BASE}/health")
                    if r.status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.5)

        async with httpx.AsyncClient(timeout=180) as client:
            # ============ 1. 知识库构建 ============
            r = await client.post(f"{BASE}/api/v1/knowledge/build", json={"scope": "all", "reset": True})
            check("POST 触发知识库构建", r.status_code == 200 and r.json()["code"] == 0, r.text[:200])
            build_id = r.json()["data"]["build_id"]

            status, detail = "running", {}
            for _ in range(150):
                r = await client.get(f"{BASE}/api/v1/knowledge/build/{build_id}")
                status = r.json()["data"]["status"]
                detail = r.json()["data"]["detail"]
                if status in ("success", "failed"):
                    break
                await asyncio.sleep(1.0)
            check("知识库构建成功", status == "success", f"status={status} detail={detail}")
            if status == "success":
                check("构建统计非空", detail.get("tables", 0) >= 5 and detail.get("metrics", 0) >= 2, str(detail))

            # ============ 2. 问数链路 ============
            if status == "success":
                r = await client.post(f"{BASE}/api/v1/query/sync", json={"query": "华北地区销售总额"})
                body = r.json()
                check("POST /query/sync 返回", r.status_code == 200 and body["code"] == 0, r.text[:300])
                data = body.get("data", {})
                if body["code"] == 0:
                    check("生成SQL非空", bool(data.get("sql")), str(data)[:200])
                    check("链路阶段完整", "生成SQL" in data.get("stages", []) and "执行SQL" in data.get("stages", []), str(data.get("stages")))

                r = await client.post(f"{BASE}/api/v1/query", json={"query": "2025年各地区平均销售额"})
                text = r.text
                check("POST /query SSE 有事件输出",
                      r.status_code == 200 and "event: stage" in text and ("event: result" in text or "event: error" in text),
                      text[:300])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        _restore_yaml(orig_port)

    print("\n".join(results))
    print(f"\n===== PASS {PASS} / FAIL {FAIL} =====")


if __name__ == "__main__":
    asyncio.run(main())
