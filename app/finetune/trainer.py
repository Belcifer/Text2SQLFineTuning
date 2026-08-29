"""微调训练任务编排（设计书第 6 章，API 文档 5 节）。

重型依赖（llamafactory-cli / peft / transformers）延迟导入：
- build_command() 为纯函数，可离线单测；
- run_job() 需要 GPU 训练环境，本仓库不内置该环境时抛出明确提示。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional

from app.conf.app_config import app_config


def build_command(job: dict, dataset_dir: str, output_dir: str) -> list[str]:
    """构造 LLaMA-Factory 训练命令（设计书 6.3 节）。

    job: {"base_model","method","hyperparams":{...}}
    """
    hp = job.get("hyperparams") or {}
    base_model = job["base_model"]
    method = job.get("method", "qlora")
    lora_rank = hp.get("lora_rank", 64)
    lora_alpha = hp.get("lora_alpha", 128)
    lr = hp.get("learning_rate", 2e-4)
    epochs = hp.get("epochs", 3)
    max_seq_len = hp.get("max_seq_len", 4096)
    batch_size = hp.get("batch_size", 128)
    per_device = hp.get("per_device_batch_size", 8)
    grad_accum = max(1, batch_size // (per_device or 8))

    cmd = [
        "llamafactory-cli", "train",
        "--model_name_or_path", base_model,
        "--dataset", "train.json",
        "--dataset_dir", dataset_dir,
        "--template", "qwen",
        "--finetuning_type", "lora",
        "--output_dir", output_dir,
        "--per_device_train_batch_size", str(per_device),
        "--gradient_accumulation_steps", str(grad_accum),
        "--learning_rate", str(lr),
        "--num_train_epochs", str(epochs),
        "--max_length", str(max_seq_len),
        "--lora_rank", str(lora_rank),
        "--lora_alpha", str(lora_alpha),
        "--lora_dropout", str(hp.get("lora_dropout", 0.05)),
    ]
    if method == "qlora":
        cmd += ["--quantization_bit", "4"]
    return cmd


def run_job(
    job: dict,
    sample_dir: str = "data/finetune",
    progress_cb: Optional[Callable[[float], None]] = None,
    cmd_builder: Callable = build_command,
) -> dict:
    """执行训练任务（阻塞式）。返回 {"adapter_path": ..., "checkpoint": ...}。

    依赖 llamafactory-cli（GPU 环境），未安装时抛出 RuntimeError。
    """
    from app.finetune.exporter import export_samples

    out_dir = Path(app_config.finetune.sample_dir) / "output" / job["name"]
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. 导出训练数据（job.datasets 在此处由调用方解析为样本列表后传入）
    samples = job.get("_samples", [])
    export_samples(samples, format_="llama_factory", output_dir=str(out_dir))

    # 2. 构造并执行命令
    cmd = cmd_builder(job, dataset_dir=str(out_dir), output_dir=str(out_dir / "checkpoint"))
    if progress_cb:
        progress_cb(0.05)

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as e:
        raise RuntimeError(
            "未找到 llamafactory-cli，请先在 GPU 训练环境安装："
            "pip install 'llamafactory[torch,bitsandbytes]'"
        ) from e

    if progress_cb:
        progress_cb(1.0)
    return {"adapter_path": str(out_dir / "checkpoint"), "checkpoint": 1}


if __name__ == "__main__":
    # 仅打印命令示例，不真正执行训练
    demo_job = {
        "name": "qwen2.5-coder-14b-lora-v1",
        "base_model": app_config.finetune.base_model,
        "method": "qlora",
        "hyperparams": dict(app_config.finetune.default_hyperparams),
    }
    print(" ".join(build_command(demo_job, "data/finetune", "output/demo")))
