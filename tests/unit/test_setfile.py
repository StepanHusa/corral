from corral import setfile
from corral.setfile import Entry


def test_parse_keeps_command_spaces_and_skips_comments():
    text = "# header\n\nmon  ~  watch -n 1 'date +%T'\nshell  /tmp\n"
    entries, problems = setfile.parse(text)
    assert entries == [Entry("mon", "~", "watch -n 1 'date +%T'"), Entry("shell", "/tmp", "")]
    assert problems == []


def test_parse_reports_bad_lines_but_keeps_the_good_ones():
    text = "lonely\nok ~ ls\nok ~ again\nbad/name ~\n"
    entries, problems = setfile.parse(text)
    assert entries == [Entry("ok", "~", "ls")]
    assert [p.split(":")[0] for p in problems] == ["line 1", "line 3", "line 4"]


def test_format_then_parse_round_trips():
    entries = [Entry("agent-1", "~/Claude", "claude --continue"), Entry("x", "/", "")]
    parsed, problems = setfile.parse(setfile.format_entries(entries))
    assert parsed == entries and problems == []


def test_sets_live_under_xdg_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    setfile.save("school", [Entry("a", "~")])
    assert setfile.set_path("school") == tmp_path / "corral" / "sets" / "school.conf"
    assert setfile.available_sets() == ["school"]


def test_contract_and_expand_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "proj").mkdir()
    assert setfile.contract_dir(str(tmp_path / "proj")) == "~/proj"
    assert setfile.expand_dir("~/proj") == str(tmp_path / "proj")
    assert setfile.expand_dir("~/missing") == str(tmp_path)  # falls back to home
