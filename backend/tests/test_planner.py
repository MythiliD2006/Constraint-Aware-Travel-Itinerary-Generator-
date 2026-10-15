"""HTN planner, constraints, budget handling and failure explanations."""

from dataclasses import replace
from datetime import date

import pytest

from app.planner.constraints import PACES, ScheduleItem, validate_itinerary
from app.planner.htn import Applied, Failure, HTNPlanner, Task
from app.planner.itinerary import TripRequest, plan_trip
from app.planner.knowledge_base import get_knowledge_base, to_minutes

MONDAY = date(2026, 10, 19)


@pytest.fixture(scope="module")
def kb():
    return get_knowledge_base()


def visits(result):
    return [i for d in result["days"] for i in d["items"] if i["kind"] == "visit"]


# ---- Generic HTN engine ------------------------------------------------------
def test_htn_backtracks_to_next_method_when_a_later_precondition_fails():
    """Toy domain: the preferred method looks fine at first but makes a later
    primitive fail; the planner must undo it and use the second method."""
    def op_spend(state, amount):
        if state["money"] < amount:
            return Failure("not enough money")
        return Applied({**state, "money": state["money"] - amount}, f"spend {amount}")

    def m_trip(state):
        yield "expensive_first", [Task("spend", (8,)), Task("spend", (5,))]
        yield "cheap_first", [Task("spend", (3,)), Task("spend", (5,))]

    planner = HTNPlanner({"spend": op_spend}, {"trip": m_trip})
    result = planner.plan({"money": 10}, Task("trip"))
    assert result is not None
    assert result.items == ["spend 3", "spend 5"]
    assert result.tree["method"] == "cheap_first"
    assert planner.stats.backtracks == 1


def test_htn_returns_none_when_no_decomposition_works():
    planner = HTNPlanner({"fail": lambda s: Failure("never")}, {"t": lambda s: iter([("only", [Task("fail")])])})
    assert planner.plan({}, Task("t")) is None


# ---- Feasible itineraries ----------------------------------------------------------
@pytest.mark.parametrize("destination", ["jaipur", "mysuru", "puducherry"])
@pytest.mark.parametrize("pace", ["relaxed", "moderate", "packed"])
def test_generated_plans_pass_independent_validation(kb, destination, pace):
    result = plan_trip(kb, TripRequest(destination, MONDAY, 3, 2, 40000, pace=pace,
                                       interests=["history", "nature", "spiritual"]))
    assert result["status"] == "ok"
    assert all(check["passed"] for check in result["checks"]), result["checks"]
    assert len(visits(result)) >= 5
    assert result["budget"]["within_budget"]


def test_plan_is_not_hardcoded_it_reacts_to_interests(kb):
    nature = plan_trip(kb, TripRequest("puducherry", MONDAY, 1, 2, 20000, interests=["nature"]))
    spiritual = plan_trip(kb, TripRequest("puducherry", MONDAY, 1, 2, 20000, interests=["spiritual"]))
    nature_ids = {v["attraction_id"] for v in visits(nature)}
    spiritual_ids = {v["attraction_id"] for v in visits(spiritual)}
    assert nature_ids and spiritual_ids and nature_ids.isdisjoint(spiritual_ids)


def test_must_visit_and_excluded(kb):
    result = plan_trip(kb, TripRequest("jaipur", MONDAY, 2, 2, 30000, interests=["history"],
                                       must_visit=["johari_bazaar"], exclude=["city_palace"]))
    ids = [v["attraction_id"] for v in visits(result)]
    assert "johari_bazaar" in ids        # must-visit even though it does not match "history"
    assert "city_palace" not in ids
    reasons = {r["attraction_id"]: r["code"] for r in result["rejected"]}
    assert reasons["city_palace"] == "excluded"


def test_closed_days_are_respected(kb):
    # Mysuru Zoo is closed on Tuesdays and the Rail Museum on Mondays.
    result = plan_trip(kb, TripRequest("mysuru", MONDAY, 2, 2, 30000,
                                       must_visit=["mysore_zoo", "rail_museum"]))
    day_of = {v["attraction_id"]: v["day"] for v in visits(result)}
    assert day_of["mysore_zoo"] == 1       # Monday
    assert day_of["rail_museum"] == 2      # Tuesday


def test_split_opening_hours_are_respected(kb):
    result = plan_trip(kb, TripRequest("jaipur", MONDAY, 1, 1, 20000, pace="packed",
                                       must_visit=["birla_mandir"]))
    birla = next(v for v in visits(result) if v["attraction_id"] == "birla_mandir")
    start, end = to_minutes(birla["start_time"]), to_minutes(birla["end_time"])
    assert end <= to_minutes("12:00") or start >= to_minutes("15:00")


def test_every_day_has_lunch_in_window_and_returns_to_base(kb):
    result = plan_trip(kb, TripRequest("puducherry", MONDAY, 2, 3, 40000))
    for day in result["days"]:
        lunches = [i for i in day["items"] if i["kind"] == "lunch"]
        assert len(lunches) == 1
        assert "12:00" <= lunches[0]["start_time"] <= "14:30"
        assert day["items"][-1]["target"] == "base"


def test_budget_totals_add_up(kb):
    result = plan_trip(kb, TripRequest("jaipur", MONDAY, 3, 3, 50000, accommodation="comfort"))
    budget = result["budget"]
    items = [i for d in result["days"] for i in d["items"]]
    assert budget["entry_fees"] == sum(i["cost"] for i in items if i["kind"] == "visit")
    assert budget["local_transport"] == sum(i["cost"] for i in items if i["kind"] == "travel")
    assert budget["accommodation"] == 2 * 2 * 6500      # 2 nights x 2 rooms x comfort rate
    assert budget["total"] == (budget["accommodation"] + budget["food"]
                               + budget["entry_fees"] + budget["local_transport"])


def test_tight_activity_budget_drops_paid_attractions(kb):
    # Fixed costs: 1 night x 1 room (1400) + 2 days x 2 x 450 = 3200; leaves 300 for activities.
    result = plan_trip(kb, TripRequest("jaipur", MONDAY, 2, 2, 3500, accommodation="budget"))
    assert result["status"] == "ok"
    assert result["budget"]["total"] <= 3500
    assert any(r["code"] in ("budget", "no_slot") for r in result["rejected"])


def test_same_seed_is_deterministic_and_other_seed_varies(kb):
    request = TripRequest("jaipur", MONDAY, 2, 2, 30000)
    first, again = plan_trip(kb, request), plan_trip(kb, request)
    assert visits(first) == visits(again)
    other = plan_trip(kb, replace(request, seed=3))
    assert [v["attraction_id"] for v in visits(other)] != [v["attraction_id"] for v in visits(first)]
    assert all(c["passed"] for c in other["checks"])


# ---- Infeasible requests and explanations ----------------------------------------------
def test_budget_below_fixed_costs_is_explained(kb):
    result = plan_trip(kb, TripRequest("jaipur", MONDAY, 3, 2, 5000))
    assert result["status"] == "infeasible"
    assert result["issues"][0]["code"] == "budget_fixed_costs"
    assert result["suggestions"]


def test_must_visit_closed_on_every_trip_day(kb):
    result = plan_trip(kb, TripRequest("mysuru", MONDAY, 1, 2, 20000, must_visit=["rail_museum"]))
    assert result["status"] == "infeasible"
    assert result["issues"][0]["code"] == "closed_all_days"


def test_too_many_must_visits_for_one_day(kb):
    musts = ["amber_fort", "city_palace", "albert_hall", "galtaji", "sisodia_garden"]
    result = plan_trip(kb, TripRequest("jaipur", MONDAY, 1, 2, 30000, must_visit=musts))
    assert result["status"] == "infeasible"
    assert "too_many_must_visits" in {i["code"] for i in result["issues"]}


def test_search_failure_names_the_conflicting_must_visits(kb):
    # Four long must-visits in one day pass the quick pre-checks (count, total
    # minutes) but cannot be scheduled together around closing times and lunch.
    # The search must exhaust its options (not hit the node limit) and explain.
    musts = ["amber_fort", "city_palace", "hawa_mahal", "albert_hall"]
    result = plan_trip(kb, TripRequest("jaipur", MONDAY, 1, 2, 30000, must_visit=musts))
    assert result["status"] == "infeasible"
    codes = [i["code"] for i in result["issues"]]
    assert codes[0] == "no_plan"
    assert "must_visit_conflict" in codes
    assert any("closing" in i["message"] for i in result["issues"])
    assert 0 < result["stats"]["nodes_expanded"] < 30000
    assert result["stats"]["backtracks"] > 0


# ---- The validator really checks (it is not a rubber stamp) ---------------------------------
def test_validator_detects_a_visit_outside_opening_hours(kb):
    destination = kb.destinations["jaipur"]
    profile = PACES["packed"]
    items = [
        ScheduleItem(1, "travel", 900, 920, label="To Birla", mode="cab", origin="base", target="birla_mandir"),
        ScheduleItem(1, "visit", 750, 790, attraction_id="birla_mandir", label="Birla Mandir"),
    ]
    checks = validate_itinerary(kb, destination, [{"day": 1, "weekday": "monday"}], items, profile, 1,
                                set(), set(), {"within_budget": True, "total": 0, "limit": 1})
    by_name = {c["name"]: c for c in checks}
    assert not by_name["Opening hours and closed days"]["passed"]
    assert not by_name["Daily time window and lunch break"]["passed"]
