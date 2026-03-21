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
        """Initialize the agent (create LLM, tools, etc.)"""
        ...

    @abstractmethod
    async def run(self, harness_url: str, instruction: str) -> str | None:
        """Run the agent on a single task. Returns answer or None."""
        ...
```

### Prototype Loader (`prototypes/__init__.py`)

```python
import importlib
from .base import BaseAgent

def load_prototype(name: str) -> type[BaseAgent]:
    module = importlib.import_module(f"prototypes.{name}")
    return module.Agent
```

### Baseline Prototype (`prototypes/baseline/agent.py`)

Migrated from current `agent.py`:
- Wrapped in `class Agent(BaseAgent)`
- `build_agent()` → `async build()`
- `run_agent()` → `async run(harness_url, instruction)`
- Uses `MiniRuntimeClient` (async) instead of `MiniRuntimeClientSync`
- Uses `agent.ainvoke()` instead of `agent.invoke()`

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
        return sum(r.score for r in self.results) / len(self.results)

async def run_eval(config: dict) -> EvalResult:
    """
    1. load_prototype(config["prototype"]) → AgentClass
    2. agent = AgentClass(); await agent.build()
    3. Connect to BitGN HarnessService (async client)
    4. Fetch benchmark tasks
    5. sem = asyncio.Semaphore(config["concurrency"])
    6. Run tasks in parallel via asyncio.gather with semaphore
    7. Langfuse tracing per task
    8. Return EvalResult
    """
```

### CLI Entry Point (`main.py`)

```python
import asyncio
import sys
import yaml

from eval.runner import run_eval

async def main():
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
| Tool functions | sync `_call_vm()` | `async _call_vm()` |
| Langfuse | `CallbackHandler` | `CallbackHandler` (works with async) |

## Concurrency Model

- `asyncio.Semaphore(config["concurrency"])` limits parallel task execution
- Each task gets its own agent instance (via `AgentClass()` + `build()`) to avoid shared state
- Tasks run via `asyncio.gather(*[run_task_with_sem(task) for task in tasks])`

## New Prototype Workflow

1. `cp -r prototypes/baseline prototypes/my_new_agent`
2. Edit `prototypes/my_new_agent/agent.py`
3. Create `configs/my_new_agent_sandbox.yaml` with `prototype: my_new_agent`
4. `python main.py configs/my_new_agent_sandbox.yaml`

## Dependencies

Add to `pyproject.toml`:
- `pyyaml` — YAML config parsing

## Out of Scope

- Multiple prototypes in one YAML (matrix runs)
- Parallel prototype execution
- Result persistence/comparison between runs
- Web UI for results
