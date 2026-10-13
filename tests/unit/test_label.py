from pathlib import Path

from corral.label import describe, fit, title_topic

HOME = str(Path.home())


def test_idle_shell_is_named_by_its_directory():
    assert describe([], "zsh", HOME + "/Claude", "husas@host:~/Claude") == ("~/Claude", "shell")


def test_claude_is_named_by_its_conversation_topic():
    argv = ["node", "/home/x/.local/bin/claude", "--continue"]
    label, detail = describe(argv, "claude", HOME + "/Claude", "✳ Higher-order Arnold tongue paths")
    assert label == "Higher-order Arnold tongue paths"
    assert detail == "claude · ~/Claude"


def test_claude_without_a_title_falls_back_to_its_name():
    assert describe(["claude"], "claude", HOME, "")[0] == "claude"


def test_program_label_shows_the_file_it_works_on(tmp_path):
    (tmp_path / "TODO.md").write_text("")
    label, detail = describe(["nvim", "-p", "TODO.md"], "nvim", str(tmp_path), "")
    assert (label, detail) == ("nvim TODO.md", str(tmp_path))


def test_flag_values_are_not_taken_for_files(tmp_path):
    assert describe(["top", "-d", "1"], "top", str(tmp_path), "")[0] == "top"


def test_script_run_by_an_interpreter_is_named_by_the_script():
    assert describe(["/usr/bin/python3", "monitor.py"], "python3", HOME, "")[0] == "monitor"


def test_unreadable_process_falls_back_to_tmux_command():
    assert describe(None, "top", HOME, "") == ("top", "~")
    assert describe(None, "zsh", HOME, "") == ("~", "shell")


def test_title_topic_keeps_titles_without_a_glyph():
    assert title_topic("Plain title") == "Plain title"
    assert title_topic("✻ Working on it") == "Working on it"


def test_fit_marks_the_cut():
    assert fit("abcdef", 4) == "abc…"
    assert fit("abc", 4) == "abc"
