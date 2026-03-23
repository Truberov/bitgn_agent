import asyncio
import os
import textwrap
from dataclasses import dataclass
from typing import Optional

from bitgn.harness_connect import HarnessServiceClient
from bitgn.harness_pb2 import (
    EndTrialRequest,
    EvalPolicy,
    GetBenchmarkRequest,
    StartPlaygroundRequest,
    StatusRequest,
)
from prototypes import load_prototype

CLI_RED = "\x1b[31m"
CLI_GREEN = "\x1b[32m"
CLI_CLR = "\x1b[0m"

BITGN_URL = os.getenv("BENCHMARK_HOST") or "https://api.bitgn.com"
_BRAINTRUST_PROJECT = "bitgn-agent"


@dataclass
class TaskResult:
    task_id: str
    score: float
    details: str


@dataclass
class EvalResult:
    prototype: str
    benchmark: str
    results: list[TaskResult]

    @property
    def avg_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)


def _init_braintrust():
    """Best-effort Braintrust setup for environments where observability is configured."""
    api_key = os.getenv("BRAINTRUST_API_KEY")
    if not api_key:
        return None

    try:
        from braintrust import init_logger
        from braintrust_langchain import BraintrustCallbackHandler, set_global_handler

        logger = init_logger(
            project=_BRAINTRUST_PROJECT,
            api_key=api_key,
        )
        set_global_handler(BraintrustCallbackHandler())
        return logger
    except Exception:
        return None


def _log_braintrust_score(
    logger,
    *,
    benchmark_id: str,
    task_id: str,
    instruction: str,
    harness_url: str,
    prototype_name: str,
    score: float,
    score_detail: list[str],
) -> Optional[str]:
    try:
        return logger.log(
            input={
                "benchmark_id": benchmark_id,
                "task_id": task_id,
                "instruction": instruction,
            },
            output={"score_detail": score_detail},
            scores={"task_score": score},
            metadata={
                "prototype": prototype_name,
                "harness_url": harness_url,
            },
            tags=["bitgn", "agent"],
        )
    except Exception:
        return None


async def run_eval(config: dict) -> EvalResult:
    """Run evaluation: load prototype, fetch benchmark tasks, run concurrently."""
    prototype_name = config["prototype"]
    benchmark_id = config["benchmark"]
    concurrency = config.get("concurrency", 1)
    task_filter = config.get("task_ids", [])

    AgentClass = load_prototype(prototype_name)

    client = HarnessServiceClient(BITGN_URL)
    print("Connecting to BitGN", await client.status(StatusRequest()))

    res = await client.get_benchmark(GetBenchmarkRequest(benchmark_id=benchmark_id))
    print(
        f"{EvalPolicy.Name(res.policy)} benchmark: {res.benchmark_id} "
        f"with {len(res.tasks)} tasks.\n{CLI_GREEN}{res.description}{CLI_CLR}"
    )

    tasks = res.tasks
    if task_filter:
        tasks = [t for t in tasks if t.task_id in task_filter]

    braintrust_logger = _init_braintrust()
    if braintrust_logger:
        print("Braintrust tracing enabled")
    else:
        print("Braintrust tracing disabled")

    sem = asyncio.Semaphore(concurrency)

    async def run_task(t) -> TaskResult:
        async with sem:
            print("=" * 40)
            print(f"Starting Task: {t.task_id}")

            trial = await client.start_playground(
                StartPlaygroundRequest(
                    benchmark_id=benchmark_id,
                    task_id=t.task_id,
                )
            )
            print("Task:", trial.instruction)

            invoke_config = {}
            if braintrust_logger:
                invoke_config = {"run_name": f"task-{t.task_id}"}

            try:
                agent = AgentClass()
                await agent.run(
                    trial.harness_url,
                    trial.instruction,
                    config=invoke_config,
                )
            except Exception as e:
                print(f"{CLI_RED}Agent error: {e}{CLI_CLR}")

            result = await client.end_trial(
                EndTrialRequest(trial_id=trial.trial_id)
            )

            if braintrust_logger:
                _log_braintrust_score(
                    braintrust_logger,
                    benchmark_id=benchmark_id,
                    task_id=t.task_id,
                    instruction=trial.instruction,
                    harness_url=trial.harness_url,
                    prototype_name=prototype_name,
                    score=result.score,
                    score_detail=list(result.score_detail),
                )

            score = result.score if result.score >= 0 else 0.0
            details = "\n".join(result.score_detail)

            style = CLI_GREEN if result.score == 1 else CLI_RED
            explain = textwrap.indent(details, "  ")
            print(f"\n{style}Score: {result.score:0.2f}\n{explain}\n{CLI_CLR}")

            return TaskResult(
                task_id=t.task_id,
                score=score,
                details=details,
            )

    coros = [run_task(t) for t in tasks]
    results = await asyncio.gather(*coros, return_exceptions=True)

    # Convert exceptions to failed TaskResults
    final_results = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"{CLI_RED}Task failed with exception: {r}{CLI_CLR}")
            final_results.append(
                TaskResult(task_id=tasks[i].task_id, score=0.0, details=str(r))
            )
        else:
            final_results.append(r)

    return EvalResult(
        prototype=prototype_name,
        benchmark=benchmark_id,
        results=final_results,
    )
