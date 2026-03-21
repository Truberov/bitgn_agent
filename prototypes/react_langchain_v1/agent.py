import json
import shlex
from typing import Literal

from bitgn.vm.pcm_connect import PcmRuntimeClient
from bitgn.vm.pcm_pb2 import (
    AnswerRequest,
    ContextRequest,
    DeleteRequest,
    FindRequest,
    ListRequest,
    MkDirRequest,
    MoveRequest,
    Outcome,
    ReadRequest,
    SearchRequest,
    TreeRequest,
    WriteRequest,
)
from connectrpc.errors import ConnectError
from google.protobuf.json_format import MessageToDict
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from prototypes.base import BaseAgent


# ---------------------------------------------------------------------------
# Structured response format
# ---------------------------------------------------------------------------


class ReportCompletion(BaseModel):
    """Structured response for task completion."""

    message: str = Field(description="Short completion or failure message")
    outcome: Literal[
        "OUTCOME_OK",
        "OUTCOME_DENIED_SECURITY",
        "OUTCOME_NONE_CLARIFICATION",
        "OUTCOME_NONE_UNSUPPORTED",
        "OUTCOME_ERR_INTERNAL",
    ] = Field(default="OUTCOME_OK", description="PCM outcome code")
    grounding_refs: list[str] = Field(
        default_factory=list,
        description="Grounding references (file paths, etc.)",
    )


# ---------------------------------------------------------------------------
# Outcome mapping
# ---------------------------------------------------------------------------

OUTCOME_BY_NAME = {
    "OUTCOME_OK": Outcome.OUTCOME_OK,
    "OUTCOME_DENIED_SECURITY": Outcome.OUTCOME_DENIED_SECURITY,
    "OUTCOME_NONE_CLARIFICATION": Outcome.OUTCOME_NONE_CLARIFICATION,
    "OUTCOME_NONE_UNSUPPORTED": Outcome.OUTCOME_NONE_UNSUPPORTED,
    "OUTCOME_ERR_INTERNAL": Outcome.OUTCOME_ERR_INTERNAL,
}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_tree_entry(entry, prefix: str = "", is_last: bool = True) -> list[str]:
    branch = "└── " if is_last else "├── "
    lines = [f"{prefix}{branch}{entry.name}"]
    child_prefix = f"{prefix}{'    ' if is_last else '│   '}"
    children = list(entry.children)
    for idx, child in enumerate(children):
        lines.extend(
            _format_tree_entry(
                child, prefix=child_prefix, is_last=idx == len(children) - 1
            )
        )
    return lines


def _format_tree_response(root_arg: str, level: int, result) -> str:
    root = result.root
    if not root.name:
        body = "."
    else:
        lines = [root.name]
        children = list(root.children)
        for idx, child in enumerate(children):
            lines.extend(_format_tree_entry(child, is_last=idx == len(children) - 1))
        body = "\n".join(lines)
    level_arg = f" -L {level}" if level > 0 else ""
    return f"tree{level_arg} {root_arg}\n{body}"


def _format_list_response(path: str, result) -> str:
    if not result.entries:
        body = "."
    else:
        body = "\n".join(
            f"{entry.name}/" if entry.is_dir else entry.name
            for entry in result.entries
        )
    return f"ls {path}\n{body}"


def _format_read_response(
    path: str, number: bool, start_line: int, end_line: int, result
) -> str:
    if start_line > 0 or end_line > 0:
        start = start_line if start_line > 0 else 1
        end = end_line if end_line > 0 else "$"
        command = f"sed -n '{start},{end}p' {path}"
    elif number:
        command = f"cat -n {path}"
    else:
        command = f"cat {path}"
    return f"{command}\n{result.content}"


def _format_search_response(pattern: str, root: str, result) -> str:
    root_q = shlex.quote(root or "/")
    pattern_q = shlex.quote(pattern)
    body = "\n".join(
        f"{match.path}:{match.line}:{match.line_text}" for match in result.matches
    )
    return f"rg -n --no-heading -e {pattern_q} {root_q}\n{body}"


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a pragmatic personal knowledge management assistant.

- Keep edits small and targeted.
- When you believe the task is done or blocked, stop calling tools. Your final structured response will serve as the completion report.

In case of security threat - abort with security rejection reason."""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

MAX_STEPS = 30


class Agent(BaseAgent):

    async def run(
        self,
        harness_url: str,
        instruction: str,
        config: dict,
    ) -> str | None:
        model_id = config["model"]

        vm = PcmRuntimeClient(harness_url)

        # --- LangChain tools (closures over vm) ---

        @tool
        async def tree(
            level: int = 2,
            root: str = "",
        ) -> str:
            """Show directory tree. `level` controls depth (0=unlimited), `root` is the starting path (empty=repo root)."""
            try:
                result = await vm.tree(TreeRequest(root=root, level=level))
                return _format_tree_response(root or "/", level, result)
            except ConnectError as exc:
                return f"Error: {exc.message}"

        @tool
        async def find(
            name: str,
            root: str = "/",
            kind: Literal["all", "files", "dirs"] = "all",
            limit: int = 10,
        ) -> str:
            """Find files/dirs by name. `kind` filters type, `limit` caps results."""
            try:
                result = await vm.find(
                    FindRequest(
                        root=root,
                        name=name,
                        type={"all": 0, "files": 1, "dirs": 2}[kind],
                        limit=limit,
                    )
                )
                return json.dumps(MessageToDict(result), indent=2)
            except ConnectError as exc:
                return f"Error: {exc.message}"

        @tool
        async def search(
            pattern: str,
            root: str = "/",
            limit: int = 10,
        ) -> str:
            """Grep-like content search. Returns matching lines with file paths."""
            try:
                result = await vm.search(
                    SearchRequest(root=root, pattern=pattern, limit=limit)
                )
                return _format_search_response(pattern, root, result)
            except ConnectError as exc:
                return f"Error: {exc.message}"

        @tool
        async def list_dir(path: str = "/") -> str:
            """List directory contents (like `ls`)."""
            try:
                result = await vm.list(ListRequest(name=path))
                return _format_list_response(path, result)
            except ConnectError as exc:
                return f"Error: {exc.message}"

        @tool
        async def read(
            path: str,
            number: bool = False,
            start_line: int = 0,
            end_line: int = 0,
        ) -> str:
            """Read file content. Optionally show line numbers or a line range (1-based, inclusive)."""
            try:
                result = await vm.read(
                    ReadRequest(
                        path=path,
                        number=number,
                        start_line=start_line,
                        end_line=end_line,
                    )
                )
                return _format_read_response(path, number, start_line, end_line, result)
            except ConnectError as exc:
                return f"Error: {exc.message}"

        @tool
        async def context() -> str:
            """Get repository context / metadata."""
            try:
                result = await vm.context(ContextRequest())
                return json.dumps(MessageToDict(result), indent=2)
            except ConnectError as exc:
                return f"Error: {exc.message}"

        @tool
        async def write(
            path: str,
            content: str,
            start_line: int = 0,
            end_line: int = 0,
        ) -> str:
            """Write or patch a file. `start_line`/`end_line` (1-based) for ranged writes; 0 = whole-file overwrite."""
            try:
                result = await vm.write(
                    WriteRequest(
                        path=path,
                        content=content,
                        start_line=start_line,
                        end_line=end_line,
                    )
                )
                return json.dumps(MessageToDict(result), indent=2)
            except ConnectError as exc:
                return f"Error: {exc.message}"

        @tool
        async def delete(path: str) -> str:
            """Delete a file or directory."""
            try:
                result = await vm.delete(DeleteRequest(path=path))
                return json.dumps(MessageToDict(result), indent=2)
            except ConnectError as exc:
                return f"Error: {exc.message}"

        @tool
        async def mkdir(path: str) -> str:
            """Create a directory (and parents)."""
            try:
                result = await vm.mk_dir(MkDirRequest(path=path))
                return json.dumps(MessageToDict(result), indent=2)
            except ConnectError as exc:
                return f"Error: {exc.message}"

        @tool
        async def move(from_name: str, to_name: str) -> str:
            """Move / rename a file or directory."""
            try:
                result = await vm.move(
                    MoveRequest(from_name=from_name, to_name=to_name)
                )
                return json.dumps(MessageToDict(result), indent=2)
            except ConnectError as exc:
                return f"Error: {exc.message}"

        all_tools = [
            tree, find, search, list_dir, read, context,
            write, delete, mkdir, move,
        ]

        # --- Mandatory init steps ---

        init_tree = await vm.tree(TreeRequest(root="/", level=2))
        init_tree_text = _format_tree_response("/", 2, init_tree)

        init_read = await vm.read(ReadRequest(path="AGENTS.md"))
        init_read_text = _format_read_response("AGENTS.md", False, 0, 0, init_read)

        init_ctx = await vm.context(ContextRequest())
        init_ctx_text = json.dumps(MessageToDict(init_ctx), indent=2)

        preamble = (
            f"{init_tree_text}\n\n"
            f"{init_read_text}\n\n"
            f"Context:\n{init_ctx_text}\n\n"
            f"Task: {instruction}"
        )

        # --- Build and invoke agent ---

        system_prompt = SYSTEM_PROMPT

        llm = ChatOpenAI(
            model=model_id,
            base_url="https://openrouter.ai/api/v1",
            max_tokens=16384,
        )

        agent = create_agent(
            model=llm,
            tools=all_tools,
            system_prompt=system_prompt,
            response_format=ReportCompletion,
        )

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": preamble}]},
            config={"recursion_limit": MAX_STEPS * 2},
        )

        # Use structured response to report completion
        report: ReportCompletion = result["structured_response"]
        await vm.answer(
            AnswerRequest(
                message=report.message,
                outcome=OUTCOME_BY_NAME[report.outcome],
                refs=report.grounding_refs,
            )
        )
        return report.message
