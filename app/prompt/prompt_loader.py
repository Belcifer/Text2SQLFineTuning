from pathlib import Path


def load_prompt(name: str):
    prompt_path = Path(__file__).parents[2] / 'prompt' / f"{name}.prompt"
    return prompt_path.read_text(encoding='utf-8')

if __name__ == '__main__':
    print(load_prompt("correct_sql"))