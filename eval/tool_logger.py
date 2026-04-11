import json
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

CLI_CYAN = "\x1B[36m"
CLI_DIM = "\x1B[2m"
CLI_GREEN = "\x1B[32m"
CLI_RED = "\x1B[31m"
CLI_CLR = "\x1B[0m"

_CONSOLE_ARG_LIMIT = 120


@dataclass
class ToolEvent:
    run_id: str
    parent_run_id: str | None
    tool_name: str
    args: dict
    start_time: float
    end_time: float | None = None
    output: str | None = None
    error: str | None = None
    status: Literal["running", "ok", "error"] = "running"
    depth: int = 0
    step: int = 0


class ToolCallLogger(AsyncCallbackHandler):
    """Collects tool call events for realtime console output and file logging."""

    def __init__(self, task_id: str, console: bool = True) -> None:
        super().__init__()
        self.task_id = task_id
        self.console = console
        self.events: list[ToolEvent] = []
        self._by_run_id: dict[str, ToolEvent] = {}
        self._step_counter = 0
        # Maps chain run_id -> depth (for tracking sub-agent chain nesting)
        self._chain_depth: dict[str, int] = {}

    def _get_depth(self, parent_run_id: str | None) -> int:
        """Depth 0 = top-level tool. Depth > 0 = nested inside a sub-agent."""
        if parent_run_id is None:
            return 0
        p = str(parent_run_id)
        # Parent is a known tool → we're nested inside it
        if p in self._by_run_id:
            return self._by_run_id[p].depth + 1
        # Parent is a chain we've seen → inherit its depth
        if p in self._chain_depth:
            return self._chain_depth[p]
        # Unknown parent (main chain) → top level
        return 0

    def _indent(self, depth: int) -> str:
        return "  " * depth

    def _format_args_console(self, args: dict) -> str:
        parts = []
        for k, v in args.items():
            s = json.dumps(v, ensure_ascii=False)
            if len(s) > _CONSOLE_ARG_LIMIT:
                s = s[:_CONSOLE_ARG_LIMIT] + "..."
            parts.append(f"{k}={s}")
        return ", ".join(parts)

    def _extract_output(self, output: Any) -> str:
        """Extract string content from tool output (may be ToolMessage or plain str)."""
        if hasattr(output, "content"):
            return str(output.content)
        return str(output)

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Track chain hierarchy so we can detect sub-agent nesting."""
        if parent_run_id is None:
            return
        p = str(parent_run_id)
        # If parent is a tool event, this chain runs inside that tool (sub-agent chain)
        if p in self._by_run_id:
            self._chain_depth[str(run_id)] = self._by_run_id[p].depth + 1
        # If parent is a known chain, inherit its depth
        elif p in self._chain_depth:
            self._chain_depth[str(run_id)] = self._chain_depth[p]

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown")
        if inputs is not None:
            args = inputs
        else:
            try:
                args = json.loads(input_str)
                if not isinstance(args, dict):
                    args = {"raw": input_str}
            except (json.JSONDecodeError, TypeError):
                args = {"raw": input_str}

        depth = self._get_depth(str(parent_run_id) if parent_run_id else None)
        self._step_counter += 1
        step = self._step_counter

        event = ToolEvent(
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            tool_name=tool_name,
            args=args,
            start_time=time.monotonic(),
            depth=depth,
            step=step,
        )
        self.events.append(event)
        self._by_run_id[str(run_id)] = event

        if self.console:
            indent = self._indent(depth)
            args_str = self._format_args_console(args)
            print(
                f"[{self.task_id}] {indent}"
                f"#{step}  {CLI_CYAN}->{CLI_CLR}  "
                f"{CLI_CYAN}{tool_name}{CLI_CLR}"
                f"({CLI_DIM}{args_str}{CLI_CLR})"
            )

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        event = self._by_run_id.get(str(run_id))
        if event is None:
            return

        event.end_time = time.monotonic()
        event.output = self._extract_output(output)
        event.status = "ok"

        if self.console:
            duration_ms = int((event.end_time - event.start_time) * 1000)
            indent = self._indent(event.depth)
            output_len = len(event.output)
            print(
                f"[{self.task_id}] {indent}"
                f"#{event.step}  {CLI_GREEN}<-{CLI_CLR}  "
                f"{event.tool_name}  "
                f"{CLI_GREEN}{duration_ms}ms{CLI_CLR}  "
                f"{CLI_DIM}({output_len} chars){CLI_CLR}"
            )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        event = self._by_run_id.get(str(run_id))
        if event is None:
            return

        event.end_time = time.monotonic()
        event.error = str(error)
        event.status = "error"

        if self.console:
            indent = self._indent(event.depth)
            print(
                f"[{self.task_id}] {indent}"
                f"#{event.step}  {CLI_RED}!!{CLI_CLR}  "
                f"{event.tool_name}  "
                f"{CLI_RED}ERROR: {error}{CLI_CLR}"
            )

    @property
    def has_events(self) -> bool:
        return len(self.events) > 0
