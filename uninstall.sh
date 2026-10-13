#!/usr/bin/env bash
# Removes what install.sh added. Set files and state are kept (printed below).
set -euo pipefail

for arg in "$@"; do
    case "$arg" in
        -h|--help)
            echo "Usage: ./uninstall.sh"
            echo ""
            echo "Remove the ~/.local/bin/corral link. If corral's tmux server is"
            echo "running it is left alone: stop it first with 'corral stop'."
            echo "Set files and state are kept; the paths are printed."
            echo ""
            echo "Options:"
            echo "  -h, --help   Show this help"
            echo ""
            echo "Examples:"
            echo "  corral stop && ./uninstall.sh"
            exit 0
            ;;
        *)
            echo "error: unknown argument '$arg' (see -h)" >&2
            exit 1
            ;;
    esac
done

if tmux -L corral list-sessions >/dev/null 2>&1; then
    echo "note: corral's tmux server is still running; 'corral stop' kills it and its tasks"
fi
rm -f "$HOME/.local/bin/corral"
echo "Removed: $HOME/.local/bin/corral"
echo ""
echo "Kept (remove manually if you want):"
echo "  rm -rf ${XDG_CONFIG_HOME:-$HOME/.config}/corral      # your set files"
echo "  rm -rf ${XDG_STATE_HOME:-$HOME/.local/state}/corral  # last set, sidebar.log"
echo "Also undo the i3 bindings that call corral, if you added them."
