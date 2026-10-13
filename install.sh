#!/usr/bin/env bash
# Installs corral: a `corral` link in ~/.local/bin and an example set file.
# Everything else stays in this checkout; uninstall.sh removes what this adds.
set -euo pipefail

for arg in "$@"; do
    case "$arg" in
        -h|--help)
            echo "Usage: ./install.sh"
            echo ""
            echo "Link bin/corral into ~/.local/bin and create ~/.config/corral/sets/"
            echo "with an example set if there are no sets yet."
            echo ""
            echo "Options:"
            echo "  -h, --help   Show this help"
            echo ""
            echo "Examples:"
            echo "  ./install.sh"
            exit 0
            ;;
        *)
            echo "error: unknown argument '$arg' (see -h)" >&2
            exit 1
            ;;
    esac
done

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
SETS_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/corral/sets"

command -v tmux >/dev/null || { echo "error: tmux not found (sudo apt install tmux)" >&2; exit 2; }
[ -x /usr/bin/python3 ] || { echo "error: /usr/bin/python3 not found" >&2; exit 2; }
/usr/bin/python3 -c 'import curses' 2>/dev/null || { echo "error: python3 curses missing" >&2; exit 2; }
version="$(tmux -V | grep -oE '[0-9]+\.[0-9]+' | head -1)"
if [ "$(printf '%s\n3.3\n' "$version" | sort -V | head -1)" != "3.3" ]; then
    echo "error: tmux $version is too old, corral needs 3.3+" >&2
    exit 2
fi
command -v xclip >/dev/null || echo "note: xclip not found; copy-mode yank to clipboard will not work"

mkdir -p "$BIN_DIR" "$SETS_DIR"
ln -sfn "$REPO/bin/corral" "$BIN_DIR/corral"
echo "Linked: $BIN_DIR/corral -> $REPO/bin/corral"

if [ -z "$(ls -A "$SETS_DIR")" ]; then
    cat > "$SETS_DIR/main.conf" <<'SET'
# corral set file: one task per line.
# name   directory   command (rest of the line; empty = just a shell)
shell    ~
SET
    echo "Created example set: $SETS_DIR/main.conf"
fi

echo ""
echo "Suggested i3 bindings (~/.config/i3/config):"
echo "  bindsym \$mod+Return exec corral term                  # dockable terminal"
echo "  bindsym \$mod+t exec corral window                     # go to the corral (open it if none)"
echo "  for_window [window_role=\"^corral\$\"] move container to workspace corral, workspace corral"
