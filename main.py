import asyncio
import sys

import yaml
from dotenv import load_dotenv

from connectrpc.errors import ConnectError
from eval.runner import run_eval

CLI_RED = "\x1b[31m"
CLI_GREEN = "\x1b[32m"
CLI_CLR = "\x1b[0m"


async def main() -> None:
    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: python main.py <config.yaml>")
        sys.exit(1)

    config_path = sys.argv[1]
    with open(config_path) as f:
        config = yaml.safe_load(f)

    try:
        result = await run_eval(config)
    except ConnectError as e:
        print(f"{CLI_RED}{e.code}: {e.message}{CLI_CLR}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"{CLI_RED}Interrupted{CLI_CLR}")
        sys.exit(1)

    # Print summary
    print("\n" + "=" * 40)
    print("RESULTS:")
    for r in result.results:
        style = CLI_GREEN if r.score == 1 else CLI_RED
        print(f"  {r.task_id}: {style}{r.score:0.2f}{CLI_CLR}")

    print(f"\nFINAL: {result.avg_score * 100:0.2f}%")


if __name__ == "__main__":
    asyncio.run(main())
