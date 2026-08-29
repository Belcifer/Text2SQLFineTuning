from pydantic import BaseModel, Field


# ==================== 数据集（API 文档 4.1） ====================

class DatasetCreateSchema(BaseModel):
    name: str = Field(..., description="数据集名称")
    description: str = Field("", description="数据集描述")
    dialect: str = Field("mysql", description="目标方言")


# ==================== 样本（API 文档 4.2） ====================

class SamplesImportSchema(BaseModel):
    samples: list[dict] = Field(..., description="样本数组（设计书 5.2 统一 schema）")


class SamplePatchSchema(BaseModel):
    output: str | None = Field(None, description="标准输出")
    meta: dict | None = Field(None, description="标注元信息，如 annotator/quality/difficulty")


# ==================== 导出（API 文档 4.4） ====================

class ExportSchema(BaseModel):
    format: str = Field("alpaca", description="alpaca | sharegpt | llama_factory")
    task_filter: list[str] | None = Field(None, description="仅导出指定子任务")
    split: dict = Field({"train": 0.9, "eval": 0.1}, description="train/eval 比例")
    seed: int = Field(42, description="随机种子")


# ==================== trace（API 文档 4.3） ====================

class TracesReportSchema(BaseModel):
    traces: list[dict] = Field(..., description="trace 数组（设计书 5.6）")


# ==================== 训练任务（API 文档 5） ====================

class JobCreateSchema(BaseModel):
    name: str = Field(..., description="任务名称")
    base_model: str = Field("", description="基座模型，缺省用配置的 finetune.base_model")
    method: str = Field("qlora", description="微调方法")
    datasets: list[dict] = Field(..., description="[{dataset_id, weight}]")
    hyperparams: dict | None = Field(None, description="训练超参，缺省用配置默认值")


# ==================== 评估（API 文档 6） ====================

class EvalCreateSchema(BaseModel):
    name: str = Field(..., description="评估名称")
    model: str = Field(..., description="被评估模型ID/名称")
    eval_set: dict = Field(..., description="评测集 {dataset_id}")
    baseline_model: str | None = Field(None, description="基线模型")
    dimensions: list[str] = Field(
        ["ex", "schema_linking", "value_standardization", "metric_resolution", "clarification", "safety"],
        description="评估维度",
    )
