# CLAUDE.md

## Project Overview

**bitgn_agent** — async agent evaluation framework for BitGN benchmarks. Agents solve tasks in sandboxed VM environments and are scored via the BitGN harness API.

## Architecture

```
main.py                  — CLI entry point: `python main.py <config.yaml>`
configs/                 — YAML eval configs (prototype, benchmark, concurrency, task_ids)
eval/runner.py           — Async eval runner: loads prototype, fetches benchmark, runs tasks concurrently, reports scores to Langfuse
prototypes/base.py       — BaseAgent ABC (build + run)
prototypes/__init__.py   — Dynamic prototype loader (load_prototype)
prototypes/baseline/     — Reference agent implementation (LangChain + OpenAI via OpenRouter)
```

### Agent Lifecycle

1. `AgentClass()` — single instance created once per eval
2. `agent.build()` — init LLM, tools, graph (called once)
3. `agent.run(harness_url, instruction, config)` — reused for each task; per-task state (`_vm`) is reset inside `run()`
4. Harness scores the result via `end_trial`

### Key Dependencies

- **LangChain** — agent framework (`create_agent`, tools)
- **LangChain-OpenAI** — LLM provider (via OpenRouter)
- **Langfuse** — observability (traces, scores)
- **bitgn-api** — protobuf/connectRPC clients for harness and VM
- **Pydantic** — data validation
- **uv** — package manager

## Development

### Commands

```bash
uv run python main.py configs/baseline_sandbox.yaml   # Run eval
uv run ruff check .                                    # Lint
uv run ruff format .                                   # Format
```

### Adding a New Prototype

1. Create `prototypes/<name>/agent.py`
2. Implement `Agent(BaseAgent)` with `build()` and `run()`
3. Create a config YAML referencing the prototype name
4. Run with `python main.py configs/<your_config>.yaml`

## Conventions

- Python 3.13+, async/await throughout
- Formatter/linter: **ruff**
- Package manager: **uv**
- All agent prototypes subclass `BaseAgent` from `prototypes/base.py`
- VM interaction via protobuf/connectRPC (`MiniRuntimeClient`)
- Environment variables loaded from `.env` via `python-dotenv`
- Required env vars: `OPENAI_API_KEY` (for OpenRouter), `BENCHMARK_HOST` (optional, defaults to https://api.bitgn.com)