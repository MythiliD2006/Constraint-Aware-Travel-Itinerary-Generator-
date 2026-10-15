"""Time constraints and an independent validator for finished itineraries.

The planner's primitive actions use the helpers in this module in their
preconditions. ``validate_itinerary`` then re-checks the *finished* schedule
from scratch, so a bug in the search cannot silently produce an invalid plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .budget import rupees
from .knowledge_base import Attraction, Destination, KnowledgeBase, estimate_leg, to_hhmm


@dataclass(frozen=True)
class DayProfile:
    """Pace preference -> daily time window and limits."""
    start: int            # minutes after midnight
    end: int
    max_visits: int
    lunch_minutes: int


PACES: dict[str, DayProfile] = {
    "relaxed": DayProfile(start=9 * 60 + 30, end=18 * 60 + 30, max_visits=3, lunch_minutes=60),
    "moderate": DayProfile(start=9 * 60, end=19 * 60 + 30, max_visits=4, lunch_minutes=45),
    "packed": DayProfile(start=8 * 60, end=21 * 60, max_visits=6, lunch_minutes=40),
}

LUNCH_EARLIEST = 12 * 60
LUNCH_LATEST = 14 * 60 + 30      # lunch must *start* by 14:30
MAX_WAIT_MINUTES = 90            # longest we will wait outside a closed attraction


@dataclass(frozen=True)
class ScheduleItem:
    day: int
    kind: str                     # "travel" | "visit" | "lunch"
    start: int
    end: int
    attraction_id: str | None = None
    label: str = ""
    mode: str | None = None       # travel only
    distance_km: float = 0.0
    cost: int = 0
    origin: str | None = None     # travel only: attraction id or "base"
    target: str | None = None
    waited: int = 0               # visit only: minutes waited for opening

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["start_time"] = to_hhmm(self.start)
        data["end_time"] = to_hhmm(self.end)
        return data


def is_open_on(attraction: Attraction, weekday: str) -> bool:
    return weekday not in attraction.closed_on


def earliest_visit_start(attraction: Attraction, arrival: int, duration: int,
                         max_wait: int = MAX_WAIT_MINUTES) -> tuple[int | None, str]:
    """Earliest start >= arrival such that the whole visit fits in ONE opening window.

    Returns (start, "") on success or (None, reason) on failure.
    """
    reasons: list[str] = []
    for open_at, close_at in attraction.hours:
        start = max(arrival, open_at)
        if start + duration > close_at:
            if arrival < close_at:
                reasons.append(f"a {duration}-min visit would run past closing at {to_hhmm(close_at)}")
            continue
        if start - arrival > max_wait:
            reasons.append(f"would wait {start - arrival} min for opening at {to_hhmm(open_at)}")
            continue
        return start, ""
    windows = ", ".join(f"{to_hhmm(a)}-{to_hhmm(b)}" for a, b in attraction.hours)
    detail = "; ".join(reasons) or f"arriving at {to_hhmm(arrival)} is after closing"
    return None, f"outside opening hours ({windows}): {detail}"


def fits_any_window(attraction: Attraction, duration: int, day_start: int, day_end: int) -> bool:
    """Could the visit fit somewhere inside both an opening window and the day window?"""
    return any(min(close_at, day_end) - max(open_at, day_start) >= duration
               for open_at, close_at in attraction.hours)


# ---------------------------------------------------------------------------
# Independent validation of a finished itinerary
# ---------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    passed: bool = True
    details: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.passed = False
        self.details.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "details": self.details}


def validate_itinerary(kb: KnowledgeBase, destination: Destination, days: list[dict[str, Any]],
                       items: list[ScheduleItem], profile: DayProfile, travelers: int,
                       must_visit: set[str], excluded: set[str], budget: dict[str, Any]
                       ) -> list[dict[str, Any]]:
    hours = Check("Opening hours and closed days")
    travel = Check("Travel times and continuity")
    window = Check("Daily time window and lunch break")
    budget_check = Check("Total cost within budget")
    requests = Check("Must-visit and excluded attractions")

    weekday_of = {d["day"]: d["weekday"] for d in days}
    visited: list[str] = []

    for day in weekday_of:
        day_items = sorted((i for i in items if i.day == day), key=lambda i: i.start)
        location = "base"
        clock = profile.start
        lunches = [i for i in day_items if i.kind == "lunch"]
        if day_items and len(lunches) != 1:
            window.fail(f"Day {day}: expected one lunch break, found {len(lunches)}")
        for lunch in lunches:
            if not LUNCH_EARLIEST <= lunch.start <= LUNCH_LATEST:
                window.fail(f"Day {day}: lunch starts at {to_hhmm(lunch.start)}, outside 12:00-14:30")

        for item in day_items:
            if item.start < clock:
                travel.fail(f"Day {day}: '{item.label}' starts before the previous step ends")
            if item.start < profile.start or item.end > profile.end:
                window.fail(f"Day {day}: '{item.label}' is outside the "
                            f"{to_hhmm(profile.start)}-{to_hhmm(profile.end)} day window")
            clock = item.end

            if item.kind == "travel":
                if item.origin != location:
                    travel.fail(f"Day {day}: travel starts at {item.origin} but traveller is at {location}")
                a = destination.base if item.origin == "base" else destination.attractions[item.origin]
                b = destination.base if item.target == "base" else destination.attractions[item.target]
                leg = estimate_leg(a, b, item.mode or "cab", travelers, destination.costs)
                if leg is None or leg.minutes != item.end - item.start:
                    travel.fail(f"Day {day}: travel time for '{item.label}' does not match the estimate")
                location = item.target or location
            elif item.kind == "visit":
                attraction = destination.attractions[item.attraction_id or ""]
                visited.append(attraction.id)
                if location != attraction.id:
                    travel.fail(f"Day {day}: visiting {attraction.name} without travelling there")
                if not is_open_on(attraction, weekday_of[day]):
                    hours.fail(f"Day {day}: {attraction.name} is closed on {weekday_of[day].title()}")
                inside = any(a <= item.start and item.end <= b for a, b in attraction.hours)
                if not inside:
                    hours.fail(f"Day {day}: {attraction.name} {to_hhmm(item.start)}-{to_hhmm(item.end)} "
                               "is not inside a single opening window")
                if item.end - item.start != kb.duration_of(attraction):
                    window.fail(f"Day {day}: {attraction.name} visit length differs from its duration")
        if day_items and location != "base":
            travel.fail(f"Day {day}: the day does not end back at the base")

    if len(visited) != len(set(visited)):
        requests.fail("An attraction is scheduled more than once")
    for attraction_id in sorted(must_visit - set(visited)):
        requests.fail(f"Must-visit {destination.attractions[attraction_id].name} is missing")
    for attraction_id in sorted(excluded & set(visited)):
        requests.fail(f"Excluded {destination.attractions[attraction_id].name} was scheduled")

    if not budget["within_budget"]:
        budget_check.fail(f"Estimated total {rupees(budget['total'])} exceeds the budget {rupees(budget['limit'])}")
    else:
        budget_check.details.append(f"Estimated total {rupees(budget['total'])} of {rupees(budget['limit'])}")

    for check, ok_note in [(hours, "Every visit fits one opening window on an open day."),
                           (travel, "Every leg matches the travel-time model; no overlaps."),
                           (window, "All steps fit the day window with one lunch break each day."),
                           (requests, "All must-visits included; no excluded stops.")]:
        if check.passed:
            check.details.append(ok_note)
    return [c.to_dict() for c in (hours, travel, window, budget_check, requests)]
