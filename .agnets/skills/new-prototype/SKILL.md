---
name: new-prototype
description: Use when the user asks to create, add, or scaffold a new agent prototype. Guides through creating all required files (agent module, __init__, config YAML) based on the baseline pattern.
---

# New Prototype Scaffolding

This skill creates a new agent prototype for the bitgn_agent evaluation framework.

## Prerequisites

Before starting, read these reference files to understand the current patterns:

1. `prototypes/base.py` — BaseAgent abstract base class (the contract)
2. `prototypes/baseline/agent.py` — reference implementation
3. `prototypes/__init__.py` — dynamic prototype loader (expects `Agent` class)
4. `configs/baseline_sandbox.yaml` — config format example

## Step-by-Step Process

### 1. Gather Requirements

Ask the user (use AskUserQuestion):
- **Prototype name** — will become the directory name under `prototypes/` and the value in config YAML
- **LLM provider and model** — e.g. OpenAI via OpenRouter (`gpt-4.1`), Anthropic (`claude-sonnet-4-20250514`), or other
- **Custom system prompt** — or use a variation of the baseline prompt
- **Custom tools** — whether to include the standard VM tools or add/remove any

### 2. Create Directory Structure

```
prototypes/<name>/
├── __init__.py
└── agent.py
```

### 3. Create `prototypes/<name>/__init__.py`

Contents must re-export the Agent class:

```python
from .agent import Agent

__all__ = ["Agent"]
```

### 4. Create `prototypes/<name>/agent.py`

Scaffold based on `prototypes/baseline/agent.py`. The agent MUST:

- Import and subclass `BaseAgent` from `prototypes.base`
- Export a class named exactly `Agent` (the loader expects this)
- Implement `__init__(self)` — initialize LLM, create tools, build the agent graph
- Implement `async run(self, harness_url, instruction, config=None) -> str | None`
- In `run()`: create `MiniRuntimeClient(harness_url)`, invoke agent, return result

Key patterns from baseline to follow:
- Tools are created via `@tool` decorator from `langchain.tools`
- VM calls go through `MiniRuntimeClient` methods (outline, search, list, read, write, delete, answer)
- Protobuf request objects from `bitgn.vm.mini_pb2`
- `report_completion` tool is required — it submits the final answer via `AnswerRequest`
- Agent is created with `create_agent(llm, tools=..., system_prompt=...)`

Adapt for the chosen LLM provider:
- **OpenRouter**: `ChatOpenAI(model=MODEL_ID, base_url="https://openrouter.ai/api/v1")` — uses `OPENAI_API_KEY`
- **Anthropic direct**: `ChatAnthropic(model=MODEL_ID)` — uses `ANTHROPIC_API_KEY`
- **Other**: adjust LangChain chat model class and env vars accordingly

### 5. Create Config YAML

Create `configs/<name>_sandbox.yaml`:

```yaml
prototype: <name>
benchmark: bitgn/sandbox
concurrency: 5
# task_ids: [task_1, task_2]
```

### 6. Lint and Format

Run:
```bash
uv run ruff check prototypes/<name>/
uv run ruff format prototypes/<name>/
```

### 7. Verify

Run a quick smoke test:
```bash
uv run python main.py configs/<name>_sandbox.yaml
```

## Important Notes

- Each task gets a **fresh agent instance** — no shared state between tasks
- The `config` parameter passed to `run()` contains LangChain invoke config (callbacks for Langfuse, metadata, run_name) — pass it through to `agent.ainvoke()`
- The prototype loader (`prototypes/__init__.py`) dynamically imports `prototypes.<name>` and validates that `Agent` is a `BaseAgent` subclass
- Keep the same tool signatures as baseline unless there's a specific reason to change — the VM API is fixed
