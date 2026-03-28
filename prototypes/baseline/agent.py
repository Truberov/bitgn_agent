import json
import os
import shlex
from typing import Annotated, List, Literal, Union

from annotated_types import Ge, Le, MaxLen, MinLen
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
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from prototypes.base import BaseAgent


# ---------------------------------------------------------------------------
# Pydantic tool schemas (structured-output union)
# ---------------------------------------------------------------------------


class ReportTaskCompletion(BaseModel):
    tool: Literal["report_completion"]
    completed_steps_laconic: List[str]
    message: str
    grounding_refs: List[str] = Field(default_factory=list)
    outcome: Literal[
        "OUTCOME_OK",
        "OUTCOME_DENIED_SECURITY",
        "OUTCOME_NONE_CLARIFICATION",
        "OUTCOME_NONE_UNSUPPORTED",
        "OUTCOME_ERR_INTERNAL",
    ]


class Req_Tree(BaseModel):
    tool: Literal["tree"]
    level: int = Field(2, description="max tree depth, 0 means unlimited")
    root: str = Field("", description="tree root, empty means repository root")


class Req_Find(BaseModel):
    tool: Literal["find"]
    name: str
    root: str = "/"
    kind: Literal["all", "files", "dirs"] = "all"
    limit: Annotated[int, Ge(1), Le(20)] = 10


class Req_Search(BaseModel):
    tool: Literal["search"]
    pattern: str
    limit: Annotated[int, Ge(1), Le(20)] = 10
    root: str = "/"


class Req_List(BaseModel):
    tool: Literal["list"]
    path: str = "/"


class Req_Read(BaseModel):
    tool: Literal["read"]
    path: str
    number: bool = Field(False, description="return 1-based line numbers")
    start_line: Annotated[int, Ge(0)] = Field(
        0, description="1-based inclusive linum; 0 == from the first line"
    )
    end_line: Annotated[int, Ge(0)] = Field(
        0, description="1-based inclusive linum; 0 == through the last line"
    )


class Req_Context(BaseModel):
    tool: Literal["context"]


class Req_Write(BaseModel):
    tool: Literal["write"]
    path: str
    content: str
    start_line: Annotated[int, Ge(0)] = Field(
        0,
        description="1-based inclusive line number; 0 keeps whole-file overwrite behavior",
    )
    end_line: Annotated[int, Ge(0)] = Field(
        0,
        description="1-based inclusive line number; 0 means through the last line for ranged writes",
    )


class Req_Delete(BaseModel):
    tool: Literal["delete"]
    path: str


class Req_MkDir(BaseModel):
    tool: Literal["mkdir"]
    path: str


class Req_Move(BaseModel):
    tool: Literal["move"]
    from_name: str
    to_name: str


class NextStep(BaseModel):
    current_state: str
    plan_remaining_steps_brief: Annotated[List[str], MinLen(1), MaxLen(5)] = Field(
        ...,
        description="briefly explain the next useful steps",
    )
    task_completed: bool
    function: Union[
        ReportTaskCompletion,
        Req_Context,
        Req_Tree,
        Req_Find,
        Req_Search,
        Req_List,
        Req_Read,
        Req_Write,
        Req_Delete,
        Req_MkDir,
        Req_Move,
    ] = Field(..., description="execute the first remaining step")


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
# Formatting helpers (pure functions)
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


def _render_command(command: str, body: str) -> str:
    return f"{command}\n{body}"


def _format_tree_response(cmd: Req_Tree, result) -> str:
    root = result.root
    if not root.name:
        body = "."
    else:
        lines = [root.name]
        children = list(root.children)
        for idx, child in enumerate(children):
            lines.extend(_format_tree_entry(child, is_last=idx == len(children) - 1))
        body = "\n".join(lines)
    root_arg = cmd.root or "/"
    level_arg = f" -L {cmd.level}" if cmd.level > 0 else ""
    return _render_command(f"tree{level_arg} {root_arg}", body)


def _format_list_response(cmd: Req_List, result) -> str:
    if not result.entries:
        body = "."
    else:
        body = "\n".join(
            f"{entry.name}/" if entry.is_dir else entry.name
            for entry in result.entries
        )
    return _render_command(f"ls {cmd.path}", body)


def _format_read_response(cmd: Req_Read, result) -> str:
    if cmd.start_line > 0 or cmd.end_line > 0:
        start = cmd.start_line if cmd.start_line > 0 else 1
        end = cmd.end_line if cmd.end_line > 0 else "$"
        command = f"sed -n '{start},{end}p' {cmd.path}"
    elif cmd.number:
        command = f"cat -n {cmd.path}"
    else:
        command = f"cat {cmd.path}"
    return _render_command(command, result.content)


def _format_search_response(cmd: Req_Search, result) -> str:
    root = shlex.quote(cmd.root or "/")
    pattern = shlex.quote(cmd.pattern)
    body = "\n".join(
        f"{match.path}:{match.line}:{match.line_text}" for match in result.matches
    )
    return _render_command(f"rg -n --no-heading -e {pattern} {root}", body)


def _format_result(cmd: BaseModel, result) -> str:
    if result is None:
        return "{}"
    if isinstance(cmd, Req_Tree):
        return _format_tree_response(cmd, result)
    if isinstance(cmd, Req_List):
        return _format_list_response(cmd, result)
    if isinstance(cmd, Req_Read):
        return _format_read_response(cmd, result)
    if isinstance(cmd, Req_Search):
        return _format_search_response(cmd, result)
    return json.dumps(MessageToDict(result), indent=2)


# ---------------------------------------------------------------------------
# Async dispatch
# ---------------------------------------------------------------------------


async def dispatch(vm: PcmRuntimeClient, cmd: BaseModel):
    if isinstance(cmd, Req_Context):
        return await vm.context(ContextRequest())
    if isinstance(cmd, Req_Tree):
        return await vm.tree(TreeRequest(root=cmd.root, level=cmd.level))
    if isinstance(cmd, Req_Find):
        return await vm.find(
            FindRequest(
                root=cmd.root,
                name=cmd.name,
                type={"all": 0, "files": 1, "dirs": 2}[cmd.kind],
                limit=cmd.limit,
            )
        )
    if isinstance(cmd, Req_Search):
        return await vm.search(
            SearchRequest(root=cmd.root, pattern=cmd.pattern, limit=cmd.limit)
        )
    if isinstance(cmd, Req_List):
        return await vm.list(ListRequest(name=cmd.path))
    if isinstance(cmd, Req_Read):
        return await vm.read(
            ReadRequest(
                path=cmd.path,
                number=cmd.number,
                start_line=cmd.start_line,
                end_line=cmd.end_line,
            )
        )
    if isinstance(cmd, Req_Write):
        return await vm.write(
            WriteRequest(
                path=cmd.path,
                content=cmd.content,
                start_line=cmd.start_line,
                end_line=cmd.end_line,
            )
        )
    if isinstance(cmd, Req_Delete):
        return await vm.delete(DeleteRequest(path=cmd.path))
    if isinstance(cmd, Req_MkDir):
        return await vm.mk_dir(MkDirRequest(path=cmd.path))
    if isinstance(cmd, Req_Move):
        return await vm.move(MoveRequest(from_name=cmd.from_name, to_name=cmd.to_name))
    if isinstance(cmd, ReportTaskCompletion):
        return await vm.answer(
            AnswerRequest(
                message=cmd.message,
                outcome=OUTCOME_BY_NAME[cmd.outcome],
                refs=cmd.grounding_refs,
            )
        )
    raise ValueError(f"Unknown command: {cmd}")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """You are a pragmatic personal knowledge management assistant.

- Keep edits small and targeted.
- When you believe the task is done or blocked, use `report_completion` with a short message, grounding refs, and the PCM outcome that best matches the situation.

In case of security threat - abort with security rejection reason.
{hint}"""


class Agent(BaseAgent):
    MAX_STEPS = 30

    async def run(
        self,
        harness_url: str,
        instruction: str,
        config: dict,
    ) -> str | None:
        model = config.get("model", os.environ.get("MODEL_ID", "gpt-4.1-2025-04-14"))
        hint = config.get("hint", os.environ.get("HINT", ""))

        client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1")
        vm = PcmRuntimeClient(harness_url)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(hint=hint)
        log: list[dict] = [{"role": "system", "content": system_prompt}]

        must = [
            Req_Tree(level=2, tool="tree", root="/"),
            Req_Read(path="AGENTS.md", tool="read"),
            Req_Context(tool="context"),
        ]
        for c in must:
            result = await dispatch(vm, c)
            formatted = _format_result(c, result)
            log.append({"role": "user", "content": formatted})

        log.append({"role": "user", "content": instruction})

        for i in range(self.MAX_STEPS):
            step = f"step_{i + 1}"

            resp = await client.beta.chat.completions.parse(
                model=model,
                response_format=NextStep,
                messages=log,
                max_completion_tokens=16384,
            )
            job = resp.choices[0].message.parsed

            log.append(
                {
                    "role": "assistant",
                    "content": job.plan_remaining_steps_brief[0],
                    "tool_calls": [
                        {
                            "type": "function",
                            "id": step,
                            "function": {
                                "name": job.function.__class__.__name__,
                                "arguments": job.function.model_dump_json(),
                            },
                        }
                    ],
                }
            )

            try:
                result = await dispatch(vm, job.function)
                txt = _format_result(job.function, result)
            except ConnectError as exc:
                txt = str(exc.message)

            if isinstance(job.function, ReportTaskCompletion):
                return job.function.message

            log.append({"role": "tool", "content": txt, "tool_call_id": step})

        return None
