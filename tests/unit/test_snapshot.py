from corral import snapshot


def fake_proc(tmp_path, shell_pid, tpgid, argv=None):
    (tmp_path / str(shell_pid)).mkdir()
    # comm with a space and ')' to prove the parser splits on the last ')'
    (tmp_path / str(shell_pid) / "stat").write_text(
        f"{shell_pid} (z sh)) S 1 {shell_pid} {shell_pid} 34816 {tpgid} 4194304 0 0\n")
    if argv is not None:
        (tmp_path / str(tpgid)).mkdir()
        (tmp_path / str(tpgid) / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")


def test_idle_shell_has_no_foreground_command(tmp_path):
    fake_proc(tmp_path, 10, 10)
    assert snapshot.foreground_argv(10, proc=tmp_path) == []


def test_foreground_program_argv_is_read(tmp_path):
    fake_proc(tmp_path, 10, 42, ["python3", "train.py", "--epochs", "50"])
    assert snapshot.foreground_argv(10, proc=tmp_path) == ["python3", "train.py", "--epochs", "50"]


def test_vanished_pane_is_unreadable(tmp_path):
    assert snapshot.foreground_argv(999, proc=tmp_path) is None


def test_claude_via_node_restarts_with_continue():
    argv = ["node", "/home/u/.local/lib/claude", "--model", "opus"]
    assert snapshot.normalize(argv) == "claude --continue --model opus"


def test_claude_resume_is_kept_as_is():
    assert snapshot.normalize(["claude", "--resume", "abc"]) == "claude --resume abc"


def test_system_paths_are_shortened_and_args_quoted():
    assert snapshot.normalize(["/usr/bin/watch", "-n", "1", "date +%T"]) == "watch -n 1 'date +%T'"
    assert snapshot.normalize(["/opt/x/run"]) == "/opt/x/run"
