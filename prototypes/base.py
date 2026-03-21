from abc import ABC, abstractmethod


class BaseAgent(ABC):
    @abstractmethod
    async def build(self) -> None:
        """Initialize the agent (create LLM, tools, etc.).
        Called once per task — each task gets a fresh agent instance.
        Model, prompt, tools are defined by the prototype itself."""
        ...

    @abstractmethod
    async def run(
        self,
        harness_url: str,
        instruction: str,
        config: dict | None = None,
    ) -> str | None:
        """Run the agent on a single task.
        config: LangChain invoke config (callbacks, metadata, run_name).
        Returns answer or None."""
        ...
