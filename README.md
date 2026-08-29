# Text2SQLFineTuning

问数项目：基于 **LangGraph 多节点 Agent + RAG（Qdrant / Elasticsearch）+ 大模型** 的自然语言转 SQL 系统，配套**私有化微调子系统**（QLoRA + vLLM）。

## 文档

- [微调优化设计书](docs/微调优化设计书.md) — 架构保留原则、六项能力映射、训练数据体系、QLoRA 方案、评估体系、推理接入
- [API 文档](docs/API文档.md) — 问数查询（SSE）、知识库构建、微调数据/训练/评估/模型管理接口
- [问数微调.md](问数微调.md) — 微调需求原文（4.2 节六项能力）

## 快速开始

```bash
# 1. 初始化 meta 库表结构（幂等，含主链路表 + 微调子系统表）
PYTHONPATH=. ./.venv/Scripts/python.exe scripts/create_tables.py

# 2. 构建知识库（元数据 → meta 库 + Qdrant 向量 + ES 全文索引）
PYTHONPATH=. ./.venv/Scripts/python.exe scripts/build_meta_knowledge.py

# 3. 启动服务（接口文档见 http://localhost:8000/docs）
uvicorn main:app --host 0.0.0.0 --port 8000

# 冒烟检查（需本地 MySQL）
PYTHONPATH=. ./.venv/Scripts/python.exe scripts/smoke_check.py   # 配置 + LLM 工厂
PYTHONPATH=. ./.venv/Scripts/python.exe scripts/synth_check.py   # 训练数据合成 + 导出
PYTHONPATH=. ./.venv/Scripts/python.exe scripts/api_smoke.py     # API 路由 + 读写链路
```

## 架构概览

```
app/
├── agent/        # LangGraph 编排：graph.py(12节点) + state/context + nodes/
├── api/          # FastAPI 层：routers/ + schemas/ + dependencies.py（主入口 main.py）
├── services/     # 业务层：query / meta_knowledge / finetune / model / knowledge
├── finetune/     # 微调旁路子系统：sample_schema / sample_repo / synthesizer /
│                 #   exporter / trainer / evaluator / data_collector
├── repositories/ # 持久层：mysql / es / qdrant
├── models/       # 数据模型：mysql(10表) / es / qdrant
├── clients/      # 客户端管理器：mysql / es / qdrant / embedding
├── conf/         # 配置模型（app_config / meta_config）
├── core/         # 日志、请求上下文、统一响应/异常
├── prompt/       # prompt 加载器
└── scripts/      # 建表 / 构建知识库 / 冒烟检查
```

## 关键配置（`conf/app_config.yaml`）

- `llm.backend`：`api`（官方 API）或 `finetuned`（vLLM OpenAI 兼容，微调模型）
- `llm.base_url`：`backend=finetuned` 时的 vLLM 服务地址
- `finetune.*`：trace 采集开关、样本目录、基座模型、默认训练超参
- 模型激活后写入 `conf/active_llm.yaml` 覆盖 `llm` 段，重启仍生效（删除该文件恢复默认）
