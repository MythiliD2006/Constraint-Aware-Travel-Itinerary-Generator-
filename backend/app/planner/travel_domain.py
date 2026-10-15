"""The travel-itinerary planning domain: state, operators and HTN methods.

Task network
------------
plan_trip(n)
  method day_by_day -> plan_day(1) ... plan_day(n), verify_must_visits
plan_day(d)
  method single_day -> begin_day(d), fill_day(d), end_day(d)
fill_day(d)                                  (recursive: one stop at a time)
  method visit_next[A]  -> visit_attraction(A), fill_day(d)   (one per candidate A)
  method lunch_break    -> have_lunch, fill_day(d)
  method finish_day     -> go_back_to_base
visit_attraction(A)
  method walk_there     -> travel(A, walk), visit(A)          (only short hops)
  method ride_there     -> travel(A, cab), visit(A)
go_back_to_base
  method lunch_then_return -> have_lunch, return_to_base     (if lunch not taken)
  method return_on_foot / return_by_cab -> return_to_base(mode)

Primitive operators (each has preconditions and effects)
--------------------------------------------------------
begin_day, travel, visit, have_lunch, return_to_base, end_day, verify_must_visits
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Any, Iterator

from .constraints import (LUNCH_EARLIEST, LUNCH_LATEST, DayProfile, ScheduleItem,
                          earliest_visit_start, is_open_on)
from .htn import Applied, Failure, Task
from .knowledge_base import Attraction, Destination, KnowledgeBase, Leg, estimate_leg, to_hhmm


@dataclass(frozen=True)
class TripState:
    """World state. Frozen: operators return modified copies (their effects)."""
    day: int = 0
    time: int = 0                      # minutes after midnight
    location: str = "base"             # "base" or an attraction id
    visited: frozenset[str] = frozenset()
    visits_today: int = 0
    lunch_taken: bool = False
    spent: int = 0                     # entry fees + transport so far (INR)
    entry_fees: int = 0
    transport: int = 0


@dataclass
class PlanningContext:
    """Static information the operators and methods read but never change."""
    kb: KnowledgeBase
    destination: Destination
    weekdays: list[str]                # weekday name for day 1..n (index 0 = day 1)
    profile: DayProfile
    travelers: int
    activity_budget: int               # budget left after accommodation and food
    candidates: list[str]              # attraction ids the planner may choose
    must_visit: set[str]
    interest_matches: dict[str, list[str]]   # attraction id -> matched interests
    daily_limit: int
    seed: int = 0
    jitter: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # The seed only reorders equally attractive optional stops, which is how
        # "Regenerate" finds a different (still valid) itinerary.
        rng = random.Random(self.seed)
        self.jitter = {a: (rng.uniform(0, 12) if self.seed else 0.0) for a in self.candidates}

    def place(self, location: str) -> Any:
        return self.destination.base if location == "base" else self.destination.attractions[location]

    def leg(self, origin: str, target: str, mode: str) -> Leg | None:
        return estimate_leg(self.place(origin), self.place(target), mode,
                            self.travelers, self.destination.costs)

    def duration(self, attraction_id: str) -> int:
        return self.kb.duration_of(self.destination.attractions[attraction_id])

    def weekday(self, day: int) -> str:
        return self.weekdays[day - 1]


class TravelDomain:
    def __init__(self, ctx: PlanningContext) -> None:
        self.ctx = ctx

    # ------------------------------------------------------------------
    # Operators
    # ------------------------------------------------------------------
    def op_begin_day(self, state: TripState, day: int) -> Applied | Failure:
        return Applied(replace(state, day=day, time=self.ctx.profile.start, location="base",
                               visits_today=0, lunch_taken=False))

    def op_travel(self, state: TripState, target: str, mode: str) -> Applied | Failure:
        ctx = self.ctx
        leg = ctx.leg(state.location, target, mode)
        if leg is None:
            return Failure(f"too far to walk", target)
        arrival = state.time + leg.minutes
        if not state.lunch_taken and arrival > LUNCH_LATEST:
            return Failure("arrival would push lunch past 14:30", target)
        if state.spent + leg.cost > ctx.activity_budget:
            return Failure("transport fare exceeds remaining budget", target)
        item = ScheduleItem(day=state.day, kind="travel", start=state.time, end=arrival,
                            label=f"To {ctx.destination.attractions[target].name}", mode=leg.mode,
                            distance_km=leg.road_km, cost=leg.cost, origin=state.location, target=target)
        return Applied(replace(state, time=arrival, location=target,
                               spent=state.spent + leg.cost, transport=state.transport + leg.cost), item)

    def op_visit(self, state: TripState, attraction_id: str) -> Applied | Failure:
        ctx = self.ctx
        attraction: Attraction = ctx.destination.attractions[attraction_id]
        weekday = ctx.weekday(state.day)
        # --- preconditions -------------------------------------------------
        if state.location != attraction_id:
            return Failure("not at the attraction", attraction_id)
        if attraction_id in state.visited:
            return Failure("already visited", attraction_id)
        if not is_open_on(attraction, weekday):
            return Failure(f"closed on {weekday.title()}", attraction_id)
        duration = ctx.duration(attraction_id)
        start, reason = earliest_visit_start(attraction, state.time, duration)
        if start is None:
            return Failure(reason, attraction_id)
        end = start + duration
        if not state.lunch_taken and end > LUNCH_LATEST:
            return Failure("visit would push lunch past 14:30", attraction_id)
        # Reserve time and money to get back to the base at the end of the day.
        way_back = ctx.leg(attraction_id, "base", "walk") or ctx.leg(attraction_id, "base", "cab")
        assert way_back is not None
        lunch_reserve = 0 if state.lunch_taken else ctx.profile.lunch_minutes
        if end + lunch_reserve + way_back.minutes > ctx.profile.end:
            return Failure(f"could not get back by {to_hhmm(ctx.profile.end)}", attraction_id)
        fee = attraction.entry_fee * ctx.travelers
        if state.spent + fee + way_back.cost > ctx.activity_budget:
            return Failure("entry fee exceeds remaining activity budget", attraction_id)
        if attraction_id not in ctx.must_visit:
            blocked = self.crowds_out_must_visits(state, end + lunch_reserve + way_back.minutes)
            if blocked:
                return Failure(blocked, attraction_id)
        # --- effects ----------------------------------------------------------
        item = ScheduleItem(day=state.day, kind="visit", start=start, end=end,
                            attraction_id=attraction_id, label=attraction.name, cost=fee,
                            waited=start - state.time)
        return Applied(replace(state, time=end, visited=state.visited | {attraction_id},
                               visits_today=state.visits_today + 1, spent=state.spent + fee,
                               entry_fees=state.entry_fees + fee), item)

    def crowds_out_must_visits(self, state: TripState, earliest_finish: int) -> str:
        """Pruning for optional stops (returns a reason, or "" if the stop is fine).

        A must-visit that is still unscheduled and is not open on any later day
        has to happen today. Adding an optional stop is pointless if, even with
        zero travel time (an optimistic lower bound), today's remaining
        must-visits would no longer fit. Because the bound never overestimates,
        this pruning cannot remove a branch that could have led to a plan.
        """
        ctx = self.ctx
        later_days = range(state.day + 1, len(ctx.weekdays) + 1)
        due_today = [a for a in ctx.must_visit - state.visited
                     if not any(is_open_on(ctx.destination.attractions[a], ctx.weekday(d)) for d in later_days)]
        if not due_today:
            return ""
        if state.visits_today + 1 + len(due_today) > ctx.daily_limit:
            return "would leave no room for today's must-visits"
        if earliest_finish + sum(ctx.duration(a) for a in due_today) > ctx.profile.end:
            return "would leave too little time for today's must-visits"
        return ""

    def op_have_lunch(self, state: TripState) -> Applied | Failure:
        if state.lunch_taken:
            return Failure("lunch already taken")
        start = max(state.time, LUNCH_EARLIEST)
        if start > LUNCH_LATEST:
            return Failure("too late for lunch")
        end = start + self.ctx.profile.lunch_minutes
        if end > self.ctx.profile.end:
            return Failure("no time left for lunch")
        item = ScheduleItem(day=state.day, kind="lunch", start=start, end=end, label="Lunch break")
        return Applied(replace(state, time=end, lunch_taken=True), item)

    def op_return_to_base(self, state: TripState, mode: str) -> Applied | Failure:
        ctx = self.ctx
        if not state.lunch_taken:
            return Failure("lunch not yet taken")
        if state.location == "base":
            return Applied(state)       # nothing to do: an empty day
        leg = ctx.leg(state.location, "base", mode)
        if leg is None:
            return Failure("too far to walk back")
        arrival = state.time + leg.minutes
        if arrival > ctx.profile.end:
            return Failure(f"back after {to_hhmm(ctx.profile.end)}")
        if state.spent + leg.cost > ctx.activity_budget:
            return Failure("fare back exceeds remaining budget")
        item = ScheduleItem(day=state.day, kind="travel", start=state.time, end=arrival,
                            label=f"Back to {ctx.destination.base.name}", mode=leg.mode,
                            distance_km=leg.road_km, cost=leg.cost, origin=state.location, target="base")
        return Applied(replace(state, time=arrival, location="base",
                               spent=state.spent + leg.cost, transport=state.transport + leg.cost), item)

    def op_end_day(self, state: TripState, day: int) -> Applied | Failure:
        """Pruning check: every unvisited must-visit still needs an open day ahead.

        Failing here makes the planner backtrack into today's choices now,
        instead of discovering the problem only at the end of the trip.
        """
        ctx = self.ctx
        remaining_days = range(day + 1, len(ctx.weekdays) + 1)
        for attraction_id in ctx.must_visit - state.visited:
            attraction = ctx.destination.attractions[attraction_id]
            if not any(is_open_on(attraction, ctx.weekday(d)) for d in remaining_days):
                return Failure(f"still unscheduled after day {day} with no later open day", attraction_id)
        return Applied(state)

    def op_verify_must_visits(self, state: TripState) -> Applied | Failure:
        missing = self.ctx.must_visit - state.visited
        if missing:
            return Failure("must-visit not scheduled", sorted(missing)[0])
        return Applied(state)

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------
    def m_plan_trip(self, state: TripState, days: int) -> Iterator[tuple[str, list[Task]]]:
        subtasks = [Task("plan_day", (d,)) for d in range(1, days + 1)]
        yield "day_by_day", subtasks + [Task("verify_must_visits")]

    def m_plan_day(self, state: TripState, day: int) -> Iterator[tuple[str, list[Task]]]:
        yield "single_day", [Task("begin_day", (day,)), Task("fill_day", (day,)), Task("end_day", (day,))]

    def m_fill_day(self, state: TripState, day: int) -> Iterator[tuple[str, list[Task]]]:
        if state.visits_today < self.ctx.daily_limit:
            for attraction_id in self.rank_candidates(state):
                yield f"visit_next[{attraction_id}]", [Task("visit_attraction", (attraction_id,)),
                                                       Task("fill_day", (day,))]
        # Take lunch explicitly only around midday; otherwise finish_day adds it.
        if not state.lunch_taken and state.time >= LUNCH_EARLIEST - 60:
            yield "lunch_break", [Task("have_lunch"), Task("fill_day", (day,))]
        yield "finish_day", [Task("go_back_to_base")]

    def m_visit_attraction(self, state: TripState, attraction_id: str) -> Iterator[tuple[str, list[Task]]]:
        # Walking is free, so it is preferred when the distance allows it.
        if self.ctx.leg(state.location, attraction_id, "walk") is not None:
            yield "walk_there", [Task("travel", (attraction_id, "walk")), Task("visit", (attraction_id,))]
        yield "ride_there", [Task("travel", (attraction_id, "cab")), Task("visit", (attraction_id,))]

    def m_go_back_to_base(self, state: TripState) -> Iterator[tuple[str, list[Task]]]:
        if not state.lunch_taken:
            yield "lunch_then_return", [Task("have_lunch"), Task("go_back_to_base")]
            return
        if state.location != "base" and self.ctx.leg(state.location, "base", "walk") is not None:
            yield "return_on_foot", [Task("return_to_base", ("walk",))]
        yield "return_by_cab", [Task("return_to_base", ("cab",))]

    # ------------------------------------------------------------------
    # Heuristic ordering of candidates (decides which branch is tried first)
    # ------------------------------------------------------------------
    def rank_candidates(self, state: TripState) -> list[str]:
        ctx = self.ctx
        weekday = ctx.weekday(state.day)
        scored: list[tuple[float, str]] = []
        for attraction_id in ctx.candidates:
            if attraction_id in state.visited:
                continue
            attraction = ctx.destination.attractions[attraction_id]
            if not is_open_on(attraction, weekday):
                continue                              # cheap filter; visit() would fail anyway
            score = 10.0 * len(ctx.interest_matches.get(attraction_id, []))
            if attraction_id in ctx.must_visit:
                score += 1000                         # try must-visits first
            leg = ctx.leg(state.location, attraction_id, "cab")
            assert leg is not None
            score -= leg.minutes / 2                  # prefer nearby stops
            best_time = ctx.kb.get_property(attraction, "best_time")
            if best_time and best_time[0] == "evening":
                score += 12 if state.time >= 15 * 60 else -12
            elif best_time and best_time[0] == "morning":
                score += 8 if state.time < 12 * 60 else -8
            score += ctx.jitter.get(attraction_id, 0.0)
            scored.append((score, attraction_id))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [attraction_id for _, attraction_id in scored]

    # ------------------------------------------------------------------
    def operators(self) -> dict[str, Any]:
        return {
            "begin_day": self.op_begin_day,
            "travel": self.op_travel,
            "visit": self.op_visit,
            "have_lunch": self.op_have_lunch,
            "return_to_base": self.op_return_to_base,
            "end_day": self.op_end_day,
            "verify_must_visits": self.op_verify_must_visits,
        }

    def methods(self) -> dict[str, Any]:
        return {
            "plan_trip": self.m_plan_trip,
            "plan_day": self.m_plan_day,
            "fill_day": self.m_fill_day,
            "visit_attraction": self.m_visit_attraction,
            "go_back_to_base": self.m_go_back_to_base,
        }
