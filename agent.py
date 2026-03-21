import json
from typing import Optional

from google.protobuf.json_format import MessageToDict
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI

from bitgn.vm.mini_connect import MiniRuntimeClientSync
from bitgn.vm.mini_pb2 import (
    AnswerRequest,
    DeleteRequest,
    ListRequest,
    OutlineRequest,
    ReadRequest,
    SearchRequest,
    WriteRequest,
)
from connectrpc.errors import ConnectError

SYSTEM_PROMPT = """
You are a personal business assistant, helpful and precise.

- always start by discovering available information by running root outline.
- always read `AGENTS.md` at the start
- always reference (ground) in final response all files that contributed to the answer
- Clearly report when tasks are done
"""

CLI_RED = "\x1b[31m"
CLI_GREEN = "\x1b[32m"
CLI_CLR = "\x1b[0m"
CLI_BLUE = "\x1b[34m"


class VMHolder:
    """Mutable container so tools can reference the current VM without rebuilding the agent."""

    def __init__(self):
        self.vm: MiniRuntimeClientSync | None = None

    def set(self, harness_url: str):
        self.vm = MiniRuntimeClientSync(harness_url)

    def get(self) -> MiniRuntimeClientSync:
        assert self.vm is not None, "VM not initialized — call set() first"
        return self.vm


def _call_vm(fn, *args):
    """Call a VM method and return JSON string result or error text."""
    try:
        result = fn(*args)
        mapped = MessageToDict(result)
        txt = json.dumps(mapped, indent=2)
        print(f"{CLI_GREEN}OUT{CLI_CLR}: {txt}")
        return txt
    except ConnectError as e:
        print(f"{CLI_RED}ERR {e.code}: {e.message}{CLI_CLR}")
        return f"Error: {e.message}"


def _create_tools(holder: VMHolder):
    """Create LangChain tools bound to a VMHolder (re-pointable across tasks)."""

    @tool
    def tree(path: str) -> str:
        """Get folder structure / outline at the given path."""
        return _call_vm(holder.get().outline, OutlineRequest(path=path))

    @tool
    def search(pattern: str, path: str = "/", count: int = 5) -> str:
        """Search for files matching a pattern. Returns up to `count` results."""
        return _call_vm(
            holder.get().search, SearchRequest(path=path, pattern=pattern, count=count)
        )

    @tool
    def list_dir(path: str) -> str:
        """List contents of a directory."""
        return _call_vm(holder.get().list, ListRequest(path=path))

    @tool
    def read_file(path: str) -> str:
        """Read the contents of a file."""
        return _call_vm(holder.get().read, ReadRequest(path=path))

    @tool
    def write_file(path: str, content: str) -> str:
        """Write content to a file."""
        return _call_vm(holder.get().write, WriteRequest(path=path, content=content))

    @tool
    def delete_file(path: str) -> str:
        """Delete a file."""
        return _call_vm(holder.get().delete, DeleteRequest(path=path))

    @tool
    def report_completion(
        answer: str, grounding_refs: Optional[list[str]] = None
    ) -> str:
        """Submit the final answer when the task is complete. Include grounding_refs listing all files that contributed to the answer."""
        refs = grounding_refs or []
        result = _call_vm(holder.get().answer, AnswerRequest(answer=answer, refs=refs))

        print(f"\n{CLI_BLUE}AGENT ANSWER: {answer}{CLI_CLR}")
        for ref in refs:
            print(f"- {CLI_BLUE}{ref}{CLI_CLR}")

        return result

    return [
        tree,
        search,
        list_dir,
        read_file,
        write_file,
        delete_file,
        report_completion,
    ]


def build_agent(model: str):
    """Build the agent once. Returns (agent, vm_holder) — call vm_holder.set() before each task."""
    holder = VMHolder()
    llm = ChatOpenAI(model=model, base_url="https://openrouter.ai/api/v1")
    tools = _create_tools(holder)
    agent = create_agent(llm, tools=tools, system_prompt=SYSTEM_PROMPT)
    return agent, holder


def run_agent(
    agent,
    holder: VMHolder,
    harness_url: str,
    task_text: str,
    langfuse_handler=None,
    langfuse_metadata=None,
    run_name=None,
):
    """Run a single task. Points the VM to the new harness_url and invokes the agent."""
    holder.set(harness_url)

    config = {}
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
    if langfuse_metadata:
        config["metadata"] = langfuse_metadata
    if run_name:
        config["run_name"] = run_name

    result = agent.invoke(
        {"messages": [{"role": "user", "content": task_text}]},
        config=config,
    )

    messages = result.get("messages", [])
    if messages:
        final = messages[-1]
        content = final.content if hasattr(final, "content") else str(final)
        return content

    return None
