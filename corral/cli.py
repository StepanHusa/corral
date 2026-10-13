"""Command line: `corral <command>`. Run `corral -h` for the list."""

import argparse
import os
import shlex
import sys
import traceback
from pathlib import Path

from . import core, label, setfile, tmux

EPILOG = """\
examples:
  corral open school      open (or create) the set "school" in this terminal
  corral term             new terminal window that can be docked later (bind to Mod+Return)
  corral term ~/Claude claude   the same, in ~/Claude, with claude typed into its shell
  corral run ~/Claude claude    claude as a new task of the last set, shown in its window
  corral sets             list sets: * running, files in ~/.config/corral/sets/
  corral save school      snapshot what "school" runs now into its set file
  corral stop             kill corral's tmux server and every task in it

inside corral: Alt+j/k next/prev task, prefix D dock, prefix U undock,
prefix S switch set, prefix s focus the sidebar, prefix b hide/show it
(? in the sidebar for its keys)
"""


def _fail(message: str, code: int = 1) -> int:
    print(f"corral: {message}", file=sys.stderr)
    return code


def _check_name(name: str) -> str | None:
    if not setfile.valid_set_name(name):
        return f"bad set name {name!r} (letters, digits, . _ -)"
    return None


def _default_set() -> str:
    sets = setfile.available_sets()
    return core.last_set() or (sets[0] if sets else "main")


def _current_session() -> str | None:
    """The set session this command was typed in, if it runs inside corral."""
    pane = os.environ.get("TMUX_PANE")
    if not tmux.inside_corral() or not pane:
        return None
    return core.pane_info(pane, "#{session_name}")


def cmd_open(args: argparse.Namespace) -> int:
    name = args.set or _default_set()
    if problem := _check_name(name):
        return _fail(problem)
    for problem in core.ensure_set(name):
        print(f"corral: {setfile.set_path(name)}: {problem}", file=sys.stderr)
    core.remember_last_set(name)
    here = _current_session()
    if here is not None:
        client = core.first_client(here)
        tmux.run("switch-client", *(["-c", client] if client else []), "-t", f"={name}")
        return 0
    env = {k: v for k, v in os.environ.items() if k != "TMUX"}
    os.execvpe("tmux", tmux.base_cmd() + ["attach-session", "-t", f"={name}"], env)


def cmd_term(args: argparse.Namespace) -> int:
    directory = os.path.expanduser(args.dir) if args.dir else str(Path.home())
    core.open_terminal(core.loose_session_args(directory, shlex.join(args.command)))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Start a command as a new task of a set, show it, open the set if no window shows it."""
    name = args.set or _default_set()
    if problem := _check_name(name):
        return _fail(problem)
    for problem in core.ensure_set(name):
        print(f"corral: {setfile.set_path(name)}: {problem}", file=sys.stderr)
    command = shlex.join(args.command)
    wanted = label.tool_name(args.command[0]) if args.command else "shell"
    task = core.unique_name(name, wanted if setfile.valid_set_name(wanted) else "task")
    pane = core.add_task(name, task, args.dir, command)
    core.show(name, pane, focus=True)
    core.remember_last_set(name)
    if core.first_client(name) is None:
        core.open_terminal(["attach-session", "-t", f"={name}"])
    return 0


def cmd_sets(args: argparse.Namespace) -> int:
    running = set(core.set_sessions()) if tmux.server_running() else set()
    names = sorted(set(setfile.available_sets()) | running)
    if not names:
        print(f"no sets yet; `corral open <name>` creates one ({setfile.config_dir()})")
    for name in names:
        mark = "*" if name in running else " "
        has_file = "" if setfile.set_path(name).exists() else "  (no file)"
        print(f"{mark} {name}{has_file}")
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    name = args.set or _current_session() or core.last_set()
    if not name or not tmux.has_session(name):
        return _fail(f"set {name!r} is not running")
    print(f"saved {core.save_snapshot(name)}")
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    name = args.set or _current_session() or _default_set()
    if problem := _check_name(name):
        return _fail(problem)
    path = setfile.set_path(name)
    if not path.exists():
        setfile.save(name, [])
    os.execvp("sh", ["sh", "-c", f'{core.editor()} "$1"', "corral-edit", str(path)])


def cmd_apply(args: argparse.Namespace) -> int:
    if problem := _check_name(args.set):
        return _fail(problem)
    for problem in core.ensure_set(args.set):
        print(f"corral: {problem}", file=sys.stderr)
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    if not tmux.has_session(args.set):
        return _fail(f"set {args.set!r} is not running")
    core.close_set(args.set)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    if not tmux.server_running():
        print("corral is not running")
        return 0
    if not args.yes:
        answer = input("kill corral's tmux server and every task in it? [y/N] ")
        if answer.strip().lower() != "y":
            return 1
    tmux.run("kill-server", check=False)
    return 0


# --- internal commands, called from tmux key bindings and menus -------------

def cmd_sidebar(args: argparse.Namespace) -> int:
    from . import sidebar  # curses only where needed
    try:
        sidebar.run(args.set)
    except Exception:
        log = core.state_dir() / "sidebar.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as fh:
            traceback.print_exc(file=fh)
        raise
    return 0


def cmd_step(args: argparse.Namespace) -> int:
    core.step(args.session, args.delta)
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    if args.session not in core.set_sessions():
        tmux.run("display-message", "-d", "2000", "corral: new tasks go into a set (prefix S)", check=False)
        return 0
    pane = core.add_task(args.session, core.unique_name(args.session, "shell"), args.dir)
    core.show(args.session, pane, focus=True)
    return 0


def cmd_dock(args: argparse.Namespace) -> int:
    pane = args.pane or core.menu_context("pane") or os.environ.get("TMUX_PANE")
    if not pane:
        return _fail("no pane to dock")
    if problem := _check_name(args.set):
        return _fail(problem)
    core.dock(pane, args.set)
    return 0


def cmd_dock_menu(args: argparse.Namespace) -> int:
    current = core.pane_info(args.pane, "#{session_name}")
    core.show_set_menu(args.client, "dock into", "dock", current, pane=args.pane)
    return 0


def cmd_undock(args: argparse.Namespace) -> int:
    if not core.pane_info(args.pane, "#{@corral_task}"):
        tmux.run("display-message", "-d", "2000", "corral: not a docked task", check=False)
        return 0
    core.undock(args.pane)
    return 0


def cmd_set_menu(args: argparse.Namespace) -> int:
    current = tmux.run("display-message", "-p", "-c", args.client, "#{session_name}", check=False).strip()
    core.show_set_menu(args.client, "switch set", "switch", current)
    return 0


def cmd_switch(args: argparse.Namespace) -> int:
    if problem := _check_name(args.set):
        tmux.run("display-message", f"corral: {problem}", check=False)
        return 1
    client = core.menu_context("client")
    problems = core.ensure_set(args.set)
    tmux.run("switch-client", *(["-c", client] if client else []), "-t", f"={args.set}")
    core.remember_last_set(args.set)
    if problems:
        tmux.run("display-message", *(["-c", client] if client else []),
                 f"corral: {args.set}.conf: {problems[0]}", check=False)
    return 0


def cmd_focus_sidebar(args: argparse.Namespace) -> int:
    side = core.sidebar_pane(args.session)
    if side:
        tmux.run("select-pane", "-t", side)
    return 0


def cmd_toggle_sidebar(args: argparse.Namespace) -> int:
    core.toggle_sidebar(args.session)
    return 0


def cmd_reap(args: argparse.Namespace) -> int:
    core.reap_loose()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="corral",
        description="Task sets in a private tmux server, with a sidebar and docking.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def add(name, func, help_text=None):
        # internal commands get no help= at all, which keeps them out of -h
        p = sub.add_parser(name, help=help_text) if help_text else sub.add_parser(name)
        p.set_defaults(func=func)
        return p

    add("open", cmd_open, "open a set (default: the last one) in this terminal").add_argument("set", nargs="?")
    p = add("run", cmd_run, "start a command as a new task in a set (default: the last one)")
    p.add_argument("--set")
    p.add_argument("dir")
    p.add_argument("command", nargs=argparse.REMAINDER)
    p = add("term", cmd_term, "open a dockable terminal window, optionally running a command")
    p.add_argument("dir", nargs="?")
    p.add_argument("command", nargs=argparse.REMAINDER)
    add("sets", cmd_sets, "list sets")
    add("save", cmd_save, "snapshot a running set into its set file").add_argument("set", nargs="?")
    add("edit", cmd_edit, "edit a set file").add_argument("set", nargs="?")
    add("apply", cmd_apply, "start tasks of a set file that are not running").add_argument("set")
    add("close", cmd_close, "kill a set and its tasks").add_argument("set")
    add("stop", cmd_stop, "kill corral's tmux server").add_argument("-y", "--yes", action="store_true")

    add("sidebar", cmd_sidebar).add_argument("set")
    p = add("step", cmd_step)
    p.add_argument("session")
    p.add_argument("delta", type=int)
    p = add("new", cmd_new)
    p.add_argument("session")
    p.add_argument("dir")
    p = add("dock", cmd_dock)
    p.add_argument("set")
    p.add_argument("--pane")
    p = add("dock-menu", cmd_dock_menu)
    p.add_argument("pane")
    p.add_argument("client")
    add("undock", cmd_undock).add_argument("pane")
    add("set-menu", cmd_set_menu).add_argument("client")
    add("switch", cmd_switch).add_argument("set")
    add("focus-sidebar", cmd_focus_sidebar).add_argument("session")
    add("toggle-sidebar", cmd_toggle_sidebar).add_argument("session")
    add("reap", cmd_reap)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return args.func(args) or 0
    except tmux.TmuxError as err:
        return _fail(str(err), 2)
