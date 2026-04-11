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
    StartRunRequest,
    StartTrialRequest,
    SubmitRunRequest,
    StatusRequest,
)

from prototypes import load_prototype
from eval.run_logger import (
    generate_run_id,
    create_run_dir,
    format_task_log,
    format_error_log,
    write_task_log,
    write_run_summary,
)


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

    run_id = generate_run_id()
    run_dir = create_run_dir(run_id)
    print(f"Run logs: {run_dir}")

    ls_client = LangSmithClient()
    AgentClass = load_prototype(prototype_name)

    bitgn_url = os.environ.get("BENCHMARK_HOST", "https://api.bitgn.com")
    bitgn_key = os.environ.get("BITGN_API_KEY")
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

    run = await harness.start_run(
        StartRunRequest(
            name="Base react agent",
            benchmark_id=benchmark_id,
            api_key=bitgn_key or "",
        )
    )

    sem = asyncio.Semaphore(concurrency)

    async def run_task(trial_id: str) -> TaskResult | None:
        async with sem:
            trial = await harness.start_trial(
                StartTrialRequest(trial_id=trial_id)
            )

            if task_filter and trial.task_id not in task_filter:
                return None

            print(f"{'=' * 30} Starting task: {trial.task_id} {'=' * 30}")
            print(f"{CLI_BLUE}{trial.instruction}{CLI_CLR}\n{'-' * 80}")

            task_config = {**agent_config, "run_name": trial.task_id}

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

            # Write task log
            messages = getattr(agent, "last_messages", None)
            if messages:
                log_content = format_task_log(
                    task_id=trial.task_id,
                    instruction=trial.instruction,
                    messages=messages,
                    score=score,
                    score_details=details,
                )
            else:
                log_content = format_error_log(
                    task_id=trial.task_id,
                    instruction=trial.instruction,
                    error="No messages captured (agent may have failed before execution)",
                    score=score,
                    score_details=details,
                )
            write_task_log(run_dir, trial.task_id, log_content)

            agent_run_id = getattr(agent, "last_run_id", None)
            if agent_run_id:
                try:
                    ls_client.create_feedback(
                        run_id=agent_run_id,
                        key="score",
                        score=score,
                        comment=details,
                    )
                except Exception as exc:
                    print(f"{CLI_YELLOW}LangSmith feedback error: {exc}{CLI_CLR}")

            return TaskResult(trial.task_id, score, details, run_id=agent_run_id)

    try:
        raw_results = await asyncio.gather(
            *[run_task(tid) for tid in run.trial_ids], return_exceptions=True
        )
    finally:
        await harness.submit_run(SubmitRunRequest(run_id=run.run_id, force=True))

    task_results: list[TaskResult] = []
    for i, r in enumerate(raw_results):
        if isinstance(r, BaseException):
            print(f"{CLI_RED}Trial {run.trial_ids[i]} failed: {r}{CLI_CLR}")
            task_results.append(TaskResult(run.trial_ids[i], 0.0, str(r)))
        elif r is not None:
            task_results.append(r)

    write_run_summary(run_dir, task_results, config)

    return EvalResult(results=task_results)
