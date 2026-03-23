# Braintrust Tracing Migration Design

## Goal

Replace the existing optional Langfuse observability path with Braintrust-only tracing while keeping eval runs functional when Braintrust is not configured.

## Context

The current tracing integration lives in `eval/runner.py`. The runner initializes Langfuse, passes a LangChain callback handler into each task invocation, and reports a benchmark score after `end_trial`. The baseline agent in `prototypes/baseline/agent.py` already accepts a LangChain `config` dict, so the tracing boundary is clean and does not require agent logic changes.

## Chosen Approach

Use Braintrust's LangChain callback integration at the same boundary where Langfuse is currently wired.

This is preferred over process-wide auto-instrumentation because the eval runner already has an explicit task invocation boundary. Keeping tracing setup in the runner preserves local control over per-task metadata and avoids broader runtime patching.

## Architecture

### Runner Integration

`eval/runner.py` will:

- initialize Braintrust once per eval run with `project="bitgn-agent"`
- treat Braintrust as optional at runtime and disable tracing cleanly when `BRAINTRUST_API_KEY` is unset or the SDK is unavailable
- create a Braintrust LangChain callback handler per task
- pass the handler through the existing `config` argument to `agent.run(...)`
- log benchmark score data to Braintrust after `end_trial`

### Agent Boundary

`prototypes/baseline/agent.py` will remain structurally unchanged. The existing `ainvoke(..., config=config or {})` call is the integration seam that allows Braintrust tracing to work without modifying VM tools or agent business logic.

### Dependencies

The project will stop advertising Langfuse as the observability dependency and instead depend on:

- `braintrust`
- `braintrust-langchain`

Versions will be pinned exactly when added.

## Runtime Behavior

### When Braintrust Is Disabled

If `BRAINTRUST_API_KEY` is missing, eval execution continues normally and prints `Braintrust tracing disabled`. No callback handler is passed to the agent and the invoke config remains empty.

### When Braintrust Is Enabled

If the Braintrust SDK is importable and `BRAINTRUST_API_KEY` is present:

- the runner prints `Braintrust tracing enabled`
- each task invocation includes a Braintrust LangChain callback handler
- the benchmark result is attached to Braintrust after the harness returns the final score

The CLI will not attempt to print trace IDs or trace URLs unless the SDK provides a stable, supported API for that exact path. This migration does not require trace-link output.

## Error Handling

- SDK import failures must not crash eval runs
- missing Braintrust credentials must not crash eval runs
- Braintrust logging failures after task completion should be best-effort and should not prevent score collection from BitGN

## Testing

The existing Langfuse-focused test module will be rewritten to cover Braintrust-only behavior:

- eval works when Braintrust is unavailable
- eval works when the API key is missing
- tracing-enabled runs pass a Braintrust callback handler to the agent
- benchmark scores are logged through the Braintrust integration path

## Documentation

`README.md` and project metadata will be updated to describe Braintrust installation and configuration instead of Langfuse.
