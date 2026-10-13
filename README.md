# corral

Task sets for terminals: a sidebar of running tasks (agents, monitors,
shells) with one task shown full size, sets of tasks you can reopen with one
command, and docking of ordinary terminal windows into a set and back out.

It runs on **its own tmux server** (`tmux -L corral`, config `tmux.conf` in
this repo), so the normal tmux setup (`~/.tmux.conf`, resurrect, plugins)
never sees it, and it does not leak into other terminals.

```
┌─ one terminal window: `corral open school` ──────────────┐
│ corral · school │                                         │
│ ▶ mymonitor  ◐  │                                         │
│   ~             │     the shown task, full size           │
│   Fix parser ●  │     (a real, live pane)                 │
│   claude · ~/C… │                                         │
│   ~/Notes    ○  │                                         │
│   shell         │                                         │
└─────────────────┴─────────────────────────────────────────┘
```

## Install

```sh
./install.sh        # links ~/.local/bin/corral, creates ~/.config/corral/sets/
./uninstall.sh      # removes the link; set files are kept
```

Needs tmux ≥ 3.3, `/usr/bin/python3` (stdlib only, curses), xfce4-terminal
(override with `CORRAL_TERMINAL`, e.g. `CORRAL_TERMINAL="kitty --"`), xclip
for clipboard yank.

i3:
```
bindsym $mod+Return exec corral term                  # dockable terminal
bindsym $mod+t exec corral window                     # go to the corral (open it if none)
for_window [window_role="^corral$"] move container to workspace corral, workspace corral
```

## Use

| Command | |
|---|---|
| `corral open [SET]` | open a set in this terminal (default: the last one); creates it if new, starts tasks from its file that are not running |
| `corral window [SET]` | go to corral's window and its i3 workspace; opens it (window role `corral`, terminal from `CORRAL_SET_TERMINAL`) if there is none |
| `corral term [DIR [CMD…]]` | new terminal window that looks plain but can be docked; CMD is typed into its shell (`corral term ~/Claude claude`) |
| `corral run [--set SET] DIR [CMD…]` | start CMD as a new task of a set (default: the last one) and show it, in corral's window like `corral window` |
| `corral sets` | list sets (`*` = running) |
| `corral save [SET]` | snapshot what a set runs now into its set file |
| `corral edit [SET]` / `apply SET` | edit a set file / start what is missing |
| `corral close SET` / `stop` | kill one set / corral's whole server |

Keys (prefix = Ctrl+Space, like `~/.tmux.conf`):

| Where | Key | |
|---|---|---|
| anywhere in a set | Alt+j / Alt+k (Alt+↓/↑) | show next / previous task, focused |
| | Alt+← / Alt+→ | focus sidebar / task |
| | prefix n / p | show next / previous task |
| | prefix c | new shell in this directory |
| any corral pane | prefix D | dock this pane into a set (menu) |
| | prefix U | undock this task into its own window |
| | prefix S | switch set (menu) |
| | prefix s | focus the sidebar |
| | prefix b | hide / show the sidebar |
| sidebar | j/k, ↑/↓, wheel | show next / previous (focus stays in sidebar) |
| | Enter, l, click | show and focus the task |
| | n r x | new shell (shown task's dir) / label by hand / kill task |
| | h | hide the sidebar (prefix b or prefix s brings it back) |
| | u D | undock / move to another set |
| | S s e a Q | switch set / save snapshot / edit file / apply file / close set |
| | ? | help |

Sidebar labels are derived from what runs, nothing is typed: an idle shell
shows its directory, a program its name and the file it works on
(`nvim TODO.md`), Claude Code the topic from its terminal title. `r` sets a
label by hand (empty goes back to automatic). The sidebar has a minimum
width, `@corral_sidebar_width` in `tmux.conf` (23 columns, about 200 px);
drag its border to make it wider. Hiding it zooms the shown task; Alt+j/k
keep it hidden.
The selected row is gray with white text.

tmux's own window and session keys (prefix 0–9, w, f, ', (, ), L, ., &, $)
are removed: they would show a parked task without the sidebar.

Sidebar marks: spinning `◐` (yellow) busy (screen changed in the last 3 s),
`●` (green) done (was busy, went quiet while you were not looking; clears
when shown), `▲` (red) bell, `○` quiet. These come from the screen, so they
work for any program; a constantly updating monitor is always busy.

## Set files

`~/.config/corral/sets/<set>.conf`, one task per line:

```
# name     directory    command (rest of the line; empty = just a shell)
monitor    ~            mymonitor
agent-1    ~/Claude     claude --continue
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
  Tasks not shown are parked one per hidden window (status bar is off).
  Showing a task is `swap-pane` with the shown one, so processes never
  notice. If the shown task exits, the sidebar shows the first one.
- **loose** = session marked `@corral_loose`: a `corral term` window or an
  undocked task. Closing the window detaches its client; the
  `client-detached` hook runs `corral reap`, which kills loose sessions that
  were attached once and now have no client — so closing the window ends the
  task, like a normal terminal. Docking moves the pane into a set; the loose
  session is left empty, tmux destroys it and the window closes by itself.
- The sidebar (`corral/sidebar.py`, curses) polls once a second: task list,
  one batched `capture-pane` of every task (hashes feed `status.py`).
  It runs in a restart loop; crashes go to `~/.local/state/corral/sidebar.log`.
  Showing a task from elsewhere (Alt+j/k) sends the sidebar SIGUSR1 (pid in
  the pane option `@corral_sidebar_pid`) so it redraws at once.
- Menus are tmux's own `display-menu`, so they work from any pane. The pane
  and client a menu is about are passed through global options
  (`@corral_menu_pane/client`): pane ids start with `%`, which
  `command-prompt` would eat as a placeholder.

Code: `tmux.py` (calls to the private server), `setfile.py`, `status.py`,
`snapshot.py` (foreground process from `/proc`), `core.py` (all pane moves),
`sidebar.py`, `cli.py`. History of the idea: `docs/brainstorm.md`.

## Limits

- Docking works between windows of corral's server only (tmux cannot move a
  process between servers): a plain terminal or one in the normal tmux
  cannot be docked. That is why `Mod+Return` opens `corral term`.
- No hover-to-switch (terminals get clicks, not hover).
- Nothing survives a reboot except set files: reopening a set restarts its
  commands (`claude --continue` resumes the conversation, not the turn).
- Alt+j/k are taken from programs inside corral.

## Tests

```sh
/usr/bin/python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest -q        # integration tests use a throwaway tmux socket
```
