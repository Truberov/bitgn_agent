# Braintrust Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Langfuse with Braintrust-only tracing, keeping eval runs operational when Braintrust is not configured.

**Architecture:** The runner remains the observability boundary. It initializes Braintrust once per eval run, injects a per-task LangChain callback handler into agent invocation config, and logs BitGN benchmark scores after trial completion. The baseline agent keeps its current `config` seam and does not need structural changes.

**Tech Stack:** Python 3.13, uv, Braintrust Python SDK, braintrust-langchain, unittest, LangChain

---

### File Map

**Create:**
- `docs/superpowers/specs/2026-03-23-braintrust-tracing-design.md`
- `docs/superpowers/plans/2026-03-23-braintrust-tracing.md`

**Modify:**
- `pyproject.toml`
- `README.md`
- `eval/runner.py`
- `tests/test_runner_langfuse_optional.py`

### Task 1: Pin Braintrust dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`

- [ ] **Step 1: Resolve exact package versions**

Run: `pip index versions braintrust` and identify the latest exact version
Run: resolve the exact `braintrust-langchain` version from the package index as well
Expected: exact versions ready for pinning

- [ ] **Step 2: Write the dependency change**

Update `pyproject.toml` to remove Langfuse optional dependency handling and add pinned `braintrust` and `braintrust-langchain` dependencies.

- [ ] **Step 3: Update install docs**

Update `README.md` so install instructions mention Braintrust setup and `BRAINTRUST_API_KEY`.

- [ ] **Step 4: Verify dependency metadata is coherent**

Run: `uv run python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['dependencies'])"`
Expected: dependency list includes exact Braintrust packages

### Task 2: Write failing Braintrust runner tests

**Files:**
- Modify: `tests/test_runner_langfuse_optional.py`

- [ ] **Step 1: Write the failing test for disabled tracing**

Add a test proving `run_eval` still works when Braintrust imports fail or when `BRAINTRUST_API_KEY` is absent.

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `uv run python -m unittest tests.test_runner_langfuse_optional.RunnerLangfuseOptionalTests.test_run_eval_works_when_braintrust_is_unavailable`
Expected: FAIL because the test names and runner hooks still reference Langfuse

- [ ] **Step 3: Write the failing test for enabled tracing**

Add a test proving the runner passes a Braintrust callback handler in `config` and logs the benchmark score through the Braintrust logger path.

- [ ] **Step 4: Run the targeted test to verify it fails**

Run: `uv run python -m unittest tests.test_runner_langfuse_optional.RunnerLangfuseOptionalTests.test_run_eval_logs_score_when_braintrust_is_enabled`
Expected: FAIL because Braintrust integration is not implemented yet

### Task 3: Implement Braintrust-only runner integration

**Files:**
- Modify: `eval/runner.py`

- [ ] **Step 1: Write the minimal Braintrust initialization path**

Replace Langfuse helper functions with Braintrust helpers that:
- check `BRAINTRUST_API_KEY`
- import Braintrust modules best-effort
- initialize the logger with project `bitgn-agent`
- return the callback handler class or factory needed by the runner

- [ ] **Step 2: Run targeted tests**

Run: `uv run python -m unittest tests.test_runner_langfuse_optional.RunnerLangfuseOptionalTests.test_run_eval_works_when_braintrust_is_unavailable`
Expected: PASS

- [ ] **Step 3: Add score logging after `end_trial`**

Log task score data through Braintrust without making eval success depend on observability success.

- [ ] **Step 4: Run targeted tests**

Run: `uv run python -m unittest tests.test_runner_langfuse_optional.RunnerLangfuseOptionalTests.test_run_eval_logs_score_when_braintrust_is_enabled`
Expected: PASS

### Task 4: Clean up names and docs

**Files:**
- Modify: `tests/test_runner_langfuse_optional.py`
- Modify: `README.md`

- [ ] **Step 1: Rename test intent from Langfuse to Braintrust**

Keep the same coverage focus but update names, fake modules, and output assertions to match Braintrust-only behavior.

- [ ] **Step 2: Run the focused test module**

Run: `uv run python -m unittest tests.test_runner_langfuse_optional -v`
Expected: PASS

### Task 5: Final verification

**Files:**
- Modify: `uv.lock` if dependency resolution updates it

- [ ] **Step 1: Install pinned Braintrust packages**

Run: `uv add braintrust==<VERSION> braintrust-langchain==<VERSION>`
Expected: `pyproject.toml` and lockfile updated

- [ ] **Step 2: Run the full targeted verification**

Run: `uv run python -m unittest tests.test_runner_langfuse_optional -v`
Expected: PASS

- [ ] **Step 3: Run lint**

Run: `uv run ruff check .`
Expected: PASS

- [ ] **Step 4: Smoke-check imports**

Run: `uv run python -c "import eval.runner; print('runner import ok')"`
Expected: prints `runner import ok`
