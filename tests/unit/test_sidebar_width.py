from corral.sidebar import MIN_TASK_COLUMNS, plan_width

MIN = 23


def test_window_growing_back_restores_the_chosen_width():
    # tmux gave the sidebar part of the new space (23 -> 31); undo that
    assert plan_width(31, 200, last_window=120, chosen=23, minimum=MIN) == (23, 23)


def test_dragging_the_border_wider_is_remembered():
    assert plan_width(40, 200, last_window=200, chosen=23, minimum=MIN) == (40, 40)
    # and survives the window being resized later
    assert plan_width(33, 160, last_window=200, chosen=40, minimum=MIN) == (40, 40)


def test_dragging_below_the_minimum_snaps_back():
    assert plan_width(12, 200, last_window=200, chosen=30, minimum=MIN) == (MIN, MIN)


def test_a_narrow_window_keeps_room_for_the_task_but_not_the_choice():
    width, chosen = plan_width(23, 50, last_window=200, chosen=40, minimum=MIN)
    assert width == 50 - MIN_TASK_COLUMNS - 1
    assert chosen == 40  # back to 40 once the window is wide again
