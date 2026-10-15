"""Set files: one plain-text file per set, one task per line.

    # name     directory    command (rest of the line; empty = just a shell)
    monitor    ~            htop
    agent-1    ~/Claude     claude --continue

Name and directory cannot contain spaces; the command is everything after
them and is typed into the task's shell as if you typed it yourself.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

HEADER = (
    "# corral set file: one task per line.\n"
    "# name   directory   command (rest of the line; empty = just a shell)\n"
)


@dataclass(frozen=True)
class Entry:
    name: str
    directory: str
    command: str = ""


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "corral" / "sets"


def set_path(set_name: str) -> Path:
    return config_dir() / f"{set_name}.conf"


def available_sets() -> list[str]:
    folder = config_dir()
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.conf"))


def valid_set_name(name: str) -> bool:
    return bool(NAME_RE.match(name))


def parse(text: str) -> tuple[list[Entry], list[str]]:
    """Parse a set file. Bad lines are skipped and reported, never fatal."""
    entries: list[Entry] = []
    problems: list[str] = []
    seen: set[str] = set()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            problems.append(f"line {number}: need at least a name and a directory")
            continue
        name, directory = parts[0], parts[1]
        if not NAME_RE.match(name):
            problems.append(f"line {number}: bad task name {name!r}")
            continue
        if name in seen:
            problems.append(f"line {number}: duplicate task name {name!r}")
            continue
        seen.add(name)
        entries.append(Entry(name, directory, parts[2].strip() if len(parts) > 2 else ""))
    return entries, problems


def format_entries(entries: list[Entry]) -> str:
    name_w = max([len(e.name) for e in entries] + [4]) + 2
    dir_w = max([len(e.directory) for e in entries] + [9]) + 2
    body = "".join(
        f"{e.name:<{name_w}}{e.directory:<{dir_w}}{e.command}".rstrip() + "\n" for e in entries
    )
    return HEADER + body


def load(set_name: str) -> tuple[list[Entry], list[str]]:
    path = set_path(set_name)
    if not path.is_file():
        return [], []
    return parse(path.read_text())


def save(set_name: str, entries: list[Entry]) -> Path:
    path = set_path(set_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_entries(entries))
    return path


def expand_dir(directory: str) -> str:
    expanded = os.path.expanduser(directory)
    return expanded if os.path.isdir(expanded) else str(Path.home())


def contract_dir(directory: str) -> str:
    home = str(Path.home())
    if directory == home:
        return "~"
    if directory.startswith(home + "/"):
        return "~" + directory[len(home):]
    return directory
