"""The sidebar: the task list on the left of a set's view (stdlib curses)."""

import curses
import locale
import os
import time
import zlib

from . import core, setfile, tmux
from .status import Tracker

REFRESH_SECONDS = 1.0
ROWS_PER_TASK = 2
HEADER_ROWS = 2

HELP = [
    "j/k ↑/↓   show next/prev",
    "Enter l   focus the task",
    "click     show + focus",
    "n         new task",
    "r         rename",
    "x         kill task",
    "u         undock (own window)",
    "D         move to another set",
    "S         switch set",
    "s         save set (snapshot)",
    "e         edit set file",
    "a         apply set file",
    "Q         close this set",
    "?         this help",
    "",
    "anywhere: Alt+j/k next/prev",
    "prefix D dock, U undock,",
    "prefix S sets, s sidebar",
]

STATE_MARK = {"busy": "⟳", "done": "●", "quiet": "·", "bell": "!"}


def capture_screens(panes: list[str]) -> dict[str, str]:
    """Visible text of every pane, in one tmux call (per pane on failure)."""
    if not panes:
        return {}
    args: list[str] = []
    for pane in panes:
        args += ["capture-pane", "-p", "-t", pane, ";",
                 "display-message", "-p", "-t", pane, "@@corral-end #{pane_id}@@", ";"]
    try:
        out = tmux.run(*args[:-1])
    except tmux.TmuxError:
        return {p: tmux.run("capture-pane", "-p", "-t", p, check=False) for p in panes}
    screens: dict[str, str] = {}
    chunk: list[str] = []
    for line in out.split("\n"):
        if line.startswith("@@corral-end ") and line.endswith("@@"):
            screens[line[len("@@corral-end "):-2]] = "\n".join(chunk)
            chunk = []
        else:
            chunk.append(line)
    return screens


class Sidebar:
    def __init__(self, scr: "curses.window", session: str) -> None:
        self.scr = scr
        self.session = session
        self.tasks: list[core.Task] = []
        self.states: dict[str, str] = {}
        self.shown: str | None = None
        self.last_shown: str | None = None
        self.selected = 0
        self.message = ""
        self.show_help = False
        self.tracker = Tracker()
        self.row_to_task: dict[int, int] = {}

    # --- data -----------------------------------------------------------

    def refresh(self) -> None:
        self.tasks = core.tasks(self.session)
        self.shown = core.main_pane(self.session)
        if self.shown is None and self.tasks:
            core.fill_main(self.session)
            self.shown = core.main_pane(self.session)
        now = time.monotonic()
        if self.shown != self.last_shown:
            # the swap resized both panes; their reflow is not activity
            for pane in (self.shown, self.last_shown):
                if pane:
                    self.tracker.settle(pane, now)
            self.last_shown = self.shown
            index = self._index_of(self.shown)
            if index is not None:
                self.selected = index
        watched = core.session_option(self.session, "@corral_set") == "1" and self._attached()
        screens = capture_screens([t.pane for t in self.tasks])
        for t in self.tasks:
            screen_hash = zlib.crc32(screens.get(t.pane, "").encode())
            state = self.tracker.update(t.pane, screen_hash, now, shown=watched and t.pane == self.shown)
            self.states[t.pane] = "bell" if state == "quiet" and t.bell else state
        self.tracker.forget_missing({t.pane for t in self.tasks})
        self.selected = max(0, min(self.selected, len(self.tasks) - 1))

    def _attached(self) -> bool:
        return tmux.run("display-message", "-p", "-t", f"={self.session}:",
                        "#{session_attached}", check=False).strip() not in ("", "0")

    def _index_of(self, pane: str | None) -> int | None:
        return next((i for i, t in enumerate(self.tasks) if t.pane == pane), None)

    def current(self) -> core.Task | None:
        return self.tasks[self.selected] if self.tasks else None

    # --- drawing --------------------------------------------------------

    def draw(self) -> None:
        scr = self.scr
        scr.erase()
        height, width = scr.getmaxyx()
        self.row_to_task = {}
        self._put(0, 1, f"corral · {self.session}"[: width - 2], curses.A_BOLD | curses.color_pair(4))
        if self.show_help:
            for i, line in enumerate(HELP[: height - HEADER_ROWS - 1]):
                self._put(HEADER_ROWS + i, 1, line[: width - 2], 0)
        elif not self.tasks:
            self._put(HEADER_ROWS, 1, "no tasks: n = new,", curses.A_DIM)
            self._put(HEADER_ROWS + 1, 1, "e = edit set file", curses.A_DIM)
        else:
            self._draw_tasks(height, width)
        footer = self.message or "? help"
        self._put(height - 1, 1, footer[: width - 2], curses.A_DIM)
        scr.noutrefresh()
        curses.doupdate()

    def _draw_tasks(self, height: int, width: int) -> None:
        visible = max(1, (height - HEADER_ROWS - 1) // ROWS_PER_TASK)
        first = max(0, self.selected - visible + 1)
        for slot, index in enumerate(range(first, min(len(self.tasks), first + visible))):
            t = self.tasks[index]
            row = HEADER_ROWS + slot * ROWS_PER_TASK
            state = self.states.get(t.pane, "quiet")
            selected = index == self.selected
            base = curses.A_REVERSE if selected else 0
            marker = "▶" if t.pane == self.shown else " "
            name = f"{marker} {t.name}"
            self._put(row, 0, name.ljust(width - 2)[: width - 2], base | (curses.A_BOLD if t.pane == self.shown else 0))
            self._put(row, width - 2, STATE_MARK[state], base | self._state_attr(state))
            detail = f"  {t.command} · {setfile.contract_dir(t.path)}"
            self._put(row + 1, 0, detail[: width - 1], curses.A_DIM)
            self.row_to_task[row] = index
            self.row_to_task[row + 1] = index

    def _state_attr(self, state: str) -> int:
        return {
            "busy": curses.color_pair(1),
            "done": curses.color_pair(2) | curses.A_BOLD,
            "bell": curses.color_pair(3) | curses.A_BOLD,
        }.get(state, curses.A_DIM)

    def _put(self, row: int, col: int, text: str, attr: int) -> None:
        try:
            self.scr.addstr(row, col, text, attr)
        except curses.error:
            pass  # writing into the last cell of the window raises; harmless

    # --- input ----------------------------------------------------------

    def prompt(self, question: str) -> str:
        height, width = self.scr.getmaxyx()
        self.scr.move(height - 1, 0)
        self.scr.clrtoeol()
        self._put(height - 1, 0, question[: width - 1], curses.A_BOLD)
        self.scr.refresh()
        curses.echo()
        curses.curs_set(1)
        self.scr.timeout(-1)
        try:
            answer = self.scr.getstr(height - 1, min(len(question), width - 2), 200)
        finally:
            curses.noecho()
            curses.curs_set(0)
            self.scr.timeout(250)
        return answer.decode(errors="replace").strip()

    def confirm(self, question: str) -> bool:
        return self.prompt(f"{question} [y/N] ").lower() == "y"

    def client(self) -> str | None:
        return core.first_client(self.session)

    def handle(self, key: int) -> None:
        self.message = ""
        task = self.current()
        if key in (ord("j"), curses.KEY_DOWN) and self.tasks:
            self.selected = (self.selected + 1) % len(self.tasks)
            core.show(self.session, self.tasks[self.selected].pane)
        elif key in (ord("k"), curses.KEY_UP) and self.tasks:
            self.selected = (self.selected - 1) % len(self.tasks)
            core.show(self.session, self.tasks[self.selected].pane)
        elif key in (ord("l"), curses.KEY_RIGHT, 10, 13, curses.KEY_ENTER) and task:
            core.show(self.session, task.pane, focus=True)
        elif key == curses.KEY_MOUSE:
            self._mouse()
        elif key == ord("n"):
            self._new_task()
        elif key == ord("r") and task:
            name = self.prompt("rename to: ")
            if name and setfile.valid_set_name(name):
                core.rename_task(task.pane, core.unique_name(self.session, name))
            elif name:
                self.message = "names: letters, digits, . _ -"
        elif key == ord("x") and task:
            if self.confirm(f"kill {task.name}?"):
                core.kill_task(task.pane)
        elif key == ord("u") and task:
            core.undock(task.pane)
            self.message = f"{task.name} undocked"
        elif key == ord("D") and task and self.client():
            core.show_set_menu(self.client(), f"move {task.name} to", "dock", self.session, pane=task.pane)
        elif key == ord("S") and self.client():
            core.show_set_menu(self.client(), "switch set", "switch", self.session)
        elif key == ord("s"):
            core.save_snapshot(self.session)
            core.edit_in_popup(self.session, self.client())
        elif key == ord("e"):
            core.edit_in_popup(self.session, self.client())
        elif key == ord("a"):
            problems = core.ensure_set(self.session)
            self.message = problems[0] if problems else "set file applied"
        elif key == ord("Q"):
            if self.confirm(f"close set {self.session} and kill its tasks?"):
                core.close_set(self.session)
        elif key == ord("?"):
            self.show_help = not self.show_help

    def _mouse(self) -> None:
        try:
            _, _, row, _, state = curses.getmouse()
        except curses.error:
            return
        if state & curses.BUTTON4_PRESSED and self.tasks:
            self.handle(ord("k"))
        elif state & getattr(curses, "BUTTON5_PRESSED", 0) and self.tasks:
            self.handle(ord("j"))
        elif state & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED | curses.BUTTON1_RELEASED):
            index = self.row_to_task.get(row)
            if index is not None:
                self.selected = index
                core.show(self.session, self.tasks[index].pane, focus=True)

    def _new_task(self) -> None:
        name = self.prompt("name: ")
        if not name:
            return
        if not setfile.valid_set_name(name):
            self.message = "names: letters, digits, . _ -"
            return
        shown = self.tasks[self._index_of(self.shown)] if self._index_of(self.shown) is not None else None
        default_dir = setfile.contract_dir(shown.path) if shown else "~"
        directory = self.prompt(f"dir [{default_dir}]: ") or default_dir
        command = self.prompt("command (empty = shell): ")
        pane = core.add_task(self.session, core.unique_name(self.session, name), directory, command)
        core.show(self.session, pane, focus=True)


def _main(scr: "curses.window", session: str) -> None:
    curses.curs_set(0)
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_YELLOW, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    curses.init_pair(4, curses.COLOR_MAGENTA, -1)
    curses.mousemask(curses.ALL_MOUSE_EVENTS)
    curses.mouseinterval(0)
    scr.keypad(True)
    scr.timeout(250)
    if os.environ.get("TMUX_PANE"):
        tmux.run("select-pane", "-t", os.environ["TMUX_PANE"], "-T", f"corral · {session}", check=False)

    bar = Sidebar(scr, session)
    last_refresh = 0.0
    while True:
        if time.monotonic() - last_refresh >= REFRESH_SECONDS:
            try:
                bar.refresh()
            except tmux.TmuxError as err:
                bar.message = str(err)[:60]
            last_refresh = time.monotonic()
        bar.draw()
        key = scr.getch()
        if key == -1 or key == curses.KEY_RESIZE:
            continue
        try:
            bar.handle(key)
        except tmux.TmuxError as err:
            bar.message = str(err)[:60]
        last_refresh = 0.0


def run(session: str) -> None:
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(_main, session)
