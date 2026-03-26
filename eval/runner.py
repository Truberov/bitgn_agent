from dataclasses import dataclass
from prototypes import load_prototype


@dataclass
class TaskResult:
    task_id: str
    score: float
    details: str


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
    task_filter = config.get("task_ids", [])

    AgentClass = load_prototype(prototype_name)

    return EvalResult(results=[])
