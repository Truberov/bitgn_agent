from abc import ABC, abstractmethod


class BaseAgent(ABC):
    @abstractmethod
    async def run(
        self,
        harness_url: str,
        instruction: str,
        config: dict,
    ) -> str | None:
        """Run the agent on a single task.
        config: LangChain invoke config (callbacks, metadata, run_name).
        Returns answer or None."""
        ...
