import importlib

from .base import BaseAgent


def load_prototype(name: str) -> type[BaseAgent]:
    """Dynamically import prototypes.<name> and return its Agent class."""
    module = importlib.import_module(f"prototypes.{name}")
    agent_cls = module.Agent
    assert issubclass(agent_cls, BaseAgent), (
        f"{name}.Agent must subclass BaseAgent"
    )
    return agent_cls
