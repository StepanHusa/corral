"""Thin wrapper around corral's own tmux server (`tmux -L corral`).

Every call goes to the private socket with corral's own config, so the
user's normal tmux server (~/.tmux.conf, resurrect, ...) is never touched.
CORRAL_SOCKET overrides the socket name (tests use a throwaway one).
"""

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONF = REPO / "tmux.conf"
BIN = REPO / "bin" / "corral"


class TmuxError(RuntimeError):
    pass


def socket_name() -> str:
    return os.environ.get("CORRAL_SOCKET", "corral")


def base_cmd() -> list[str]:
    return ["tmux", "-L", socket_name(), "-f", str(CONF)]


def run(*args: str, check: bool = True) -> str:
    """Run one tmux command line (args may contain ';' separators); return stdout."""
    env = dict(os.environ)
    env.pop("TMUX", None)  # never let an outer tmux redirect the call
    proc = subprocess.run(base_cmd() + list(args), capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        raise TmuxError(f"tmux {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def ok(*args: str) -> bool:
    try:
        run(*args)
        return True
    except TmuxError:
        return False


def server_running() -> bool:
    return ok("list-sessions")


def has_session(name: str) -> bool:
    # '=' forces an exact match instead of tmux's prefix matching
    return ok("has-session", "-t", f"={name}")


def lines(*args: str) -> list[list[str]]:
    """Run a list-* command whose -F format is tab separated; return the rows."""
    out = run(*args, check=False)
    return [line.split("\t") for line in out.splitlines() if line]


def inside_corral() -> bool:
    """True when the calling process runs inside a pane of corral's server."""
    tmux_env = os.environ.get("TMUX", "")
    return tmux_env.split(",")[0].endswith("/" + socket_name())
