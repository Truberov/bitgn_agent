import builtins
import contextlib
import importlib
import io
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class RunnerBraintrustOptionalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._saved_modules = {}
        for name in [
            "eval.runner",
            "bitgn",
            "bitgn.harness_connect",
            "bitgn.harness_pb2",
            "prototypes",
            "braintrust",
            "braintrust_langchain",
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
            "braintrust",
            "braintrust_langchain",
        ]:
            sys.modules.pop(name, None)

        for name, module in self._saved_modules.items():
            if module is not None:
                sys.modules[name] = module

    async def test_run_eval_works_when_braintrust_is_unavailable(self) -> None:
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "braintrust" or name.startswith("braintrust."):
                raise ImportError("braintrust is intentionally unavailable")
            if name == "braintrust_langchain" or name.startswith(
                "braintrust_langchain."
            ):
                raise ImportError("braintrust_langchain is intentionally unavailable")
            return original_import(name, globals, locals, fromlist, level)

        with (
            patch("builtins.__import__", side_effect=fake_import),
            patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop("BRAINTRUST_API_KEY", None)
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

    async def test_run_eval_logs_score_when_braintrust_is_enabled(self) -> None:
        runner = importlib.import_module("eval.runner")

        class FakeLogger:
            def __init__(self) -> None:
                self.logged_rows = []

            def log(self, **kwargs) -> str:
                self.logged_rows.append(kwargs)
                return "row-123"

        class FakeCallbackHandler:
            pass

        fake_logger = FakeLogger()
        stdout = io.StringIO()

        with (
            patch.dict(os.environ, {"BRAINTRUST_API_KEY": "test-key"}, clear=False),
            patch.object(
                runner,
                "_init_braintrust",
                return_value=fake_logger,
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
        self.assertIn("Braintrust tracing enabled", output)
        self.assertEqual(self.agent_class.last_config, {"run_name": "task-task-1"})
        self.assertEqual(
            fake_logger.logged_rows,
            [
                {
                    "input": {
                        "benchmark_id": "bench-1",
                        "task_id": "task-1",
                        "instruction": "solve it",
                    },
                    "output": {"score_detail": ["ok"]},
                    "scores": {"task_score": 1.0},
                    "metadata": {
                        "prototype": "baseline",
                        "harness_url": "https://harness.local",
                    },
                    "tags": ["bitgn", "agent"],
                }
            ],
        )

    async def test_init_braintrust_registers_global_handler(self) -> None:
        runner = importlib.import_module("eval.runner")

        class FakeLogger:
            pass

        fake_logger = FakeLogger()
        calls = {}

        braintrust = types.ModuleType("braintrust")

        def fake_init_logger(**kwargs):
            calls["init"] = kwargs
            return fake_logger

        braintrust.init_logger = fake_init_logger

        braintrust_langchain = types.ModuleType("braintrust_langchain")

        class FakeCallbackHandler:
            pass

        def fake_set_global_handler(handler):
            calls["handler"] = handler

        braintrust_langchain.BraintrustCallbackHandler = FakeCallbackHandler
        braintrust_langchain.set_global_handler = fake_set_global_handler

        sys.modules["braintrust"] = braintrust
        sys.modules["braintrust_langchain"] = braintrust_langchain

        with patch.dict(os.environ, {"BRAINTRUST_API_KEY": "test-key"}, clear=False):
            logger = runner._init_braintrust()

        self.assertIs(logger, fake_logger)
        self.assertEqual(
            calls["init"],
            {
                "project": "bitgn-agent",
                "api_key": "test-key",
            },
        )
        self.assertIsInstance(calls["handler"], FakeCallbackHandler)


if __name__ == "__main__":
    unittest.main()
