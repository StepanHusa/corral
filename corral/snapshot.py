"""Read what a task pane is running right now, for `corral save`.

The pane's shell is pane_pid; the program in the foreground is the leader of
the terminal's foreground process group (tpgid in /proc/<pid>/stat). If that
is the shell itself, the task is an idle shell and gets an empty command.
"""

import shlex
from pathlib import Path

PROC = Path("/proc")

# Commands that restart as a *new* session unless told to continue.
CONTINUE_FLAGS = {"claude": ({"-c", "--continue", "-r", "--resume"}, "--continue")}


def foreground_argv(shell_pid: int, proc: Path = PROC) -> list[str] | None:
    """argv of the foreground program, [] for an idle shell, None if unreadable."""
    try:
        stat = (proc / str(shell_pid) / "stat").read_text()
    except OSError:
        return None
    fields = stat.rsplit(")", 1)[-1].split()
    try:
        tpgid = int(fields[5])
    except (IndexError, ValueError):
        return None
    if tpgid <= 0 or tpgid == shell_pid:
        return []
    try:
        raw = (proc / str(tpgid) / "cmdline").read_bytes()
    except OSError:
        return None
    return [part.decode(errors="replace") for part in raw.split(b"\0") if part]


def normalize(argv: list[str]) -> str:
    """Turn a live argv into the command line a set file should restart with."""
    if not argv:
        return ""
    # Interpreted tools show up as `node /path/to/claude ...`; keep the tool.
    for i, part in enumerate(argv[:2]):
        tool = Path(part).name
        if tool in CONTINUE_FLAGS:
            args = argv[i + 1:]
            flags, add = CONTINUE_FLAGS[tool]
            if not flags.intersection(args):
                args = [add] + args
            return shlex.join([tool] + args)
    prog = argv[0]
    if prog.startswith(("/usr/bin/", "/bin/", "/usr/local/bin/")):
        prog = Path(prog).name  # on PATH anyway; keeps the set file readable
    return shlex.join([prog] + argv[1:])
