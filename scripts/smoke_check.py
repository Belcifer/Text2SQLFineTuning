"""冒烟检查：验证配置加载与 LLM 工厂（供 CI/本地快速验证）。"""
from app.conf.app_config import app_config
from app.agent.llm import get_llm


def main():
    assert app_config.llm.backend in ("api", "finetuned")
    assert app_config.finetune.base_model
    assert app_config.finetune.default_hyperparams["learning_rate"] > 0
    llm = get_llm()
    print("smoke OK:", app_config.llm.backend, type(llm).__name__)


if __name__ == "__main__":
    main()
