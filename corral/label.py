"""Sidebar labels: what a task is, derived from what runs in it.

Nothing here is typed by the user: the label comes from the foreground
program (argv read from /proc), its directory, and for Claude Code the
terminal title it sets to the conversation's topic. A label set by hand
(sidebar `r`) wins over all of this.
"""

from pathlib import Path

from .setfile import contract_dir

SHELLS = {"zsh", "bash", "sh", "fish", "dash"}
# Programs that run a script: the script is the tool (`node .../claude`).
INTERPRETERS = {"node", "python", "python3", "bun", "deno", "perl", "ruby"}
# Programs whose terminal title says what they work on.
TITLE_TOOLS = {"claude"}


def tool_argv(argv: list[str]) -> list[str]:
    """argv starting at the tool: `node /x/claude -c` -> `claude -c`."""
    if len(argv) > 1 and Path(argv[0]).name in INTERPRETERS and not argv[1].startswith("-"):
        return argv[1:]
    return argv


def tool_name(path: str) -> str:
    name = Path(path).name
    for ext in (".py", ".js", ".mjs", ".sh"):
        name = name.removesuffix(ext)
    return name


def title_topic(title: str) -> str:
    """'✳ Fix the parser' -> 'Fix the parser' (drops a leading spinner glyph)."""
    text = title.strip()
    if len(text) > 2 and not text[0].isalnum() and text[1] == " ":
        text = text[2:].strip()
    return text


def describe(argv: list[str] | None, command: str, path: str, title: str) -> tuple[str, str]:
    """(label, detail) for a sidebar row.

    argv is the foreground program ([] = idle shell, None = unreadable,
    then tmux's pane_current_command is used instead).
    """
    where = contract_dir(path)
    if argv is None:
        argv = [] if command in SHELLS else [command]
    if not argv:
        return where, "shell"
    args = tool_argv(argv)
    tool = tool_name(args[0])
    if tool in TITLE_TOOLS:
        topic = title_topic(title)
        return (topic or tool), f"{tool} · {where}"
    target = next((a for a in args[1:] if _is_file(a, path)), None)
    label = f"{tool} {Path(target).name}" if target else tool
    return label, where


def _is_file(arg: str, cwd: str) -> bool:
    """An argument naming an existing file (not a flag or a flag's value)."""
    return not arg.startswith("-") and (Path(cwd) / Path(arg).expanduser()).is_file()


def fit(text: str, width: int) -> str:
    """Cut text to width columns, marking the cut with an ellipsis."""
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: width - 1] + "…"
