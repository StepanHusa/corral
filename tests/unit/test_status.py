from corral.status import BUSY_SECONDS, STARTUP_SECONDS, Tracker

T0 = 100.0
AFTER_STARTUP = T0 + STARTUP_SECONDS + 1


def feed(tracker, hashes, start, shown=False, pane="%1"):
    """Feed one hash per second; return the last state."""
    state = None
    for i, h in enumerate(hashes):
        state = tracker.update(pane, h, start + i, shown)
    return state


def test_new_pane_drawing_its_prompt_is_not_activity():
    tr = Tracker()
    assert feed(tr, [1, 2, 3, 3, 3], T0) == "quiet"


def test_unseen_task_that_goes_quiet_is_done_until_shown():
    tr = Tracker()
    feed(tr, [1], T0)
    assert feed(tr, [2, 3, 4], AFTER_STARTUP) == "busy"
    quiet_at = AFTER_STARTUP + 3 + BUSY_SECONDS
    assert tr.update("%1", 4, quiet_at, shown=False) == "done"
    assert tr.update("%1", 4, quiet_at + 1, shown=False) == "done"
    assert tr.update("%1", 4, quiet_at + 2, shown=True) == "quiet"


def test_task_watched_while_it_finishes_is_not_done():
    tr = Tracker()
    feed(tr, [1], T0)
    feed(tr, [2, 3], AFTER_STARTUP, shown=True)
    assert tr.update("%1", 3, AFTER_STARTUP + 2 + BUSY_SECONDS, shown=True) == "quiet"


def test_settle_hides_resize_reflow():
    tr = Tracker()
    feed(tr, [1], T0)
    tr.settle("%1", AFTER_STARTUP)
    assert tr.update("%1", 99, AFTER_STARTUP + 0.5, shown=False) == "quiet"
