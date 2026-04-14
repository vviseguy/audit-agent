"""Forecast engine: pack pending work into the next open availability windows.

The queue page's goal is to answer "given my weekly availability and the
Ranker's effort-hour estimates, when will each pending item actually run?"
The engine does that in three steps:

1. Expand the availability sources (general pattern + overrides) into a list
   of concrete open hour-slots going forward from `now`.
2. Collapse adjacent open hours into windows. Each window is a contiguous
   availability block — these are the group headers the queue page shows.
3. Walk the pending work list in priority order, assigning each item to
   window(s). An item larger than the window it starts in spills into the
   next window (same session resuming, not a new session).

The engine is pure: it takes a snapshot of cells/overrides/work and returns
a plan. The scheduler writes actual session rows elsewhere — here we only
forecast what will happen so the UI can show ETAs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable


@dataclass
class WorkItem:
    """One chunk of future work the forecaster should place."""
    kind: str  # 'vulnerability' | 'session'
    id: int
    project_id: int
    project_name: str
    title: str
    hours_remaining: float
    priority: int = 0  # higher = placed first

    def __post_init__(self) -> None:
        # Floor at 15 minutes so degenerate 0-hour items still consume a slot.
        if self.hours_remaining < 0.25:
            self.hours_remaining = 0.25


@dataclass
class OverrideRange:
    start_at: datetime
    end_at: datetime
    mode: str  # 'available' | 'blocked'


@dataclass
class ForecastAssignment:
    """One item's slice inside one window. An item spanning two windows
    produces two assignments — the UI can show them as 'continued'."""
    item_kind: str
    item_id: int
    project_id: int
    project_name: str
    title: str
    start_at: datetime
    end_at: datetime
    hours: float
    continued_from_prior_window: bool = False
    continues_into_next_window: bool = False


@dataclass
class ForecastWindow:
    """One contiguous block of open hours and the items placed inside it."""
    start_at: datetime
    end_at: datetime
    capacity_hours: float
    assignments: list[ForecastAssignment] = field(default_factory=list)

    @property
    def used_hours(self) -> float:
        return sum(a.hours for a in self.assignments)

    @property
    def free_hours(self) -> float:
        return max(0.0, self.capacity_hours - self.used_hours)


@dataclass
class ForecastPlan:
    windows: list[ForecastWindow]
    unscheduled: list[WorkItem]  # items that didn't fit in the horizon

    def eta_for(self, kind: str, item_id: int) -> datetime | None:
        """Finish time of the item's last assignment, or None if unscheduled."""
        last: datetime | None = None
        for w in self.windows:
            for a in w.assignments:
                if a.item_kind == kind and a.item_id == item_id:
                    if last is None or a.end_at > last:
                        last = a.end_at
        return last


def _is_cell_available(
    moment: datetime,
    cells: set[tuple[int, int]],
    overrides: list[OverrideRange],
) -> bool:
    """Resolve availability for the hour `moment` sits in.

    Overrides beat the general pattern: an 'available' override turns an
    off-hour on, and a 'blocked' override turns an on-hour off. If two
    overrides overlap the same hour, the later-created one wins — but we
    sidestep that by letting callers pass overrides in any order and just
    applying them in sequence (blocked is checked last so it's sticky).
    """
    in_cell = (moment.weekday(), moment.hour) in cells
    forced_on = False
    forced_off = False
    hour_end = moment + timedelta(hours=1)
    for ov in overrides:
        if ov.end_at <= moment or ov.start_at >= hour_end:
            continue
        if ov.mode == "available":
            forced_on = True
        elif ov.mode == "blocked":
            forced_off = True
    if forced_off:
        return False
    if forced_on:
        return True
    return in_cell


def _collect_windows(
    *,
    start: datetime,
    horizon_hours: int,
    cells: set[tuple[int, int]],
    overrides: list[OverrideRange],
) -> list[ForecastWindow]:
    """Walk forward hour by hour, gluing adjacent open hours into windows."""
    windows: list[ForecastWindow] = []
    # Align to the top of the current hour so windows have clean boundaries.
    cursor = start.replace(minute=0, second=0, microsecond=0)
    if cursor < start:
        cursor = cursor + timedelta(hours=1)

    open_start: datetime | None = None
    for _ in range(horizon_hours):
        if _is_cell_available(cursor, cells, overrides):
            if open_start is None:
                open_start = cursor
        else:
            if open_start is not None:
                windows.append(
                    ForecastWindow(
                        start_at=open_start,
                        end_at=cursor,
                        capacity_hours=(cursor - open_start).total_seconds() / 3600,
                    )
                )
                open_start = None
        cursor += timedelta(hours=1)
    if open_start is not None:
        windows.append(
            ForecastWindow(
                start_at=open_start,
                end_at=cursor,
                capacity_hours=(cursor - open_start).total_seconds() / 3600,
            )
        )
    return windows


def build_forecast(
    *,
    now: datetime,
    horizon_days: int,
    cells: Iterable[tuple[int, int]],
    overrides: Iterable[OverrideRange],
    work: Iterable[WorkItem],
) -> ForecastPlan:
    """Pack `work` into the open windows of the next `horizon_days` days.

    Items are taken in descending priority (ties broken by id). An item
    larger than the window it lands in spills into the next window as a
    `continued_from_prior_window` assignment — the scheduler treats that as
    a resumed session, which is exactly the auto-resume behavior the user
    asked for.
    """
    cell_set: set[tuple[int, int]] = set(cells)
    ov_list = list(overrides)
    windows = _collect_windows(
        start=now,
        horizon_hours=horizon_days * 24,
        cells=cell_set,
        overrides=ov_list,
    )

    items = sorted(
        list(work),
        key=lambda w: (-w.priority, w.id),
    )

    unscheduled: list[WorkItem] = []
    win_idx = 0
    for item in items:
        remaining = item.hours_remaining
        continued = False
        while remaining > 0 and win_idx < len(windows):
            w = windows[win_idx]
            if w.free_hours <= 0:
                win_idx += 1
                continue
            take = min(remaining, w.free_hours)
            # The assignment starts where prior assignments in this window end.
            slice_start = w.start_at + timedelta(hours=w.used_hours)
            slice_end = slice_start + timedelta(hours=take)
            spills = take < remaining
            w.assignments.append(
                ForecastAssignment(
                    item_kind=item.kind,
                    item_id=item.id,
                    project_id=item.project_id,
                    project_name=item.project_name,
                    title=item.title,
                    start_at=slice_start,
                    end_at=slice_end,
                    hours=round(take, 2),
                    continued_from_prior_window=continued,
                    continues_into_next_window=spills,
                )
            )
            remaining -= take
            continued = spills
        if remaining > 0:
            unscheduled.append(
                WorkItem(
                    kind=item.kind,
                    id=item.id,
                    project_id=item.project_id,
                    project_name=item.project_name,
                    title=item.title,
                    hours_remaining=round(remaining, 2),
                    priority=item.priority,
                )
            )

    return ForecastPlan(windows=windows, unscheduled=unscheduled)
