"""Integration tests against a real, throwaway tmux server (own socket)."""

import os
import subprocess
import time
import uuid

import pytest

from corral import core, setfile, tmux
from corral.setfile import Entry


@pytest.fixture(autouse=True)
def corral_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRAL_SOCKET", f"corral-test-{uuid.uuid4().hex[:8]}")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("CORRAL_NO_TERMINAL", "1")
    monkeypatch.delenv("TMUX", raising=False)
    yield
    tmux.run("kill-server", check=False)


def view_tasks(session):
    side = core.sidebar_pane(session)
    view = core.pane_info(side, "#{window_id}")
    rows = tmux.lines("list-panes", "-t", view, "-F", "#{pane_id}\t#{@corral_task}")
    return [r[1] if len(r) > 1 else "" for r in rows]


def names(session):
    return [t.name for t in core.tasks(session)]


def test_open_starts_file_tasks_and_shows_the_first(tmp_path):
    setfile.save("work", [Entry("one", "~"), Entry("two", str(tmp_path), "echo hi")])
    assert core.ensure_set("work") == []
    assert names("work") == ["one", "two"]
    assert view_tasks("work") == ["", "one"]  # sidebar + shown task
    assert core.tasks("work")[1].path == str(tmp_path)


def test_reopening_a_set_only_starts_what_is_missing():
    setfile.save("work", [Entry("one", "~")])
    core.ensure_set("work")
    pane_before = core.tasks("work")[0].pane
    setfile.save("work", [Entry("one", "~"), Entry("new", "~")])
    core.ensure_set("work")
    assert names("work") == ["one", "new"]
    assert core.tasks("work")[0].pane == pane_before  # the running one was kept


def test_step_cycles_through_tasks_in_order():
    setfile.save("work", [Entry("a", "~"), Entry("b", "~"), Entry("c", "~")])
    core.ensure_set("work")
    seen = []
    for _ in range(4):
        core.step("work", 1)
        seen.append(view_tasks("work")[1])
    assert seen == ["b", "c", "a", "b"]


def test_dock_moves_a_loose_terminal_in_and_its_session_vanishes():
    core.ensure_set("work")
    loose = tmux.run("new-session", "-d", "-P", "-F", "#{session_name}", "-c", "/tmp").strip()
    tmux.run("set-option", "-t", f"={loose}:", "@corral_loose", "1")
    pane = tmux.run("display-message", "-p", "-t", f"={loose}:", "#{pane_id}").strip()
    pid = core.pane_info(pane, "#{pane_pid}")
    for _ in range(50):  # until the pane's shell has started
        if core.pane_info(pane, "#{pane_current_command}") in core.SHELLS:
            break
        time.sleep(0.1)

    core.dock(pane, "work")

    assert not tmux.has_session(loose)
    assert names("work") == ["tmp"]  # named after its directory
    assert core.pane_info(pane, "#{pane_pid}") == pid  # same process, just moved
    assert view_tasks("work")[1] == "tmp"


def test_undock_keeps_the_process_and_survives_until_attached():
    setfile.save("work", [Entry("agent", "~", "sleep 300")])
    core.ensure_set("work")
    task = core.tasks("work")[0]

    loose = core.undock(task.pane)
    core.reap_loose()  # its terminal has not attached yet: must not be killed

    assert tmux.has_session(loose)
    assert core.pane_info(task.pane, "#{session_name}") == loose
    assert core.pane_info(task.pane, "#{pane_pid}") == str(task.pid)
    assert names("work") == []


def test_closed_loose_window_is_reaped():
    core.ensure_set("work")
    loose = tmux.run("new-session", "-d", "-P", "-F", "#{session_name}").strip()
    tmux.run("set-option", "-t", f"={loose}:", "@corral_loose", "1")
    env = {k: v for k, v in os.environ.items() if k != "TMUX"}
    client = subprocess.Popen(tmux.base_cmd() + ["-C", "attach", "-t", f"={loose}"],
                              stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, env=env)
    time.sleep(0.5)
    client.stdin.close()  # the "window" closes: the client detaches
    client.wait(timeout=5)
    core.reap_loose()
    assert not tmux.has_session(loose)


def test_snapshot_records_the_foreground_command(tmp_path):
    setfile.save("work", [Entry("sleeper", str(tmp_path), "sleep 300")])
    core.ensure_set("work")
    for _ in range(50):  # the shell needs a moment to start the command
        if core.snapshot_entries("work")[0].command:
            break
        time.sleep(0.1)
    assert core.snapshot_entries("work") == [Entry("sleeper", setfile.contract_dir(str(tmp_path)), "sleep 300")]
