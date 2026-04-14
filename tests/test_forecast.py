"""Unit tests for server.forecast — the queue packing engine."""

from __future__ import annotations

from datetime import datetime

from server.forecast import (
    OverrideRange,
    WorkItem,
    build_forecast,
)


def _cells_weekday_night() -> list[tuple[int, int]]:
    # Mon-Fri (weekday 0..4), 22:00 + 23:00 = two hours/night.
    out = []
    for dow in range(5):
        for hour in (22, 23):
            out.append((dow, hour))
    return out


def test_single_item_fits_in_first_window():
    # Monday 20:00 — next window opens at 22:00 for 2h.
    now = datetime(2026, 4, 13, 20, 0, 0)  # Mon
    plan = build_forecast(
        now=now,
        horizon_days=3,
        cells=_cells_weekday_night(),
        overrides=[],
        work=[
            WorkItem(
                kind="vulnerability",
                id=1,
                project_id=1,
                project_name="demo",
                title="SQLi",
                hours_remaining=1.5,
                priority=20,
            )
        ],
    )
    assert plan.windows[0].start_at.hour == 22
    assert len(plan.windows[0].assignments) == 1
    a = plan.windows[0].assignments[0]
    assert a.hours == 1.5
    assert not a.continues_into_next_window
    assert plan.unscheduled == []


def test_item_spills_into_next_window():
    now = datetime(2026, 4, 13, 20, 0, 0)  # Mon 20:00
    plan = build_forecast(
        now=now,
        horizon_days=3,
        cells=_cells_weekday_night(),
        overrides=[],
        work=[
            WorkItem(
                kind="vulnerability",
                id=1,
                project_id=1,
                project_name="demo",
                title="Big auth rewrite",
                hours_remaining=3.0,
                priority=25,
            )
        ],
    )
    # Should get 2h in Mon 22-00 window and 1h in Tue 22-23 window.
    assert len(plan.windows) >= 2
    first = plan.windows[0].assignments[0]
    second = plan.windows[1].assignments[0]
    assert first.hours == 2.0
    assert first.continues_into_next_window
    assert second.hours == 1.0
    assert second.continued_from_prior_window


def test_priority_order_beats_insertion_order():
    now = datetime(2026, 4, 13, 20, 0, 0)
    plan = build_forecast(
        now=now,
        horizon_days=3,
        cells=_cells_weekday_night(),
        overrides=[],
        work=[
            WorkItem(kind="vulnerability", id=1, project_id=1, project_name="p",
                     title="low",  hours_remaining=1.0, priority=5),
            WorkItem(kind="vulnerability", id=2, project_id=1, project_name="p",
                     title="high", hours_remaining=1.0, priority=25),
        ],
    )
    first_assign = plan.windows[0].assignments[0]
    assert first_assign.item_id == 2  # high priority scheduled first


def test_blocked_override_wins_over_general_cell():
    now = datetime(2026, 4, 13, 20, 0, 0)  # Mon
    # User blocks Monday night for a deadline.
    overrides = [
        OverrideRange(
            start_at=datetime(2026, 4, 13, 22, 0, 0),
            end_at=datetime(2026, 4, 14, 0, 0, 0),
            mode="blocked",
        )
    ]
    plan = build_forecast(
        now=now,
        horizon_days=3,
        cells=_cells_weekday_night(),
        overrides=overrides,
        work=[
            WorkItem(kind="vulnerability", id=1, project_id=1, project_name="p",
                     title="SQLi", hours_remaining=1.0, priority=20),
        ],
    )
    # First window should NOT be Monday night — it should be Tuesday night.
    assert plan.windows[0].start_at.day == 14
    assert plan.windows[0].start_at.hour == 22


def test_available_override_opens_otherwise_closed_hour():
    now = datetime(2026, 4, 18, 10, 0, 0)  # Saturday morning (no general cells)
    overrides = [
        OverrideRange(
            start_at=datetime(2026, 4, 18, 14, 0, 0),
            end_at=datetime(2026, 4, 18, 17, 0, 0),
            mode="available",
        )
    ]
    plan = build_forecast(
        now=now,
        horizon_days=2,
        cells=_cells_weekday_night(),
        overrides=overrides,
        work=[
            WorkItem(kind="vulnerability", id=1, project_id=1, project_name="p",
                     title="focused push", hours_remaining=2.0, priority=10),
        ],
    )
    w0 = plan.windows[0]
    assert w0.start_at.weekday() == 5  # Saturday
    assert w0.capacity_hours == 3.0
    assert w0.assignments[0].hours == 2.0


def test_unscheduled_when_work_exceeds_horizon():
    now = datetime(2026, 4, 13, 20, 0, 0)
    plan = build_forecast(
        now=now,
        horizon_days=1,  # only today, so 2 hours capacity total
        cells=_cells_weekday_night(),
        overrides=[],
        work=[
            WorkItem(kind="vulnerability", id=1, project_id=1, project_name="p",
                     title="huge", hours_remaining=8.0, priority=50),
        ],
    )
    # 2h scheduled today, 6h spill out of the horizon.
    assert plan.windows[0].assignments[0].hours == 2.0
    assert len(plan.unscheduled) == 1
    assert plan.unscheduled[0].hours_remaining == 6.0


def test_eta_for_returns_last_slice_end():
    now = datetime(2026, 4, 13, 20, 0, 0)
    plan = build_forecast(
        now=now,
        horizon_days=3,
        cells=_cells_weekday_night(),
        overrides=[],
        work=[
            WorkItem(kind="vulnerability", id=42, project_id=1, project_name="p",
                     title="spans two nights", hours_remaining=3.0, priority=10),
        ],
    )
    eta = plan.eta_for("vulnerability", 42)
    assert eta is not None
    # Tue 22:00 + 1h = Tue 23:00
    assert eta == datetime(2026, 4, 14, 23, 0, 0)
