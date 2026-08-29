"""训练数据导出（设计书 5.2 节配套，API 文档 4.4 节）。

支持格式：
- alpaca        : {"instruction", "input", "output"}
- sharegpt      : {"conversations": [{"from":"human","value":...},{"from":"gpt","value":...}]}
- llama_factory : 与 alpaca 同构（LLaMA-Factory 原生支持）
"""
from __future__ import annotations

import json
import random
from pathlib import Path


def to_alpaca(sample: dict) -> dict:
    instruction = sample.get("instruction") or ""
    input_text = sample.get("input") or ""
    output_text = sample.get("output") or ""
    # 统一指令模板（设计书第 4 章）：指令 + 上下文 + 问题
    if input_text:
        instruction = f"{instruction}\n上下文：{json.dumps(sample.get('context', {}), ensure_ascii=False)}"
    return {"instruction": instruction, "input": input_text, "output": output_text}


def to_sharegpt(sample: dict) -> dict:
    instruction = sample.get("instruction") or ""
    input_text = sample.get("input") or ""
    user_value = input_text
    if instruction:
        user_value = f"{instruction}\n用户问题：{input_text}"
    return {
        "conversations": [
            {"from": "human", "value": user_value},
            {"from": "gpt", "value": sample.get("output") or ""},
        ]
    }


def export_samples(
    samples: list[dict],
    format_: str = "alpaca",
    output_dir: str = "data/finetune",
    train_ratio: float = 0.9,
    seed: int = 42,
) -> dict:
    """导出样本并切分 train/eval，返回 {"files": [...], "sample_count": {...}}。"""
    if format_ not in ("alpaca", "sharegpt", "llama_factory"):
        raise ValueError(f"不支持的导出格式: {format_!r}")

    converter = to_alpaca if format_ in ("alpaca", "llama_factory") else to_sharegpt

    # 稳定切分
    rng = random.Random(seed)
    items = list(samples)
    rng.shuffle(items)
    split_at = int(len(items) * train_ratio)
    train_items, eval_items = items[:split_at], items[split_at:]

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_file = out_dir / "train.json"
    eval_file = out_dir / "eval.json"

    def _write(path: Path, data: list):
        with path.open("w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(converter(item), ensure_ascii=False) + "\n")

    _write(train_file, train_items)
    _write(eval_file, eval_items)

    return {
        "export_id": f"exp-{seed}",
        "files": [str(train_file), str(eval_file)],
        "sample_count": {"train": len(train_items), "eval": len(eval_items)},
    }


if __name__ == "__main__":
    from app.conf.meta_config import meta_config
    from app.finetune.synthesizer import synthesize_all

    result = export_samples(synthesize_all(meta_config))
    print(result)
