# corral

One place for your long-running terminals: a sidebar of tasks (agents,
monitors, editors, shells) on the left, one task shown full size on the
right, and every other window on your desktop stays clean.

- **Sets** of tasks (say *work*, *school*, *own projects*), one visible at a
  time. A set is a small text file; reopening it starts what is missing.
- **Done marks**: a task that was busy and went quiet while you were not
  looking gets a green `●`. Made for coding agents like Claude Code: start
  several, and come back when one waits for you.
- **Docking**: a terminal opened with `corral term` looks like any other
  window, and can be moved into a set (and back out) with its processes
  untouched.
- **Isolated**: corral runs on its own tmux server (`tmux -L corral`) with its
  own config, so your normal tmux, its plugins and its sessions never see it.

```
┌─ corral window ──────────────────────────────────────────┐
│ corral · school │                                         │
│ ▶ mymonitor  ◐  │                                         │
│   ~             │     the shown task, full size           │
│   Fix parser ●  │     (a real, live terminal)             │
│   claude · ~/C… │                                         │
│   ~/Notes    ○  │                                         │
│   shell         │                                         │
└─────────────────┴─────────────────────────────────────────┘
```

## Why

Desktop window managers have no "list on the left, one task on the right"
layout: i3's stacked layout puts titles on top and shows no status, and
compositor overviews (Hyprland's master layout, expo plugins) tile live
windows instead of listing them. tmux already has every part (panes that can
move between windows without their processes noticing, screen capture,
menus), so corral is a small layer on a private tmux server that works under
any window manager.

## Install

Linux only. Needs tmux ≥ 3.3, Python ≥ 3.10 at `/usr/bin/python3` (standard
library only, with curses), and a terminal emulator (xfce4-terminal by
default, see [Terminal](#terminal)). xclip is optional, for copying to the
clipboard.

```sh
git clone https://github.com/StepanHusa/corral.git
cd corral
./install.sh        # links ~/.local/bin/corral, creates ~/.config/corral/sets/
./uninstall.sh      # removes the link; set files are kept
```

Then `corral open` in any terminal opens the default set.

### i3 (optional)

```
bindsym $mod+Return exec corral term     # terminals that can be docked
bindsym $mod+t exec corral window        # go to the corral workspace (opens it if needed)
for_window [window_role="^corral$"] move container to workspace corral, workspace corral
```

The corral window has the window role `corral`; the rule keeps it on its own
workspace, and `corral window` raises it there instead of opening another.

### Terminal

corral opens windows for `corral term`, undocked tasks and the corral window
itself. The commands come from environment variables; the tmux command line
is appended to them:

| Variable | Default | Used for |
|---|---|---|
| `CORRAL_TERMINAL` | `xfce4-terminal -x` | `corral term`, undocked tasks |
| `CORRAL_SET_TERMINAL` | `xfce4-terminal --role=corral -x` | the corral window |

For example `CORRAL_TERMINAL="kitty"` and
`CORRAL_SET_TERMINAL="kitty --class corral"` (then match `class` instead of
`window_role` in the i3 rule), or `alacritty -e` / `alacritty --class corral -e`.

## Use

| Command | |
|---|---|
| `corral open [SET]` | open a set in this terminal (default: the last one); creates it if new, starts tasks from its file that are not running |
| `corral window [SET]` | go to corral's window (and its i3 workspace); opens it if there is none |
| `corral term [DIR [CMD…]]` | new terminal window that looks plain but can be docked; CMD is typed into its shell |
| `corral run [--set SET] DIR [CMD…]` | start CMD as a new task of a set (default: the last one) and show it |
| `corral sets` | list sets (`*` = running) |
| `corral save [SET]` | snapshot what a set runs now into its set file |
| `corral edit [SET]` / `apply SET` | edit a set file / start what is missing |
| `corral close SET` / `stop` | kill one set / corral's whole server |

For example, a launcher entry that starts an agent straight into the corral:
`corral run ~/project claude`.

### Keys

The prefix is Ctrl+Space.

| Where | Key | |
|---|---|---|
| anywhere in a set | Alt+j / Alt+k (Alt+↓/↑) | show next / previous task, focused |
| | Alt+← / Alt+→ | focus sidebar / task |
| | prefix n / p | show next / previous task |
| | prefix c | new shell in this directory |
| | prefix b | hide / show the sidebar |
| | prefix s | focus the sidebar |
| | prefix S | switch set (menu) |
| any corral pane | prefix D | dock this pane into a set (menu) |
| | prefix U | undock this task into its own window |
| sidebar | j/k, ↑/↓, wheel | show next / previous (focus stays in the sidebar) |
| | Enter, l, click | show and focus the task |
| | n r x | new shell (in the shown task's directory) / label by hand / kill task |
| | h | hide the sidebar |
| | u D | undock / move to another set |
| | S s e a Q | switch set / save snapshot / edit file / apply file / close set |
| | ? | help |

Copy mode works as usual: prefix `[`, `v` or Space to select, `y` to copy
to the clipboard. tmux's own window and session keys (prefix 0–9, w, f, ',
(, ), L, ., &, $) are removed: they would show a parked task without the
sidebar.

### The sidebar

Labels come from what runs, nothing has to be typed: an idle shell shows its
directory, a program its name and the file it works on (`nvim TODO.md`),
Claude Code the topic from its terminal title. `r` sets a label by hand
(empty goes back to automatic).

Marks: spinning `◐` busy (the screen or title changed in the last 2 s),
`●` done (was busy, went quiet while you were not looking; clears when
shown), `▲` bell, `○` quiet. They come from the screen, so they work for any
program; a constantly updating monitor is always busy.

The sidebar is at least `@corral_sidebar_width` columns wide (23, set in
`tmux.conf`); drag its border to widen it. Hiding it zooms the shown task,
and Alt+j/k keep it hidden.

## Set files

`~/.config/corral/sets/<set>.conf`, one task per line:

```
# name     directory    command (rest of the line; empty = just a shell)
monitor    ~            htop
agent-1    ~/project    claude --continue
notes      ~/Notes      nvim TODO.md
```

The command is **typed into a shell**, as if you typed it: aliases work, it
lands in history, and when it exits you are left in a shell in that
directory. Opening a set starts only the tasks that are not running, so it
is safe to reopen. `corral save` writes the file from what runs now: the
directory and the foreground program's full command line; `claude` gets
`--continue` added so it resumes instead of starting fresh. Tidy it after.

## How it works

- **set** = tmux session marked `@corral_set`. Its first window is the
  *view*: the sidebar pane (`@corral_sidebar`) left, the shown task right.
- **task** = pane marked `@corral_task=<name>`, ordered by `@corral_order`.
  Tasks not shown are parked one per hidden window (the status bar is off).
  Showing a task is `swap-pane` with the shown one, so processes never
  notice. If the shown task exits, the sidebar shows the first one.
- **loose** = session marked `@corral_loose`: a `corral term` window or an
  undocked task. Closing the window detaches its client; the
  `client-detached` hook runs `corral reap`, which kills loose sessions that
  were attached once and now have no client, so closing the window ends the
  task like in a normal terminal. Docking moves the pane into a set; the
  loose session is left empty, tmux destroys it and the window closes.
- The sidebar (`corral/sidebar.py`, curses) polls twice a second: the task
  list and one batched `capture-pane` of every task (hashes feed
  `status.py`). It runs in a restart loop; crashes go to
  `~/.local/state/corral/sidebar.log`. Showing a task from elsewhere
  (Alt+j/k) sends the sidebar SIGUSR1 (pid in the pane option
  `@corral_sidebar_pid`) so it redraws at once.
- Menus are tmux's own `display-menu`, so they work from any pane. The pane
  and client a menu is about are passed through global options
  (`@corral_menu_pane/client`): pane ids start with `%`, which
  `command-prompt` would eat as a placeholder.

Code: `tmux.py` (calls to the private server), `setfile.py`, `status.py`,
`label.py` (sidebar labels), `snapshot.py` (foreground process from
`/proc`), `core.py` (all pane moves), `sidebar.py`, `cli.py`.

## Limits

- Docking works between windows of corral's server only (tmux cannot move a
  process between servers): a plain terminal, or one in your normal tmux,
  cannot be docked. That is why `corral term` exists.
- No hover-to-switch (terminals get clicks, not hover).
- Nothing survives a reboot except set files: reopening a set restarts its
  commands (`claude --continue` resumes the conversation, not the turn).
- Alt+j/k are taken from programs running inside corral.

## Tests

```sh
/usr/bin/python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest -q        # integration tests use a throwaway tmux socket
```

## License

MIT, see [LICENSE](LICENSE).
