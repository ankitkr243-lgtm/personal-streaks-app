"""Derived-field and streak computation. Nothing here is ever cached to disk
as authoritative — goal-met flags, book progress, and streaks are all
recomputed from raw log data on every read (Section 6 of the spec).
"""
from datetime import datetime, timedelta

HABITS = ("steps", "reading", "professional_reading")


def compute_day_derived(data, config):
    """Recompute goal-met flags from raw values, ignoring any stored derived values."""
    goals = config["habits"]

    total_steps = data.get("steps") or 0
    steps_goal_met = total_steps >= goals["steps"]["goal"]

    reading = data.get("reading") or []
    total_pages = sum((r.get("pages") or 0) for r in reading)
    reading_goal_met = total_pages >= goals["reading"]["goal"]

    prof = data.get("professional_reading") or []
    professional_reading_done = len(prof) >= goals["professional_reading"]["goal"]

    return {
        "total_steps": total_steps,
        "steps_goal_met": steps_goal_met,
        "total_pages": total_pages,
        "reading_goal_met": reading_goal_met,
        "professional_reading_done": professional_reading_done,
    }


def get_day_state(date_str, entry, today_date):
    """'logged' | 'reviewed' | 'missed' | None (future/not-yet-happened)."""
    if entry is not None:
        return entry["data"].get("state", "logged")
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return "missed" if d < today_date else None


def compute_book_pages(all_logs):
    """{book_id: total_pages_logged} summed across every daily entry."""
    totals = {}
    for entry in all_logs.values():
        for r in (entry["data"].get("reading") or []):
            book_id = r.get("book_id")
            if book_id:
                totals[book_id] = totals.get(book_id, 0) + (r.get("pages") or 0)
    return totals


def _habit_pass(entry, config):
    """Per-habit bool: goal met AND not backfilled, for one day's entry (or None)."""
    if entry is None:
        return {h: False for h in HABITS}
    derived = compute_day_derived(entry["data"], config)
    backfilled = bool(entry["data"].get("backfilled"))
    return {
        "steps": derived["steps_goal_met"] and not backfilled,
        "reading": derived["reading_goal_met"] and not backfilled,
        "professional_reading": derived["professional_reading_done"] and not backfilled,
    }


def compute_streaks(all_logs, config, today_date=None):
    """Per-habit {'current': int, 'longest': int}, walking the full history.

    A day breaks the streak if it's missed (no entry), the goal wasn't met,
    or the entry is backfilled=true — even if the goal was technically met.
    """
    today_date = today_date or datetime.now().date()
    dates_with_data = sorted(all_logs.keys())
    earliest = (
        datetime.strptime(dates_with_data[0], "%Y-%m-%d").date()
        if dates_with_data
        else today_date
    )
    end_date = today_date - timedelta(days=1)  # last fully-elapsed day

    ordered_dates = []
    per_day_pass = {}
    cursor = earliest
    while cursor <= end_date:
        ds = cursor.isoformat()
        ordered_dates.append(ds)
        per_day_pass[ds] = _habit_pass(all_logs.get(ds), config)
        cursor += timedelta(days=1)

    ds_today = today_date.isoformat()
    entry_today = all_logs.get(ds_today)
    if entry_today is not None:
        ordered_dates.append(ds_today)
        per_day_pass[ds_today] = _habit_pass(entry_today, config)

    results = {}
    for habit in HABITS:
        longest = run = 0
        for ds in ordered_dates:
            if per_day_pass[ds][habit]:
                run += 1
                longest = max(longest, run)
            else:
                run = 0
        current = 0
        for ds in reversed(ordered_dates):
            if per_day_pass[ds][habit]:
                current += 1
            else:
                break
        results[habit] = {"current": current, "longest": longest}
    return results
