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
_TRACE_READY_MAX_ATTEMPTS = 30
_TRACE_READY_DELAY_SECONDS = 1


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


def _init_langfuse():
    """Best-effort Langfuse setup for environments where observability is installed."""
    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler

        langfuse = get_client()
        session_id = langfuse.create_trace_id()
        return langfuse, CallbackHandler, session_id
    except Exception:
        return None, None, None


def _get_trace_url(langfuse, trace_id: str) -> Optional[str]:
    try:
        return langfuse.get_trace_url(trace_id=trace_id)
    except Exception:
        return None


async def _trace_is_queryable(langfuse, trace_id: str) -> bool:
    for attempt in range(_TRACE_READY_MAX_ATTEMPTS):
        try:
            langfuse.api.trace.get(trace_id)
            return True
        except Exception:
            if attempt < _TRACE_READY_MAX_ATTEMPTS - 1:
                await asyncio.sleep(_TRACE_READY_DELAY_SECONDS)
    return False


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

    langfuse, langfuse_handler_cls, session_id = _init_langfuse()
    if langfuse and langfuse_handler_cls:
        print(f"Langfuse tracing enabled (session: {session_id})")
    else:
        print("Langfuse tracing disabled")

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

            langfuse_handler = (
                langfuse_handler_cls() if langfuse and langfuse_handler_cls else None
            )
            invoke_config = {}
            if langfuse_handler:
                invoke_config = {
                    "callbacks": [langfuse_handler],
                    "metadata": {
                        "langfuse_session_id": session_id,
                        "langfuse_tags": ["bitgn", "agent"],
                    },
                    "run_name": f"task-{t.task_id}",
                }

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

            if langfuse_handler and langfuse_handler.last_trace_id:
                trace_id = langfuse_handler.last_trace_id
                langfuse.create_score(
                    trace_id=trace_id,
                    name="task_score",
                    value=result.score,
                    data_type="NUMERIC",
                )
                langfuse.flush()
                print(f"Trace ID: {trace_id}")
                if await _trace_is_queryable(langfuse, trace_id):
                    trace_url = _get_trace_url(langfuse, trace_id)
                    if trace_url:
                        print(f"Trace URL: {trace_url}")
                else:
                    print(
                        f"{CLI_RED}Trace not yet queryable in Langfuse: {trace_id}{CLI_CLR}"
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

    if langfuse:
        langfuse.flush()

    return EvalResult(
        prototype=prototype_name,
        benchmark=benchmark_id,
        results=final_results,
    )
