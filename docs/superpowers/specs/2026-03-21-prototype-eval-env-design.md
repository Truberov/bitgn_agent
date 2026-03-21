# Prototype Versioning & Eval Environment

## Summary

Refactor the bitgn_agent project from a monolithic 2-file structure into a modular environment with:
- Named prototype directories, each containing a full agent implementation
- A common `BaseAgent` ABC defining the contract
- An async eval runner with configurable concurrency via `asyncio.Semaphore`
- YAML config files specifying prototype name, benchmark, and concurrency

## Current State

- `agent.py` (174 lines) — single agent with system prompt, 7 filesystem tools, LangChain + ChatOpenAI via OpenRouter
- `main.py` (118 lines) — synchronous benchmark runner, hardcoded model and benchmark `bitgn/sandbox`
- Langfuse for tracing, BitGN API for benchmarks
- All synchronous (`MiniRuntimeClientSync`, `HarnessServiceClientSync`)

## Target Structure

```
bitgn_agent/
├── prototypes/
│   ├── __init__.py              # load_prototype(name) → type[BaseAgent]
│   ├── base.py                  # ABC BaseAgent
│   └── baseline/
│       ├── __init__.py          # from .agent import Agent
│       └── agent.py             # class Agent(BaseAgent)
├── eval/
│   ├── __init__.py
│   └── runner.py                # async run_eval(config) → EvalResult
├── configs/
│   └── baseline_sandbox.yaml
├── main.py                      # CLI: python main.py configs/baseline_sandbox.yaml
├── pyproject.toml
└── .env
```

## Components

### BaseAgent (`prototypes/base.py`)

```python
from abc import ABC, abstractmethod

class BaseAgent(ABC):
    @abstractmethod
    async def build(self) -> None:
        """Initialize the agent (create LLM, tools, etc.).
        Called once per task — each task gets a fresh agent instance.
        Model, prompt, tools are defined by the prototype itself."""
        ...

    @abstractmethod
    async def run(self, harness_url: str, instruction: str, config: dict | None = None) -> str | None:
        """Run the agent on a single task.
        config: LangChain invoke config (callbacks, metadata, run_name).
        Returns answer or None."""
        ...
```

**Instance lifecycle**: One agent instance per task. `build()` creates the LLM client, tools, and LangChain agent graph. `run()` connects to the harness and executes. This avoids shared mutable state (VMHolder becomes instance state on `self`). LLM client objects are lightweight HTTP wrappers — no cost to creating per-task.

### Prototype Loader (`prototypes/__init__.py`)

```python
import importlib
from .base import BaseAgent

def load_prototype(name: str) -> type[BaseAgent]:
    module = importlib.import_module(f"prototypes.{name}")
    agent_cls = module.Agent
    assert issubclass(agent_cls, BaseAgent), f"{name}.Agent must subclass BaseAgent"
    return agent_cls
```

### Baseline Prototype (`prototypes/baseline/agent.py`)

Migrated from current `agent.py`:
- Wrapped in `class Agent(BaseAgent)`
- Model hardcoded inside the prototype (e.g. `MODEL_ID = "gpt-4.1-2025-04-14"`)
- `build_agent()` → `async build()` — creates ChatOpenAI, creates tools bound to `self`
- `run_agent()` → `async run(harness_url, instruction)` — creates `MiniRuntimeClient`, invokes agent
- Uses `MiniRuntimeClient` (async) instead of `MiniRuntimeClientSync`
- Uses `agent.ainvoke()` instead of `agent.invoke()`
- Tool functions become `async def` (LangChain `@tool` supports async)
- VMHolder becomes instance state on `self` instead of a separate class

### YAML Config (`configs/baseline_sandbox.yaml`)

```yaml
prototype: baseline
benchmark: bitgn/sandbox
concurrency: 5
# task_ids: [task_1, task_2]  # optional filter
```

### Eval Runner (`eval/runner.py`)

```python
import asyncio
from dataclasses import dataclass

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

async def run_eval(config: dict) -> EvalResult:
    """
    1. load_prototype(config["prototype"]) → AgentClass
    2. Connect to BitGN HarnessService (async: HarnessServiceClient)
    3. Fetch benchmark tasks via get_benchmark()
    4. Create Langfuse client, generate session_id for this eval run
    5. sem = asyncio.Semaphore(config["concurrency"])
    6. For each task, create coroutine run_task(task):
       a. async with sem
       b. agent = AgentClass(); await agent.build()
       c. Start playground: await harness.start_playground(...)
       d. Build langchain invoke config: {callbacks: [handler], metadata: {...}, run_name: ...}
       e. result = await agent.run(harness_url, instruction, config=invoke_config)
       f. End trial: await harness.end_trial(EndTrialRequest(trial_id=...))
       g. Extract score and score_detail from response
       h. Report score to Langfuse via langfuse.create_score(...)
       i. Return TaskResult(task_id, score, details)
       j. On exception: return TaskResult(task_id, score=0.0, details=str(error))
    7. results = await asyncio.gather(*coros)
    8. Return EvalResult
    """
```

### CLI Entry Point (`main.py`)

```python
import asyncio
import sys
import yaml
from dotenv import load_dotenv

from eval.runner import run_eval

async def main():
    load_dotenv()
    if len(sys.argv) < 2:
        print("Usage: python main.py <config.yaml>")
        sys.exit(1)
    config_path = sys.argv[1]
    with open(config_path) as f:
        config = yaml.safe_load(f)
    result = await run_eval(config)
    for r in result.results:
        print(f"  {r.task_id}: {r.score:.1%} — {r.details}")
    print(f"\nAverage: {result.avg_score:.1%}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Async Migration

| Component | Sync (current) | Async (target) |
|-----------|---------------|----------------|
| BitGN VM client | `MiniRuntimeClientSync` | `MiniRuntimeClient` |
| BitGN Harness | `HarnessServiceClientSync` | `HarnessServiceClient` |
| LangChain agent | `agent.invoke()` | `agent.ainvoke()` |
| Tool functions | sync `def` with `@tool` | `async def` with `@tool` |
| Tool helper | sync `_call_vm()` | `async _call_vm()` |
| Langfuse | `CallbackHandler` | `CallbackHandler` (works with async) |

## Concurrency Model

- `asyncio.Semaphore(config["concurrency"])` limits parallel task execution
- Each task gets its own agent instance (via `AgentClass()` + `build()`) to avoid shared state
- LLM client objects are lightweight HTTP wrappers — no cost to per-task creation
- Tasks run via `asyncio.gather(*[run_task(task) for task in tasks])`
- Each task coroutine catches its own exceptions and returns `TaskResult(score=0.0)` on failure

## Langfuse Integration

- One `session_id` per eval run (groups all task traces together)
- Langfuse info is passed to the agent via LangChain invoke config dict:
  ```python
  config = {}
  if langfuse_handler:
      config["callbacks"] = [langfuse_handler]
  if langfuse_metadata:
      config["metadata"] = langfuse_metadata
  if run_name:
      config["run_name"] = run_name
  ```
- `BaseAgent.run()` receives this config and passes it to `agent.ainvoke(input, config=config)`
- After `end_trial`, score is reported via `langfuse.create_score(trace_id, "task_score", score, data_type="NUMERIC")`

## BitGN API Usage

- Uses `start_playground` (preserves current behavior)
- `get_benchmark(benchmark_name)` to fetch tasks
- `end_trial(EndTrialRequest(trial_id=...))` to get score after agent completes

## New Prototype Workflow

1. `cp -r prototypes/baseline prototypes/my_new_agent`
2. Edit `prototypes/my_new_agent/agent.py`
3. Create `configs/my_new_agent_sandbox.yaml` with `prototype: my_new_agent`
4. `python main.py configs/my_new_agent_sandbox.yaml`

## Dependencies

User installs manually. Required new dependency:
- `pyyaml` — YAML config parsing

## Out of Scope

- Multiple prototypes in one YAML (matrix runs)
- Parallel prototype execution
- Result persistence/comparison between runs
- Web UI for results
