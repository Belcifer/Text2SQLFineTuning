"""合成/导出/校验冒烟检查（不依赖外部服务）。"""
from collections import Counter

from app.conf.meta_config import meta_config
from app.finetune.exporter import export_samples
from app.finetune.sample_schema import validate_sample
from app.finetune.synthesizer import synthesize_all


def main():
    samples = synthesize_all(meta_config)
    print("tasks:", dict(Counter(s["task"] for s in samples)))
    invalid = [s["id"] for s in samples if validate_sample(s)]
    print("invalid samples:", len(invalid))
    assert not invalid, "存在未通过质量校验的样本"
    result = export_samples(samples, format_="alpaca", output_dir="data/finetune")
    print("export:", result["sample_count"], result["files"])
    assert result["sample_count"]["train"] > 0
    print("synth OK")


if __name__ == "__main__":
    main()
