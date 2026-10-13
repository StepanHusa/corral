"""Task activity states, derived from how a pane's screen changes over time.

Works for any program, not just agents: the sidebar hashes every task's
visible screen about once a second and feeds the hashes in here.

    busy   the screen changed within the last BUSY_SECONDS
    done   it was busy, went quiet while you were not looking at it
           (the "agent finished, come answer it" signal); clears once shown
    quiet  nothing happening
"""

from dataclasses import dataclass

BUSY_SECONDS = 3.0
STARTUP_SECONDS = 8.0  # a new pane drawing its first prompt is not "activity"


@dataclass
class _PaneState:
    last_hash: int | None = None
    last_change: float = float("-inf")
    was_busy: bool = False
    done: bool = False
    ignore_until: float = float("-inf")


class Tracker:
    def __init__(self) -> None:
        self._panes: dict[str, _PaneState] = {}

    def settle(self, pane: str, now: float, seconds: float = 1.5) -> None:
        """Ignore screen changes for a moment, e.g. the reflow after a resize."""
        st = self._state(pane, now)
        st.ignore_until = max(st.ignore_until, now + seconds)

    def _state(self, pane: str, now: float) -> _PaneState:
        st = self._panes.get(pane)
        if st is None:
            st = self._panes[pane] = _PaneState(ignore_until=now + STARTUP_SECONDS)
        return st

    def update(self, pane: str, screen_hash: int, now: float, shown: bool) -> str:
        st = self._state(pane, now)
        if st.last_hash is not None and screen_hash != st.last_hash and now >= st.ignore_until:
            st.last_change = now
        st.last_hash = screen_hash

        busy = now - st.last_change < BUSY_SECONDS
        if busy:
            st.was_busy = True
        elif st.was_busy:
            st.was_busy = False
            if not shown:
                st.done = True
        if shown:
            st.done = False

        if busy:
            return "busy"
        return "done" if st.done else "quiet"

    def forget_missing(self, alive: set[str]) -> None:
        for pane in list(self._panes):
            if pane not in alive:
                del self._panes[pane]
