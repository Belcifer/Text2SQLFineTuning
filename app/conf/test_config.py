from dataclasses import dataclass
from pathlib import Path

import yaml
from omegaconf import OmegaConf


def load_by_yaml():
    # 定义文件路径
    yaml_path = Path(__file__).parents[2] / "conf" / "test_config.yaml"
    # 打开文件流
    with open(yaml_path, encoding="utf-8") as file:
        yaml_data = yaml.safe_load(file)
        print(yaml_data)
        print(type(yaml_data))

        # 读取属性编码时没有提示，写错了也没有警告
        print(yaml_data['name'])


@dataclass
class PersonConfig:
    name: str
    age: int
    gender: str

def load_by_omegaconf():
    yaml_path = Path(__file__).parents[2] / "conf" / "test_config.yaml"
    yaml_data = OmegaConf.load(yaml_path)
    # print(yaml_data)
    # print(type(yaml_data))
    # print(yaml_data["name"], yaml_data.name)
    # 将yaml数据转换为指定类型的对象
    person_config: PersonConfig = OmegaConf.to_object(OmegaConf.merge(PersonConfig, yaml_data))
    print(person_config, type(person_config))
    print(person_config.name, person_config.gender)

if __name__ == '__main__':
    # load_by_yaml()
    load_by_omegaconf()