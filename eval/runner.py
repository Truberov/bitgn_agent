import asyncio
import os
import textwrap
import uuid
from dataclasses import dataclass

from langsmith import Client as LangSmithClient

from bitgn.harness_connect import HarnessServiceClient
from bitgn.harness_pb2 import (
    EndTrialRequest,
    EvalPolicy,
    GetBenchmarkRequest,
    StartPlaygroundRequest,
    StatusRequest,
)

from prototypes import load_prototype


CLI_RED = "\x1B[31m"
CLI_GREEN = "\x1B[32m"
CLI_CLR = "\x1B[0m"
CLI_BLUE = "\x1B[34m"
CLI_YELLOW = "\x1B[33m"


@dataclass
class TaskResult:
    task_id: str
    score: float
    details: str
    run_id: str | None = None


@dataclass
class EvalResult:
    results: list[TaskResult]

    @property
    def avg_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)


async def run_eval(config: dict) -> EvalResult:
    """Run evaluation: load prototype, fetch benchmark tasks, run concurrently."""
    prototype_name = config["prototype"]
    benchmark_id = config["benchmark"]
    concurrency = config.get("concurrency", 1)
    task_filter = set(config.get("task_ids", []))

    agent_config = {
        "model": config.get("model", os.environ.get("MODEL_ID", "gpt-4.1-2025-04-14")),
        "thread_id": str(uuid.uuid4()),
    }

    ls_client = LangSmithClient()
    AgentClass = load_prototype(prototype_name)

    bitgn_url = os.environ.get("BENCHMARK_HOST", "https://api.bitgn.com")
    harness = HarnessServiceClient(bitgn_url)

    status = await harness.status(StatusRequest())
    print(f"Connected to BitGN {status}")

    bench = await harness.get_benchmark(
        GetBenchmarkRequest(benchmark_id=benchmark_id)
    )
    print(
        f"{EvalPolicy.Name(bench.policy)} benchmark: {bench.benchmark_id} "
        f"with {len(bench.tasks)} tasks.\n{CLI_GREEN}{bench.description}{CLI_CLR}"
    )

    tasks = [t for t in bench.tasks if not task_filter or t.task_id in task_filter]

    sem = asyncio.Semaphore(concurrency)

    async def run_task(task) -> TaskResult:
        async with sem:
            print(f"{'=' * 30} Starting task: {task.task_id} {'=' * 30}")

            trial = await harness.start_playground(
                StartPlaygroundRequest(
                    benchmark_id=benchmark_id,
                    task_id=task.task_id,
                )
            )
            print(f"{CLI_BLUE}{trial.instruction}{CLI_CLR}\n{'-' * 80}")

            task_config = {**agent_config, "run_name": task.task_id}

            agent = AgentClass()
            try:
                await agent.run(trial.harness_url, trial.instruction, task_config)
            except Exception as exc:
                print(f"{CLI_RED}Agent error: {exc}{CLI_CLR}")

            result = await harness.end_trial(
                EndTrialRequest(trial_id=trial.trial_id)
            )

            score = result.score if result.score >= 0 else 0.0
            details = "\n".join(result.score_detail)
            style = CLI_GREEN if result.score == 1 else CLI_RED
            print(
                f"\n{style}Score: {result.score:0.2f}\n"
                f"{textwrap.indent(details, '  ')}\n{CLI_CLR}"
            )

            run_id = getattr(agent, "last_run_id", None)
            if run_id:
                try:
                    ls_client.create_feedback(
                        run_id=run_id,
                        key="score",
                        score=score,
                        comment=details,
                    )
                except Exception as exc:
                    print(f"{CLI_YELLOW}LangSmith feedback error: {exc}{CLI_CLR}")

            return TaskResult(task.task_id, score, details, run_id=run_id)

    raw_results = await asyncio.gather(
        *[run_task(t) for t in tasks], return_exceptions=True
    )

    task_results: list[TaskResult] = []
    for i, r in enumerate(raw_results):
        if isinstance(r, BaseException):
            print(f"{CLI_RED}Task {tasks[i].task_id} failed: {r}{CLI_CLR}")
            task_results.append(TaskResult(tasks[i].task_id, 0.0, str(r)))
        else:
            task_results.append(r)

    return EvalResult(results=task_results)
