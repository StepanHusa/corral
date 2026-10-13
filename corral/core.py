"""Sets, tasks, showing, docking: everything that moves panes around.

Model (all on corral's private tmux server):
  set        a tmux session marked @corral_set; its first window is the
             *view*: the sidebar pane on the left, the shown task on the right
  task       a pane marked @corral_task=<name>; tasks not on screen are
             parked one per hidden window. Showing a task swaps its pane with
             the one in the view, so processes never notice they moved.
  loose      a session marked @corral_loose: a plain-looking terminal window
             (`corral term`, or an undocked task). Dies when its window closes.
"""

import os
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import label, setfile, snapshot, tmux

SIDEBAR_WIDTH = 23  # minimum columns (about 200 px); tmux.conf: @corral_sidebar_width


@dataclass(frozen=True)
class Task:
    pane: str
    window: str
    name: str
    order: int
    command: str
    path: str
    pid: int
    bell: bool
    title: str
    label: str  # set by hand (sidebar `r`); empty = derived from what runs


_TASK_FMT = "\t".join([
    "#{pane_id}", "#{window_id}", "#{@corral_task}", "#{@corral_order}",
    "#{pane_current_command}", "#{pane_current_path}", "#{pane_pid}", "#{window_bell_flag}",
    "#{pane_title}", "#{@corral_label}",
])


# --- state ------------------------------------------------------------------

def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "corral"


def remember_last_set(name: str) -> None:
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "last_set").write_text(name + "\n")


def last_set() -> str | None:
    try:
        name = (state_dir() / "last_set").read_text().strip()
    except OSError:
        return None
    return name or None


# --- queries ----------------------------------------------------------------

def tasks(session: str) -> list[Task]:
    rows = tmux.lines("list-panes", "-s", "-t", f"={session}", "-F", _TASK_FMT)
    found = []
    for r in rows:
        if len(r) < 10 or not r[2]:
            continue
        found.append(Task(r[0], r[1], r[2], int(r[3] or 0), r[4], r[5], int(r[6] or 0), r[7] == "1",
                          r[8], r[9]))
    return sorted(found, key=lambda t: t.order)


def pane_info(pane: str, fmt: str) -> str | None:
    try:
        return tmux.run("display-message", "-p", "-t", pane, fmt).rstrip("\n")
    except tmux.TmuxError:
        return None


def session_option(session: str, option: str) -> str:
    return tmux.run("show-options", "-qv", "-t", f"={session}:", option, check=False).strip()


def sidebar_pane(session: str) -> str | None:
    pane = session_option(session, "@corral_sidebar")
    if not pane or pane_info(pane, "#{session_name}") != session:
        return None
    return pane


def main_pane(session: str) -> str | None:
    side = sidebar_pane(session)
    if side is None:
        return None
    view = pane_info(side, "#{window_id}")
    others = [r[0] for r in tmux.lines("list-panes", "-t", view, "-F", "#{pane_id}") if r[0] != side]
    return others[0] if others else None


def set_sessions() -> list[str]:
    rows = tmux.lines("list-sessions", "-F", "#{session_name}\t#{@corral_set}")
    return [r[0] for r in rows if len(r) > 1 and r[1] == "1"]


def sidebar_width() -> int:
    value = tmux.run("show-options", "-gqv", "@corral_sidebar_width", check=False).strip()
    return int(value) if value.isdigit() else SIDEBAR_WIDTH


def first_client(session: str) -> str | None:
    rows = tmux.lines("list-clients", "-t", f"={session}", "-F", "#{client_name}")
    return rows[0][0] if rows else None


# --- building sets ----------------------------------------------------------

def _server_options() -> list[str]:
    """Commands that let tmux.conf key bindings find this checkout."""
    return ["set-option", "-g", "@corral_bin", str(tmux.BIN), ";",
            "set-option", "-g", "@corral_conf", str(tmux.CONF)]


def _sidebar_cmd(session: str) -> str:
    # restart loop: a crashed sidebar (traceback in sidebar.log) comes back
    return f"while :; do {shlex.quote(str(tmux.BIN))} sidebar {shlex.quote(session)}; sleep 1; done"


def _next_order(session: str) -> int:
    order = int(session_option(session, "@corral_seq") or 0) + 1
    tmux.run("set-option", "-t", f"={session}:", "@corral_seq", str(order))
    return order


def unique_name(session: str, wanted: str) -> str:
    taken = {t.name for t in tasks(session)}
    name, n = wanted, 2
    while name in taken:
        name, n = f"{wanted}-{n}", n + 1
    return name


def ensure_set(name: str) -> list[str]:
    """Make the set's session exist with a sidebar and every task from its file.

    Tasks already running are left alone; only missing ones are started.
    Returns problems found in the set file (bad lines are skipped).
    """
    if not tmux.has_session(name):
        tmux.run("new-session", "-d", "-s", name, "-n", "corral", "-x", "200", "-y", "50",
                 "-c", str(Path.home()), _sidebar_cmd(name), ";", *_server_options())
        side = tmux.run("display-message", "-p", "-t", f"={name}:", "#{pane_id}").strip()
        tmux.run("set-option", "-t", f"={name}:", "@corral_set", "1", ";",
                 "set-option", "-t", f"={name}:", "@corral_sidebar", side)
    else:
        tmux.run(*_server_options())
        if sidebar_pane(name) is None:
            _rebuild_sidebar(name)

    entries, problems = setfile.load(name)
    running = {t.name for t in tasks(name)}
    for entry in entries:
        if entry.name not in running:
            add_task(name, entry.name, entry.directory, entry.command)
    fill_main(name)
    return problems


def _rebuild_sidebar(session: str) -> None:
    current = tasks(session)
    if current:
        side = tmux.run("split-window", "-hbd", "-l", str(sidebar_width()), "-t", current[0].pane,
                        "-P", "-F", "#{pane_id}", _sidebar_cmd(session)).strip()
        tmux.run("select-window", "-t", pane_info(side, "#{window_id}"))
    else:
        side = tmux.run("new-window", "-t", f"={session}:", "-n", "corral",
                        "-P", "-F", "#{pane_id}", _sidebar_cmd(session)).strip()
    tmux.run("set-option", "-t", f"={session}:", "@corral_sidebar", side)


def add_task(session: str, name: str, directory: str, command: str = "") -> str:
    """Start a parked task: a shell in `directory`, with `command` typed into it."""
    pane = tmux.run("new-window", "-d", "-t", f"={session}:", "-n", name,
                    "-c", setfile.expand_dir(directory), "-P", "-F", "#{pane_id}").strip()
    _mark_task(session, pane, name)
    if command:
        tmux.run("send-keys", "-t", pane, "-l", command, ";", "send-keys", "-t", pane, "Enter")
    return pane


def _mark_task(session: str, pane: str, name: str) -> None:
    tmux.run("set-option", "-p", "-t", pane, "@corral_task", name, ";",
             "set-option", "-p", "-t", pane, "@corral_order", str(_next_order(session)))


def set_label(pane: str, text: str) -> None:
    """Label a task by hand; an empty text goes back to the derived label."""
    if text:
        tmux.run("set-option", "-p", "-t", pane, "@corral_label", text)
    else:
        tmux.run("set-option", "-p", "-u", "-t", pane, "@corral_label", check=False)


def kill_task(pane: str) -> None:
    tmux.run("kill-pane", "-t", pane, check=False)


def close_set(session: str) -> None:
    tmux.run("kill-session", "-t", f"={session}", check=False)


# --- showing ----------------------------------------------------------------

def show(session: str, pane: str, focus: bool = False) -> None:
    """Put `pane` into the view next to the sidebar; the previous one gets parked."""
    side = sidebar_pane(session)
    if side is None:
        return
    view = pane_info(side, "#{window_id}")
    hidden = sidebar_hidden(side)
    if pane_info(pane, "#{window_id}") != view:
        current = main_pane(session)
        if current:
            tmux.run("swap-pane", "-d", "-s", pane, "-t", current)
        else:
            tmux.run("join-pane", "-d", "-h", "-s", pane, "-t", side)
            tmux.run("resize-pane", "-t", side, "-x", str(sidebar_width()))
    if hidden:  # stay hidden: the new task gets the zoom, and the focus
        tmux.run("select-window", "-t", view, ";", "select-pane", "-t", pane)
        if not sidebar_hidden(side):
            tmux.run("resize-pane", "-Z", "-t", pane)
    else:
        tmux.run("select-window", "-t", view, ";", "select-pane", "-t", pane if focus else side)
    nudge_sidebar(side)


def sidebar_hidden(side: str) -> bool:
    """The sidebar is hidden by zooming the shown task over the whole view."""
    return pane_info(side, "#{window_zoomed_flag}") == "1"


def toggle_sidebar(session: str) -> None:
    """Hide the sidebar (zoom the shown task) or bring it back."""
    shown = main_pane(session)
    if shown:
        tmux.run("resize-pane", "-Z", "-t", shown)


def nudge_sidebar(side: str) -> None:
    """Make the sidebar redraw now instead of at its next poll (Alt+j/k etc.)."""
    pid = pane_info(side, "#{@corral_sidebar_pid}")
    if not pid or not pid.isdigit() or int(pid) == os.getpid():
        return
    try:
        os.kill(int(pid), signal.SIGUSR1)
    except OSError:
        pass  # sidebar restarting; its next poll catches up


def fill_main(session: str) -> None:
    """If nothing is shown (e.g. the shown task just exited), show the first task."""
    if main_pane(session) is None:
        current = tasks(session)
        if current:
            show(session, current[0].pane)


def step(session: str, delta: int) -> None:
    """Show the next (+1) or previous (-1) task and focus it."""
    current = tasks(session)
    if not current:
        return
    shown = main_pane(session)
    index = next((i for i, t in enumerate(current) if t.pane == shown), -1)
    show(session, current[(index + delta) % len(current)].pane, focus=True)


# --- docking ----------------------------------------------------------------

def _derive_name(pane: str) -> str:
    command = pane_info(pane, "#{pane_current_command}") or "shell"
    if command in label.SHELLS:
        path = pane_info(pane, "#{pane_current_path}") or ""
        return Path(path).name or "shell"
    return command


def _move_pane_to(pane: str, session: str) -> None:
    """Move a pane into its own new window at the end of `session`."""
    window = pane_info(pane, "#{window_id}")
    if pane_info(pane, "#{window_panes}") == "1":
        tmux.run("move-window", "-d", "-s", window, "-t", f"={session}:")
    else:
        tmux.run("break-pane", "-d", "-s", pane, "-t", f"={session}:")


def dock(pane: str, target: str) -> list[str]:
    """Move a pane (a loose terminal, or a task of another set) into set `target`."""
    problems = ensure_set(target)
    if pane_info(pane, "#{session_name}") == target:
        return problems
    name = pane_info(pane, "#{@corral_task}") or _derive_name(pane)
    name = unique_name(target, name)
    _move_pane_to(pane, target)  # a loose session left empty dies, closing its window
    _mark_task(target, pane, name)
    show(target, pane)
    remember_last_set(target)
    return problems


def undock(pane: str) -> str:
    """Move a task out into its own loose session and open a terminal window on it."""
    path = pane_info(pane, "#{pane_current_path}") or str(Path.home())
    loose = tmux.run("new-session", "-d", "-P", "-F", "#{session_name}", "-c", path).strip()
    placeholder = tmux.run("display-message", "-p", "-t", f"={loose}:", "#{window_id}").strip()
    tmux.run("set-option", "-t", f"={loose}:", "@corral_loose", "1")
    _move_pane_to(pane, loose)
    tmux.run("kill-window", "-t", placeholder)
    open_terminal(["attach-session", "-t", f"={loose}"])
    return loose


def reap_loose() -> None:
    """Kill loose sessions whose window was closed (attached once, now detached).

    Sessions never attached yet are kept: their terminal may still be opening,
    and killing them would kill the task inside.
    """
    fmt = "#{session_name}\t#{session_attached}\t#{session_last_attached}\t#{@corral_loose}"
    for row in tmux.lines("list-sessions", "-F", fmt):
        if len(row) < 4 or row[3] != "1" or row[1] != "0":
            continue
        if row[2] and row[2] != "0":
            tmux.run("kill-session", "-t", f"={row[0]}", check=False)


# --- terminals --------------------------------------------------------------

def terminal_prefix() -> list[str]:
    return shlex.split(os.environ.get("CORRAL_TERMINAL", "xfce4-terminal -x"))


def open_terminal(tmux_args: list[str]) -> None:
    """Open a new terminal window running a tmux client of corral's server."""
    if os.environ.get("CORRAL_NO_TERMINAL"):
        return
    env = {k: v for k, v in os.environ.items() if k != "TMUX"}
    subprocess.Popen(terminal_prefix() + tmux.base_cmd() + tmux_args, env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def loose_session_args(directory: str) -> list[str]:
    """tmux args that create and attach a fresh loose session."""
    return ["new-session", "-c", directory, ";",
            "set-option", "@corral_loose", "1", ";", *_server_options()]


# --- snapshots --------------------------------------------------------------

def snapshot_entries(session: str) -> list[setfile.Entry]:
    entries = []
    for t in tasks(session):
        argv = snapshot.foreground_argv(t.pid) or []
        entries.append(setfile.Entry(t.name, setfile.contract_dir(t.path), snapshot.normalize(argv)))
    return entries


def save_snapshot(session: str) -> Path:
    return setfile.save(session, snapshot_entries(session))


def editor() -> str:
    for candidate in (os.environ.get("VISUAL"), os.environ.get("EDITOR"), "nvim", "vim", "vi"):
        if candidate and subprocess.run(["sh", "-c", f"command -v {shlex.quote(candidate.split()[0])}"],
                                        capture_output=True).returncode == 0:
            return candidate
    return "vi"


def edit_in_popup(session: str, client: str | None) -> None:
    """Open the set file in an editor popup; re-apply it when the editor closes."""
    path = setfile.set_path(session)
    if not path.exists():
        setfile.save(session, [])
    script = (f"{editor()} {shlex.quote(str(path))}; "
              f"{shlex.quote(str(tmux.BIN))} apply {shlex.quote(session)}")
    args = ["display-popup", "-E", "-w", "80%", "-h", "80%", "-T", f" {session}.conf "]
    if client:
        args += ["-c", client]
    tmux.run(*args, script)


# --- menus (tmux's own display-menu, so they work from any pane) ------------

def _menu_sets() -> list[str]:
    return sorted(set(setfile.available_sets()) | set(set_sessions()))


def menu_context(key: str) -> str:
    """Read what a menu was opened for (client name, pane id); see show_set_menu."""
    return tmux.run("show-options", "-gqv", f"@corral_menu_{key}", check=False).strip()


def show_set_menu(client: str, title: str, action: str, current: str | None = None,
                  pane: str = "") -> None:
    """Pop up a list of sets; picking one runs `corral <action> <set>`.

    The client and pane the menu is about are parked in global options instead
    of being spliced into the menu commands: pane ids start with '%', which
    command-prompt would read as its own %1..%9 placeholders.
    """
    tmux.run("set-option", "-g", "@corral_menu_client", client, ";",
             "set-option", "-g", "@corral_menu_pane", pane)
    bin_ = shlex.quote(str(tmux.BIN))
    running = set(set_sessions())
    items: list[str] = []
    for i, name in enumerate(_menu_sets()):
        mark = "•" if name == current else ("*" if name in running else " ")
        key = str(i + 1) if i < 9 else ""
        items += [f"{mark} {name}", key, f"run-shell -b \"{bin_} {action} {name}\""]
    items += ["", "", ""]  # separator
    items += ["New set…", "n",
              f"command-prompt -p 'new set name:' \"run-shell -b '{bin_} {action} %1'\""]
    tmux.run("display-menu", "-c", client, "-T", f" {title} ", "-x", "C", "-y", "C", *items)
