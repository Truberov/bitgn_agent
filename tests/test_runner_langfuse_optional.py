import builtins
import contextlib
import importlib
import io
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class RunnerLangfuseOptionalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._saved_modules = {}
        for name in [
            "eval.runner",
            "bitgn",
            "bitgn.harness_connect",
            "bitgn.harness_pb2",
            "prototypes",
            "langfuse",
            "langfuse.langchain",
        ]:
            self._saved_modules[name] = sys.modules.pop(name, None)

        bitgn_pkg = types.ModuleType("bitgn")
        harness_connect = types.ModuleType("bitgn.harness_connect")
        harness_pb2 = types.ModuleType("bitgn.harness_pb2")
        prototypes = types.ModuleType("prototypes")

        class FakeHarnessServiceClient:
            def __init__(self, base_url: str) -> None:
                self.base_url = base_url

            async def status(self, _request):
                return "ok"

            async def get_benchmark(self, _request):
                return types.SimpleNamespace(
                    policy="EVAL_POLICY_OPEN",
                    benchmark_id="bench-1",
                    description="demo",
                    tasks=[
                        types.SimpleNamespace(
                            task_id="task-1",
                            preview="preview",
                            hint="hint",
                        )
                    ],
                )

            async def start_playground(self, _request):
                return types.SimpleNamespace(
                    trial_id="trial-1",
                    instruction="solve it",
                    harness_url="https://harness.local",
                )

            async def end_trial(self, _request):
                return types.SimpleNamespace(score=1.0, score_detail=["ok"])

        class FakeEvalPolicy:
            @staticmethod
            def Name(value):
                return value

        class FakeAgent:
            last_config = None

            async def run(self, harness_url, instruction, config):
                type(self).last_config = config

        harness_connect.HarnessServiceClient = FakeHarnessServiceClient
        harness_pb2.EndTrialRequest = lambda trial_id: types.SimpleNamespace(
            trial_id=trial_id
        )
        harness_pb2.GetBenchmarkRequest = lambda benchmark_id: types.SimpleNamespace(
            benchmark_id=benchmark_id
        )
        harness_pb2.StartPlaygroundRequest = (
            lambda benchmark_id, task_id: types.SimpleNamespace(
                benchmark_id=benchmark_id,
                task_id=task_id,
            )
        )
        harness_pb2.StatusRequest = lambda: types.SimpleNamespace()
        harness_pb2.EvalPolicy = FakeEvalPolicy
        prototypes.load_prototype = lambda _name: FakeAgent

        sys.modules["bitgn"] = bitgn_pkg
        sys.modules["bitgn.harness_connect"] = harness_connect
        sys.modules["bitgn.harness_pb2"] = harness_pb2
        sys.modules["prototypes"] = prototypes

        self.agent_class = FakeAgent

    def tearDown(self) -> None:
        for name in [
            "eval.runner",
            "bitgn",
            "bitgn.harness_connect",
            "bitgn.harness_pb2",
            "prototypes",
            "langfuse",
            "langfuse.langchain",
        ]:
            sys.modules.pop(name, None)

        for name, module in self._saved_modules.items():
            if module is not None:
                sys.modules[name] = module

    async def test_run_eval_works_when_langfuse_is_unavailable(self) -> None:
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "langfuse" or name.startswith("langfuse."):
                raise ImportError("langfuse is intentionally unavailable")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            runner = importlib.import_module("eval.runner")
            result = await runner.run_eval(
                {
                    "prototype": "baseline",
                    "benchmark": "bench-1",
                    "task_ids": ["task-1"],
                }
            )

        self.assertEqual(result.avg_score, 1.0)
        self.assertEqual(self.agent_class.last_config, {})

    async def test_run_eval_prints_trace_details_when_langfuse_is_enabled(self) -> None:
        runner = importlib.import_module("eval.runner")

        class FakeTraceApi:
            def get(self, trace_id):
                return types.SimpleNamespace(id=trace_id)

        class FakeLangfuse:
            def __init__(self) -> None:
                self.created_scores = []
                self.flushed = False
                self.api = types.SimpleNamespace(trace=FakeTraceApi())

            def create_score(self, **kwargs):
                self.created_scores.append(kwargs)

            def get_trace_url(self, *, trace_id: str) -> str:
                return f"https://langfuse.example/trace/{trace_id}"

            def flush(self) -> None:
                self.flushed = True

        class FakeCallbackHandler:
            def __init__(self) -> None:
                self.last_trace_id = "trace-123"

        fake_langfuse = FakeLangfuse()
        stdout = io.StringIO()

        with (
            patch.object(
                runner,
                "_init_langfuse",
                return_value=(fake_langfuse, FakeCallbackHandler, "session-123"),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            result = await runner.run_eval(
                {
                    "prototype": "baseline",
                    "benchmark": "bench-1",
                    "task_ids": ["task-1"],
                }
            )

        output = stdout.getvalue()
        self.assertEqual(result.avg_score, 1.0)
        self.assertIn("Langfuse tracing enabled", output)
        self.assertIn("Trace ID: trace-123", output)
        self.assertIn("Trace URL: https://langfuse.example/trace/trace-123", output)
        self.assertTrue(fake_langfuse.flushed)
        self.assertEqual(
            fake_langfuse.created_scores,
            [
                {
                    "trace_id": "trace-123",
                    "name": "task_score",
                    "value": 1.0,
                    "data_type": "NUMERIC",
                }
            ],
        )

    async def test_run_eval_warns_when_trace_is_not_queryable(self) -> None:
        runner = importlib.import_module("eval.runner")

        class FakeTraceApi:
            def get(self, trace_id):
                raise RuntimeError(f"trace {trace_id} is missing")

        class FakeLangfuse:
            def __init__(self) -> None:
                self.created_scores = []
                self.flushed = False
                self.api = types.SimpleNamespace(trace=FakeTraceApi())

            def create_score(self, **kwargs):
                self.created_scores.append(kwargs)

            def get_trace_url(self, *, trace_id: str) -> str:
                return f"https://langfuse.example/trace/{trace_id}"

            def flush(self) -> None:
                self.flushed = True

        class FakeCallbackHandler:
            def __init__(self) -> None:
                self.last_trace_id = "trace-missing"

        fake_langfuse = FakeLangfuse()
        stdout = io.StringIO()

        async def fake_sleep(_delay):
            return None

        with (
            patch.object(
                runner,
                "_init_langfuse",
                return_value=(fake_langfuse, FakeCallbackHandler, "session-123"),
            ),
            patch.object(runner, "_TRACE_READY_MAX_ATTEMPTS", 2),
            patch.object(runner, "_TRACE_READY_DELAY_SECONDS", 0),
            patch.object(runner.asyncio, "sleep", side_effect=fake_sleep),
            contextlib.redirect_stdout(stdout),
        ):
            await runner.run_eval(
                {
                    "prototype": "baseline",
                    "benchmark": "bench-1",
                    "task_ids": ["task-1"],
                }
            )

        output = stdout.getvalue()
        self.assertIn("Trace ID: trace-missing", output)
        self.assertIn("Trace not yet queryable in Langfuse", output)
        self.assertNotIn("Trace URL: https://langfuse.example/trace/trace-missing", output)


if __name__ == "__main__":
    unittest.main()
