import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"


def generate_run_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short = uuid4().hex[:6]
    return f"{ts}_{short}"


def create_run_dir(run_id: str) -> Path:
    run_dir = LOGS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _format_tool_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 200:
            v = v[:200] + "..."
        parts.append(f'{k}={json.dumps(v, ensure_ascii=False)}')
    return ", ".join(parts)


def format_task_log(
    task_id: str,
    instruction: str,
    messages: list,
    score: float | None = None,
    score_details: str = "",
) -> str:
    lines = [f"# Task: {task_id}\n"]
    lines.append(f"## Instruction\n\n{instruction}\n")
    lines.append("## Execution\n")

    step = 0
    for msg in messages:
        if isinstance(msg, HumanMessage):
            continue

        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    step += 1
                    args_str = _format_tool_args(tc["args"])
                    lines.append(f"### Step {step}: {tc['name']}\n")
                    if msg.content:
                        text = msg.content if isinstance(msg.content, str) else str(msg.content)
                        if text.strip():
                            lines.append(f"**Assistant:** {text.strip()}\n")
                    lines.append(f"**Tool call:** `{tc['name']}({args_str})`\n")
            elif msg.content:
                text = msg.content if isinstance(msg.content, str) else str(msg.content)
                if text.strip():
                    lines.append(f"**Assistant:** {text.strip()}\n")

        elif isinstance(msg, ToolMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            lines.append(f"<details>\n<summary>Result ({len(content)} chars)</summary>\n")
            lines.append(f"```\n{content}\n```\n")
            lines.append("</details>\n")

    lines.append("---\n")

    if score is not None:
        lines.append(f"## Score: {score:.2f}\n")
        if score_details:
            lines.append(f"```\n{score_details}\n```\n")

    return "\n".join(lines)


def format_error_log(
    task_id: str,
    instruction: str,
    error: str,
    score: float | None = None,
    score_details: str = "",
) -> str:
    lines = [f"# Task: {task_id}\n"]
    lines.append(f"## Instruction\n\n{instruction}\n")
    lines.append(f"## Error\n\n```\n{error}\n```\n")
    if score is not None:
        lines.append(f"## Score: {score:.2f}\n")
        if score_details:
            lines.append(f"```\n{score_details}\n```\n")
    return "\n".join(lines)


def write_task_log(run_dir: Path, task_id: str, content: str) -> None:
    path = run_dir / f"{task_id}.md"
    path.write_text(content, encoding="utf-8")


def write_run_summary(run_dir: Path, results: list, config: dict) -> None:
    lines = ["# Run Summary\n"]

    lines.append("## Config\n")
    for k, v in config.items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")

    lines.append("## Results\n")
    lines.append("| Task | Score |")
    lines.append("|------|-------|")
    for r in results:
        lines.append(f"| {r.task_id} | {r.score:.2f} |")
    lines.append("")

    if results:
        avg = sum(r.score for r in results) / len(results)
        lines.append(f"**Average: {avg * 100:.2f}%**\n")

    path = run_dir / "summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
