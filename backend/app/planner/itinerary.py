"""Glue code: turns a trip request into a planning problem, runs the HTN
planner and explains the result.

    request -> feasibility pre-checks -> HTN search -> validation -> explanation
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .budget import cheapest_trip_cost, fixed_costs, rupees, summarize
from .constraints import PACES, ScheduleItem, fits_any_window, is_open_on, validate_itinerary
from .htn import HTNPlanner, SearchLimitReached, Task
from .knowledge_base import INTERESTS, WEEKDAYS, KnowledgeBase, estimate_leg, to_hhmm
from .logic import LogicEngine
from .travel_domain import PlanningContext, TravelDomain, TripState

# Each step of the decomposition is one Python call frame deep; a 7-day packed
# trip needs a few hundred frames, so we raise the default limit a little.
sys.setrecursionlimit(max(sys.getrecursionlimit(), 5000))

DISCLAIMER = ("All prices, opening hours and travel times come from a small curated sample "
              "dataset and are illustrative estimates. They are not live prices or availability; "
              "check official sources before travelling.")


@dataclass
class TripRequest:
    destination_id: str
    start_date: date
    days: int
    travelers: int
    budget: int
    accommodation: str = "standard"      # budget | standard | comfort
    pace: str = "moderate"               # relaxed | moderate | packed
    interests: list[str] = field(default_factory=list)
    must_visit: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    seed: int = 0


class RequestError(ValueError):
    """The request itself is malformed (unknown ids, contradictions)."""


def match_interests(kb: KnowledgeBase, destination_id: str, interests: list[str]) -> dict[str, list[str]]:
    """attraction id -> interests it satisfies, derived by resolution over the KB.

    For each interest T we ask: appeals_to(?X, T), located_in(?X, destination).
    """
    engine = LogicEngine(kb.facts_for(destination_id))
    matches: dict[str, list[str]] = {}
    for interest in interests:
        query = [("appeals_to", "?X", interest), ("located_in", "?X", destination_id)]
        for answer in engine.ask(query):
            matches.setdefault(answer["bindings"]["?X"], []).append(interest)
    return matches


def plan_trip(kb: KnowledgeBase, request: TripRequest, node_limit: int = 30000) -> dict[str, Any]:
    destination = kb.destinations.get(request.destination_id)
    if destination is None:
        raise RequestError(f"Unknown destination '{request.destination_id}'")
    for attraction_id in request.must_visit + request.exclude:
        if attraction_id not in destination.attractions:
            raise RequestError(f"Unknown attraction '{attraction_id}' for {destination.name}")
    for interest in request.interests:
        if interest not in INTERESTS:
            raise RequestError(f"Unknown interest '{interest}'")
    clash = set(request.must_visit) & set(request.exclude)
    if clash:
        names = ", ".join(destination.attractions[a].name for a in sorted(clash))
        raise RequestError(f"Marked as both must-visit and excluded: {names}")
    if request.pace not in PACES:
        raise RequestError(f"Unknown pace '{request.pace}'")

    profile = PACES[request.pace]
    dates = [request.start_date + timedelta(days=i) for i in range(request.days)]
    weekdays = [WEEKDAYS[d.weekday()] for d in dates]
    day_info = [{"day": i + 1, "date": d.isoformat(), "weekday": weekdays[i]} for i, d in enumerate(dates)]

    fixed = fixed_costs(destination, request.days, request.travelers, request.accommodation)
    activity_budget = request.budget - fixed.total
    must_visit = set(request.must_visit)
    excluded = set(request.exclude)

    interest_matches = match_interests(kb, destination.id, request.interests)
    if request.interests:
        candidates = [a for a in destination.attractions if a in interest_matches or a in must_visit]
    else:
        candidates = list(destination.attractions)
    candidates = [a for a in candidates if a not in excluded]

    base_response: dict[str, Any] = {
        "destination": {"id": destination.id, "name": destination.name, "base": destination.base.name},
        "request": {**request.__dict__, "start_date": request.start_date.isoformat()},
        "pace": {"day_start": to_hhmm(profile.start), "day_end": to_hhmm(profile.end),
                 "lunch_minutes": profile.lunch_minutes},
        "disclaimer": DISCLAIMER,
    }

    # ---- 1. Cheap feasibility checks with specific explanations -----------
    issues, suggestions = precheck(kb, request, destination, weekdays, profile, activity_budget, fixed)
    if issues:
        return {**base_response, "status": "infeasible", "issues": issues, "suggestions": suggestions,
                "budget": summarize(destination, request.days, request.travelers, request.accommodation,
                                    request.budget, 0, 0),
                "stats": None}

    # ---- 2. HTN search -----------------------------------------------------
    daily_limit = min(profile.max_visits, max(2, math.ceil(len(candidates) / request.days) + 1,
                                                 math.ceil(len(must_visit) / request.days)))
    ctx = PlanningContext(kb=kb, destination=destination, weekdays=weekdays, profile=profile,
                          travelers=request.travelers, activity_budget=activity_budget,
                          candidates=candidates, must_visit=must_visit,
                          interest_matches=interest_matches, daily_limit=daily_limit, seed=request.seed)
    domain = TravelDomain(ctx)
    planner = HTNPlanner(domain.operators(), domain.methods(), node_limit=node_limit)
    try:
        result = planner.plan(TripState(), Task("plan_trip", (request.days,)))
        limit_hit = False
    except SearchLimitReached:
        result, limit_hit = None, True

    if result is None:
        issues = explain_search_failure(planner.stats.failures, destination, must_visit, limit_hit, node_limit)
        return {**base_response, "status": "infeasible", "issues": issues,
                "suggestions": ["Add a day or choose the packed pace for longer days.",
                                "Remove one of the must-visit attractions.",
                                "Raise the budget or pick a cheaper stay to free money for activities."],
                "budget": summarize(destination, request.days, request.travelers, request.accommodation,
                                    request.budget, 0, 0),
                "stats": planner.stats.to_dict()}

    # ---- 3. Validate and explain --------------------------------------------
    items: list[ScheduleItem] = result.items
    state: TripState = result.state
    budget = summarize(destination, request.days, request.travelers, request.accommodation,
                       request.budget, state.entry_fees, state.transport)
    checks = validate_itinerary(kb, destination, day_info, items, profile, request.travelers,
                                must_visit, excluded, budget)

    days_out = []
    for info in day_info:
        day_items = [i for i in items if i.day == info["day"]]
        days_out.append({**info,
                         "items": [serialize_item(kb, destination, i) for i in day_items],
                         "visit_count": sum(1 for i in day_items if i.kind == "visit"),
                         "activity_cost": sum(i.cost for i in day_items)})
    warnings = [f"Day {d['day']} has no stops: every suitable attraction was already scheduled, "
                f"closed or out of reach." for d in days_out if d["visit_count"] == 0]

    selected, rejected = explain_choices(kb, request, destination, items, weekdays, candidates,
                                         interest_matches, planner.stats.failures,
                                         activity_budget - state.spent, daily_limit)
    return {**base_response, "status": "ok", "days": days_out, "budget": budget, "checks": checks,
            "selected": selected, "rejected": rejected, "warnings": warnings,
            "stats": {**planner.stats.to_dict(), "daily_limit": daily_limit,
                      "candidates": len(candidates)},
            "decomposition": result.tree}


def serialize_item(kb: KnowledgeBase, destination: Any, item: ScheduleItem) -> dict[str, Any]:
    data = item.to_dict()
    if item.kind == "visit" and item.attraction_id:
        attraction = destination.attractions[item.attraction_id]
        data["category"] = attraction.category
        data["hours"] = [f"{to_hhmm(a)}-{to_hhmm(b)}" for a, b in attraction.hours]
        notes = []
        for prop, text in [("dress_code", None), ("footwear_removed", "Footwear removed inside"),
                           ("silence_expected", "Silence expected")]:
            found = kb.get_property(attraction, prop)
            if found and found[0]:
                notes.append({"text": text or str(found[0]).capitalize(), "inherited_from": found[1]})
        data["visitor_notes"] = notes
    return data


# ---------------------------------------------------------------------------
# Feasibility pre-checks
# ---------------------------------------------------------------------------
def precheck(kb: KnowledgeBase, request: TripRequest, destination: Any, weekdays: list[str],
             profile: Any, activity_budget: int, fixed: Any) -> tuple[list[dict], list[str]]:
    issues: list[dict] = []
    suggestions: list[str] = []
    if activity_budget < 0:
        issues.append({"code": "budget_fixed_costs", "attraction_id": None,
                       "message": f"Accommodation ({rupees(fixed.accommodation)}) and food ({rupees(fixed.food)}) "
                                  f"alone come to {rupees(fixed.total)}, which is above the budget of "
                                  f"{rupees(request.budget)}."})
        cheapest = cheapest_trip_cost(destination, request.days, request.travelers)
        if request.accommodation != "budget" and cheapest <= request.budget:
            suggestions.append(f"The budget stay tier brings fixed costs down to {rupees(cheapest)}.")
        suggestions.append(f"Raise the budget to at least {rupees(fixed.total)} plus entry fees and transport, "
                           "or shorten the trip.")

    must_fees = 0
    for attraction_id in request.must_visit:
        attraction = destination.attractions[attraction_id]
        duration = kb.duration_of(attraction)
        must_fees += attraction.entry_fee * request.travelers
        open_days = [w for w in weekdays if is_open_on(attraction, w)]
        if not open_days:
            closed = ", ".join(sorted({w.title() for w in attraction.closed_on}))
            issues.append({"code": "closed_all_days", "attraction_id": attraction_id,
                           "message": f"{attraction.name} is closed on {closed}, and every day of the "
                                      "trip falls on a closed day."})
            suggestions.append(f"Shift the start date so the trip includes a day {attraction.name} is open.")
            continue
        if not fits_any_window(attraction, duration, profile.start, profile.end):
            issues.append({"code": "window_too_short", "attraction_id": attraction_id,
                           "message": f"{attraction.name} needs {duration} min, but none of its opening "
                                      f"windows overlaps the {to_hhmm(profile.start)}-{to_hhmm(profile.end)} "
                                      "day enough to fit the visit."})
            continue
        there = estimate_leg(destination.base, attraction, "cab", request.travelers, destination.costs)
        assert there is not None
        day_length = profile.end - profile.start - profile.lunch_minutes
        if 2 * there.minutes + duration > day_length:
            issues.append({"code": "too_far", "attraction_id": attraction_id,
                           "message": f"A round trip to {attraction.name} ({2 * there.minutes} min of travel) "
                                      f"plus the {duration}-min visit does not fit in one day at this pace."})
            suggestions.append("Choose the packed pace for a longer day.")
    if len(request.must_visit) > profile.max_visits * request.days:
        issues.append({"code": "too_many_must_visits", "attraction_id": None,
                       "message": f"{len(request.must_visit)} must-visits do not fit: this pace allows at most "
                                  f"{profile.max_visits} stops per day over {request.days} day(s)."})
        suggestions.append("Add a day, choose a faster pace, or remove some must-visits.")
    must_minutes = sum(kb.duration_of(destination.attractions[a]) for a in request.must_visit)
    usable = request.days * (profile.end - profile.start - profile.lunch_minutes)
    if must_minutes > usable:
        issues.append({"code": "too_much_time", "attraction_id": None,
                       "message": f"The must-visits need {must_minutes} min of visiting time, more than the "
                                  f"{usable} min available across {request.days} day(s), before any travel."})
    if activity_budget >= 0 and must_fees > activity_budget:
        issues.append({"code": "budget_must_visits", "attraction_id": None,
                       "message": f"Entry fees for the must-visit attractions come to {rupees(must_fees)}, but only "
                                  f"{rupees(activity_budget)} is left after accommodation and food."})
        suggestions.append("Raise the budget, pick a cheaper stay, or drop a paid must-visit.")
    return issues, list(dict.fromkeys(suggestions))


def explain_search_failure(failures: Any, destination: Any, must_visit: set[str],
                           limit_hit: bool, node_limit: int) -> list[dict]:
    issues: list[dict] = []
    if limit_hit:
        issues.append({"code": "search_limit", "attraction_id": None,
                       "message": f"The planner explored {node_limit} decomposition steps without finding a "
                                  "schedule that satisfies every constraint, and stopped."})
    else:
        issues.append({"code": "no_plan", "attraction_id": None,
                       "message": "The planner tried every ordering of stops and travel modes it could and "
                                  "found no schedule meeting all time, budget and must-visit constraints."})
    # Bookkeeping failures say *that* a must-visit was missed, not *why*; skip them
    # so the user sees the concrete precondition (closing time, lunch, budget...).
    generic = ("still unscheduled", "must-visit not scheduled", "already visited", "not at the attraction")
    for attraction_id in sorted(must_visit):
        reasons = [(count, reason) for (subject, reason), count in failures.items()
                   if subject == attraction_id and not reason.startswith(generic)]
        if reasons:
            reasons.sort(reverse=True)
            top = "; ".join(reason for _, reason in reasons[:2])
            issues.append({"code": "must_visit_conflict", "attraction_id": attraction_id,
                           "message": f"{destination.attractions[attraction_id].name}: {top}."})
    return issues


# ---------------------------------------------------------------------------
# Why each attraction was selected or rejected
# ---------------------------------------------------------------------------
def explain_choices(kb: KnowledgeBase, request: TripRequest, destination: Any, items: list[ScheduleItem],
                    weekdays: list[str], candidates: list[str], interest_matches: dict[str, list[str]],
                    failures: Any, budget_left: int, daily_limit: int) -> tuple[list[dict], list[dict]]:
    visits = {i.attraction_id: i for i in items if i.kind == "visit"}
    selected: list[dict] = []
    rejected: list[dict] = []
    for attraction_id, attraction in destination.attractions.items():
        sources = kb.interests_of(attraction)
        if attraction_id in visits:
            item = visits[attraction_id]
            reasons: list[str] = []
            if attraction_id in request.must_visit:
                reasons.append("You marked it as a must-visit.")
            matched = interest_matches.get(attraction_id, [])
            if matched:
                parts = [f"{t} (" + ("set on this attraction" if sources[t] == attraction_id
                                   else f"inherited from {sources[t]}") + ")" for t in matched]
                reasons.append("Matches your interests: " + ", ".join(parts) + ".")
            elif not request.interests:
                reasons.append("No interest filter was chosen, so every attraction was a candidate.")
            windows = ", ".join(f"{to_hhmm(a)}-{to_hhmm(b)}" for a, b in attraction.hours)
            reasons.append(f"Day {item.day} ({weekdays[item.day - 1].title()}) "
                           f"{to_hhmm(item.start)}-{to_hhmm(item.end)} fits its opening hours ({windows}).")
            if item.waited:
                reasons.append(f"Arrives {item.waited} min before opening and waits.")
            selected.append({"attraction_id": attraction_id, "name": attraction.name,
                             "day": item.day, "reasons": reasons})
            continue

        if attraction_id in request.exclude:
            code, reason = "excluded", "You excluded it."
        elif attraction_id not in candidates:
            appeals = ", ".join(sorted(sources)) or "none listed"
            code, reason = "no_interest_match", f"Does not match your selected interests (it appeals to: {appeals})."
        elif not any(is_open_on(attraction, w) for w in weekdays):
            code, reason = "closed", f"Closed on every trip day ({', '.join(w.title() for w in attraction.closed_on)})."
        elif attraction.entry_fee * request.travelers > budget_left:
            code, reason = "budget", (f"Entry for {request.travelers} ({rupees(attraction.entry_fee * request.travelers)}) "
                                      f"is more than the activity budget left ({rupees(max(budget_left, 0))}).")
        else:
            tried = [(count, r) for (subject, r), count in failures.items()
                     if subject == attraction_id and r not in ("already visited", "not at the attraction")]
            if tried:
                tried.sort(reverse=True)
                code, reason = "no_slot", (f"No slot found: {tried[0][1]} "
                                           "(the most frequent failed precondition during search).")
            else:
                code, reason = "lower_priority", (f"Lower priority than the scheduled stops; days were filled "
                                                  f"(up to {daily_limit} stops per day at this pace).")
        rejected.append({"attraction_id": attraction_id, "name": attraction.name, "code": code, "reason": reason})
    selected.sort(key=lambda s: (s["day"], visits[s["attraction_id"]].start))
    return selected, rejected
