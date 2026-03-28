import asyncio
import sys

import yaml
from dotenv import load_dotenv

from eval.runner import run_eval

CLI_RED = "\x1B[31m"
CLI_GREEN = "\x1B[32m"
CLI_CLR = "\x1B[0m"


def main() -> None:
    load_dotenv()

    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/baseline.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    if len(sys.argv) > 2:
        config["task_ids"] = sys.argv[2:]

    result = asyncio.run(run_eval(config))

    if result.results:
        print()
        for r in result.results:
            style = CLI_GREEN if r.score == 1 else CLI_RED
            print(f"{r.task_id}: {style}{r.score:0.2f}{CLI_CLR}")

        print(f"FINAL: {result.avg_score * 100:0.2f}%")


if __name__ == "__main__":
    main()
