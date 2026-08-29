# 问数微调平台 API 文档

| 项 | 内容 |
|---|---|
| 文档版本 | v1.0 |
| Base URL | `http://{host}:{port}/api/v1` |
| 数据格式 | 请求/响应均为 `application/json`（SSE 接口为 `text/event-stream`） |
| 编码 | UTF-8 |
| 对应设计书 | `docs/微调优化设计书.md` |

> 本 API 在现有 `app/api/`（当前为空）之上补齐，作为 LangGraph Agent 与微调子系统的统一 HTTP 门面。设计原则与设计书一致：**主链路（问数）与旁路（微调）分离，且 API 层只做编排与透传，不侵入 `app/agent/` 内部实现**。

---

## 1. 通用约定

### 1.1 认证

私有化部署默认关闭；若开启，通过请求头认证：

```
Authorization: Bearer <api_key>
```

### 1.2 通用响应结构

非流式接口统一返回：

```json
{
  "code": 0,
  "message": "success",
  "data": { },
  "trace_id": "uuid"
}
```

- `code`：`0` 表示成功，非 `0` 为业务/系统错误。
- `trace_id`：链路追踪 ID，贯穿 Agent 与微调子系统。

### 1.3 错误码

| code | 含义 |
|---|---|
| 0 | 成功 |
| 40000 | 参数校验失败 |
| 40100 | 认证失败 / 无权限 |
| 40400 | 资源不存在 |
| 40900 | 状态冲突（如重复提交、状态机不允许） |
| 42200 | 业务校验失败（如 SQL 样本质量校验不通过） |
| 42900 | 频率限制 |
| 50000 | 系统内部错误 |

### 1.4 分页

列表接口统一入参：`page`（默认 1）、`page_size`（默认 20，上限 200）；统一返回：

```json
{ "items": [], "total": 0, "page": 1, "page_size": 20 }
```

---

## 2. 问数查询 API（核心）

### 2.1 发起问数（SSE 流式）

将自然语言问题送入 LangGraph Agent，以 SSE 流式回传各节点进度、澄清问题、最终 SQL 与执行结果。

```
POST /query
Content-Type: application/json
Accept: text/event-stream
```

**请求体**

```json
{
  "query": "华北地区销售总额",
  "thread_id": "optional-session-id",
  "dialect": "mysql",
  "db": "dw",
  "max_retry": 2
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| query | string | 是 | 用户自然语言问题 |
| thread_id | string | 否 | 会话 ID，用于跨轮澄清上下文与记忆 |
| dialect | string | 否 | 目标方言，默认 `mysql` |
| db | string | 否 | 目标业务库，默认 `dw` |
| max_retry | int | 否 | SQL 校验/纠错最大重试次数，默认 2 |

**SSE 事件协议**

对应 `app/agent/graph.py` 的 `stream_mode="custom"`（节点经 `runtime.stream_writer` 输出）与最终结果：

```
event: stage
data: {"node":"extract_keywords","message":"提取关键字","ts":1710000000000}

event: stage
data: {"node":"recall_column","message":"召回字段","recall_count":12,"ts":1710000000120}

... （recall_metric / recall_value / merge_retrieved_info / filter_metric / filter_table / add_extra_context / generate_sql / validate_sql / correct_sql / execute_sql 依次推送）

event: clarify
data: {"need_clarify":true,"questions":["您关心的指标是销售额还是销量？","请明确统计的时间范围。"],"thread_id":"optional-session-id"}

event: result
data: {"sql":"SELECT SUM(o.order_amount) ...;","columns":["销售总额"],"rows":[[123456789.0]],"row_count":1,"latency_ms":1340}

event: done
data: {"trace_id":"uuid","final_sql":"SELECT ...","execution_error":null}

event: error
data: {"code":50000,"message":"执行失败：...","trace_id":"uuid"}
```

| 事件 | 触发时机 | `data` 关键字段 |
|---|---|---|
| `stage` | 每个节点开始执行 | `node` 节点名、`message` 展示文案、`recall_count`（召回类节点可选） |
| `clarify` | 模型判定信息不足需澄清 | `need_clarify`、`questions`、`thread_id` |
| `result` | SQL 执行成功 | `sql`、`columns`、`rows`、`row_count`、`latency_ms` |
| `done` | 流程正常结束 | `trace_id`、`final_sql`、`execution_error` |
| `error` | 流程异常终止 | `code`、`message`、`trace_id` |

> 流结束后客户端收到 `done` 或 `error`，二者互斥。`clarify` 事件后流程挂起，等待用户补充后以同一 `thread_id` 再次发起（见 2.3）。

### 2.2 发起问数（非流式）

```
POST /query/sync
```

请求体同 2.1。响应为一次性结果：

```json
{
  "code": 0,
  "message": "success",
  "trace_id": "uuid",
  "data": {
    "sql": "SELECT SUM(o.order_amount) AS 销售总额 FROM fact_order o JOIN dim_region r ON o.region_id = r.region_id WHERE r.region_name = '华北';",
    "columns": ["销售总额"],
    "rows": [[123456789.0]],
    "row_count": 1,
    "need_clarify": false,
    "questions": [],
    "stages": ["提取关键字","召回字段", "...", "执行SQL"],
    "latency_ms": 1340
  }
}
```

### 2.3 澄清补充追问（复用会话）

```
POST /query/followup
```

**请求体**

```json
{
  "thread_id": "optional-session-id",
  "query": "销售额，最近三个月"
}
```

响应同 2.1（SSE）或 2.2（非流式，`Accept` 头区分）。服务端按 `thread_id` 恢复会话上下文，将补充信息并入原问题后重跑 Agent。

---

## 3. 知识库构建 API

对应 `app/scripts/build_meta_knowledge.py` 与 `app/services/meta_knowledge_service.py::build`。

### 3.1 触发知识库构建

```
POST /knowledge/build
```

**请求体（可选）**

```json
{
  "scope": "all",
  "reset": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| scope | string | 否 | `all`（默认，表+字段+值+指标）\| `tables` \| `metrics` \| `values` |
| reset | bool | 否 | 是否先清空 Qdrant/ES 集合与索引重建，默认 true |

**响应**

```json
{
  "code": 0,
  "message": "success",
  "data": { "build_id": "build_uuid", "status": "running" }
}
```

### 3.2 查询构建状态

```
GET /knowledge/build/{build_id}
```

**响应 `data`**

```json
{
  "build_id": "build_uuid",
  "status": "running | success | failed",
  "progress": 0.68,
  "detail": {
    "tables": 5,
    "columns": 24,
    "metrics": 2,
    "values_indexed": 1523,
    "error": null
  }
}
```

---

## 4. 微调数据管理 API

对应设计书第 5 章，样本统一 schema 见 `docs/微调优化设计书.md` 5.2 节。

### 4.1 数据集管理

#### 4.1.1 创建数据集

```
POST /finetune/datasets
```

```json
{
  "name": "订单域-v1",
  "description": "订单/商品/客户/地区域多任务样本",
  "dialect": "mysql"
}
```

**响应 `data`**：`{"dataset_id": "ds_uuid", "name": "订单域-v1", ...}`

#### 4.1.2 数据集列表 / 详情

```
GET  /finetune/datasets?page=1&page_size=20
GET  /finetune/datasets/{dataset_id}
```

详情 `data` 含统计：

```json
{
  "dataset_id": "ds_uuid",
  "name": "订单域-v1",
  "dialect": "mysql",
  "stats": {
    "total": 8000,
    "by_task": {"sql_generation": 3200, "sql_correction": 1200, "schema_linking": 1200, "value_standardization": 800, "metric_resolution": 800, "clarification": 800},
    "quality_passed": 7900,
    "quality_rejected": 100
  },
  "created_at": "2026-01-01T00:00:00Z"
}
```

### 4.2 样本管理

#### 4.2.1 批量导入样本

```
POST /finetune/datasets/{dataset_id}/samples
```

**请求体**（数组，元素即设计书 5.2 节统一样本 schema）：

```json
{
  "samples": [
    {
      "id": "sample_uuid",
      "task": "sql_generation",
      "source": "synthetic",
      "ability_tags": ["4.2.5"],
      "database": "mysql",
      "dialect": "mysql 8.0",
      "context": { "table_infos": [], "metric_infos": [], "value_infos": [], "date_info": "2025-01-01", "db_info": "MySQL 8.0，只读账号" },
      "instruction": "将用户问题转换为只读 SQL（严格使用上下文中的表与字段）。",
      "input": "华北地区销售总额",
      "output": "SELECT ...;",
      "meta": { "difficulty": "easy", "has_join": true, "has_clarify": false, "annotator": "auto" }
    }
  ]
}
```

**响应 `data`**

```json
{ "imported": 100, "rejected": 3, "reject_reasons": [{"id":"...","reason":"quality_check_failed"}] }
```

> 导入时服务端执行「可执行 + 只读 + 方言合法 + 字段均存在于上下文」四重校验，`meta.quality` 被置为 `passed`/`rejected`。

#### 4.2.2 分页查询样本

```
GET /finetune/datasets/{dataset_id}/samples?task=sql_generation&quality=passed&page=1&page_size=20
```

筛选参数（均可选）：`task`、`source`、`ability_tag`、`quality`、`difficulty`。

**响应 `data`**：见 1.4 分页结构，`items` 为样本数组。

#### 4.2.3 标注样本（人工纠偏）

```
PATCH /finetune/datasets/{dataset_id}/samples/{sample_id}
```

```json
{
  "output": "SELECT ...;",
  "meta": { "annotator": "human", "quality": "passed", "difficulty": "hard" }
}
```

### 4.3 运行时 Trace 上报（埋点采集）

对应设计书 5.6 节，由 Agent 旁路异步上报（不阻塞主链路）：

```
POST /finetune/traces
```

**请求体**（数组）：

```json
{
  "traces": [
    {
      "trace_id": "uuid",
      "thread_id": "session",
      "query": "华北地区销售总额",
      "final_sql": "SELECT ...;",
      "execution_error": null,
      "nodes": [
        {"node": "recall_column", "llm_output": ["销售额","地区"], "latency_ms": 120},
        {"node": "generate_sql", "llm_output": "SELECT ...;", "latency_ms": 800}
      ],
      "user_feedback": "thumbs_up"
    }
  ]
}
```

**响应 `data`**：`{"accepted": 1}`

### 4.4 导出训练格式

```
POST /finetune/datasets/{dataset_id}/export
```

**请求体**

```json
{
  "format": "alpaca | sharegpt | llama_factory",
  "task_filter": ["sql_generation", "sql_correction"],
  "split": { "train": 0.9, "eval": 0.1 },
  "seed": 42
}
```

**响应 `data`**

```json
{ "export_id": "exp_uuid", "files": ["train.json", "eval.json"], "sample_count": {"train": 7000, "eval": 800} }
```

---

## 5. 微调训练任务 API

对应设计书第 6 章。

### 5.1 提交训练任务

```
POST /finetune/jobs
```

**请求体**

```json
{
  "name": "qwen2.5-coder-14b-lora-v1",
  "base_model": "Qwen/Qwen2.5-Coder-14B-Instruct",
  "method": "qlora",
  "datasets": [{"dataset_id": "ds_uuid", "weight": 1.0}],
  "hyperparams": {
    "lora_rank": 64,
    "lora_alpha": 128,
    "lora_dropout": 0.05,
    "learning_rate": 2e-4,
    "batch_size": 128,
    "max_seq_len": 4096,
    "epochs": 3,
    "optimizer": "paged_adamw_8bit"
  },
  "resource": {"gpu_count": 1, "gpu_type": "A10"},
  "template": "qwen"
}
```

**响应 `data`**

```json
{ "job_id": "job_uuid", "status": "queued" }
```

### 5.2 任务列表 / 详情 / 进度

```
GET /finetune/jobs?status=running&page=1&page_size=20
GET /finetune/jobs/{job_id}
```

详情 `data`：

```json
{
  "job_id": "job_uuid",
  "name": "qwen2.5-coder-14b-lora-v1",
  "status": "queued | running | success | failed | cancelled",
  "progress": 0.42,
  "metrics": {"step": 210, "loss": 0.83, "eval_loss": 0.91, "lr": 1.2e-4},
  "output": {"adapter_path": "s3://models/.../adapter", "checkpoint": 500},
  "error": null,
  "created_at": "2026-01-01T00:00:00Z",
  "finished_at": null
}
```

### 5.3 取消任务

```
POST /finetune/jobs/{job_id}/cancel
```

仅 `queued`/`running` 状态可取消，成功返回 `{"code":0,"data":{"status":"cancelling"}}`。

### 5.4 训练指标曲线

```
GET /finetune/jobs/{job_id}/metrics
```

**响应 `data`**

```json
{ "loss": [{"step":0,"loss":2.1},{"step":100,"loss":1.2}], "eval_loss": [{"step":500,"loss":0.9}] }
```

---

## 6. 评估 API

对应设计书第 7 章。

### 6.1 提交评估任务

```
POST /finetune/evaluations
```

**请求体**

```json
{
  "name": "v1-离线评测",
  "model": "qwen2.5-coder-14b-lora-v1",
  "eval_set": {"dataset_id": "eval_ds_uuid"},
  "baseline_model": "deepseek-chat",
  "dimensions": ["ex", "schema_linking", "value_standardization", "metric_resolution", "clarification", "safety"]
}
```

**响应 `data`**：`{"evaluation_id": "eval_uuid", "status": "running"}`

### 6.2 查询评估结果

```
GET /finetune/evaluations/{evaluation_id}
```

**响应 `data`**

```json
{
  "evaluation_id": "eval_uuid",
  "status": "success",
  "model": "qwen2.5-coder-14b-lora-v1",
  "baseline": "deepseek-chat",
  "report": {
    "execution_accuracy": {"model": 0.86, "baseline": 0.72},
    "schema_linking_f1": {"model": 0.91, "baseline": 0.80},
    "value_mapping_accuracy": {"model": 0.94, "baseline": 0.85},
    "metric_caliber_accuracy": {"model": 0.88, "baseline": 0.70},
    "clarify_accuracy": {"model": 0.90, "baseline": 0.55},
    "safety_violation_rate": {"model": 0.0002, "baseline": 0.012}
  },
  "passed": true
}
```

---

## 7. 模型管理 API

对应设计书 8.1 节双后端切换。

### 7.1 模型列表

```
GET /models
```

**响应 `data.items`**

```json
[
  {"model_id":"m_base","name":"deepseek-chat","type":"api","status":"online","is_active":false},
  {"model_id":"m_v1","name":"qwen2.5-coder-14b-lora-v1","type":"finetuned","status":"deployed","is_active":true}
]
```

### 7.2 部署模型

```
POST /models/{model_id}/deploy
```

```json
{ "gpu_count": 1, "max_model_len": 4096 }
```

**响应 `data`**：`{"model_id":"m_v1","status":"deploying","endpoint":"http://vllm-host:8000/v1"}`

### 7.3 切换当前生效模型（灰度/回滚）

```
POST /models/{model_id}/activate
```

```json
{ "ratio": 0.1 }
```

| 字段 | 说明 |
|---|---|
| ratio | 流量比例 0~1，`1` 表示全量切换，`0.x` 表示按比例灰度 |

**响应 `data`**：`{"model_id":"m_v1","active_ratio":0.1,"previous_active":"m_base"}`

> 该接口最终写入 `conf/app_config.yaml` 的 `llm.backend/model_name/base_url` 并由 `llm.py` 热加载生效（详见设计书 8.1 节）。

---

## 附录：API 一览

| 分类 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 问数 | POST | `/query` | SSE 流式问数 |
| 问数 | POST | `/query/sync` | 非流式问数 |
| 问数 | POST | `/query/followup` | 澄清追问（复用会话） |
| 知识库 | POST | `/knowledge/build` | 触发知识库构建 |
| 知识库 | GET | `/knowledge/build/{build_id}` | 构建状态 |
| 数据 | POST | `/finetune/datasets` | 创建数据集 |
| 数据 | GET | `/finetune/datasets` | 数据集列表 |
| 数据 | GET | `/finetune/datasets/{id}` | 数据集详情 |
| 数据 | POST | `/finetune/datasets/{id}/samples` | 批量导入样本 |
| 数据 | GET | `/finetune/datasets/{id}/samples` | 分页查询样本 |
| 数据 | PATCH | `/finetune/datasets/{id}/samples/{sid}` | 标注样本 |
| 数据 | POST | `/finetune/datasets/{id}/export` | 导出训练格式 |
| 数据 | POST | `/finetune/traces` | 上报运行时 trace |
| 训练 | POST | `/finetune/jobs` | 提交训练任务 |
| 训练 | GET | `/finetune/jobs` | 训练任务列表 |
| 训练 | GET | `/finetune/jobs/{id}` | 训练任务详情/进度 |
| 训练 | POST | `/finetune/jobs/{id}/cancel` | 取消训练 |
| 训练 | GET | `/finetune/jobs/{id}/metrics` | 训练指标曲线 |
| 评估 | POST | `/finetune/evaluations` | 提交评估 |
| 评估 | GET | `/finetune/evaluations/{id}` | 评估结果 |
| 模型 | GET | `/models` | 模型列表 |
| 模型 | POST | `/models/{id}/deploy` | 部署模型 |
| 模型 | POST | `/models/{id}/activate` | 切换生效模型/灰度 |
