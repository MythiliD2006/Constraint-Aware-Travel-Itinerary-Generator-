# Academic notes: how each concept is implemented

Each section names the concept, where it lives in the code, and a test that demonstrates it.
Paths are relative to `backend/app/planner/` unless stated otherwise.

## 1. Knowledge representation and predicate logic

The domain is stored as structured data (`data/*.json`) and loaded into `KnowledgeBase`
(`knowledge_base.py`). The same knowledge is exported as ground atoms by `KnowledgeBase.facts_for()`:

```
isa(Temple, PlaceOfWorship)          instance_of(birla_mandir, Temple)
has_interest(PlaceOfWorship, spiritual)
located_in(birla_mandir, jaipur)     open_on(birla_mandir, monday)
fee_band(birla_mandir, free)
```

Rules are definite (Horn) clauses in `logic.py` (`RULES`):

```
subclass_of(?C, ?D) :- isa(?C, ?D).
subclass_of(?C, ?E) :- isa(?C, ?D), subclass_of(?D, ?E).
member_of(?I, ?C)   :- instance_of(?I, ?C).
member_of(?I, ?D)   :- instance_of(?I, ?C), subclass_of(?C, ?D).
appeals_to(?I, ?T)  :- has_interest(?I, ?T).
appeals_to(?I, ?T)  :- member_of(?I, ?C), has_interest(?C, ?T).
candidate(?I, ?T, ?City, ?Day) :- located_in(?I, ?City), appeals_to(?I, ?T), open_on(?I, ?Day).
```

Closed days are represented by the *absence* of an `open_on` fact, so queries use the closed-world assumption.

## 2. Instance and ISA relationships

* ISA links between classes: `categories.json` (`"isa": "PlaceOfWorship"`), traversed by `KnowledgeBase.lineage()`.
* Instance links: each attraction's `category` field, exported as `instance_of`.
* Tests: `test_lineage_follows_isa_links`, `test_transitive_subclass`, `test_member_of_via_isa`
  (`tests/test_knowledge_and_logic.py`).

## 3. Property inheritance

`KnowledgeBase.get_property()` looks on the instance first, then up the ISA chain, so the most specific value wins
(default inheritance with overriding). Interests instead *accumulate* along the chain (`interests_of()`).

Example (Birla Mandir, ISA chain Temple > PlaceOfWorship > HeritageSite > Attraction):

| Property | Value | Source |
| --- | --- | --- |
| default_duration | 40 | instance (overrides PlaceOfWorship's 45) |
| footwear_removed | true | Temple |
| dress_code | modest clothing expected | PlaceOfWorship |
| best_time | any | Attraction |

The planner really uses inherited values: visit length (`default_duration`), time-of-day preference (`best_time`)
and visitor notes shown in the timeline all come from inheritance.
Tests: `test_most_specific_property_wins`, `test_duration_is_inherited_when_instance_omits_it`,
`test_interests_accumulate_down_the_hierarchy`.

## 4. Unification and resolution

`logic.py` implements a deliberately small subset:

* **Terms**: constants and variables (`?X`). No function symbols (a Datalog subset), so no occurs check is needed.
* **Unification** (`unify`): returns the most general unifier extending a substitution, or `None` on a clash of
  constants, predicate names or arity.
* **Resolution** (`LogicEngine._solve`): SLD resolution. To prove a goal, its negation is (conceptually) added to the
  clause set; the left-most goal is resolved against a clause whose head unifies with it, after renaming the clause's
  variables apart; the body replaces the goal. Reaching an empty goal list is deriving the empty clause, i.e. a
  refutation, and the substitution gives the answer. Search is depth-first with backtracking.
* **Termination**: recursive rules recurse on the right after a base fact, and the ISA hierarchy is acyclic (checked
  on load), so every query terminates. A depth limit is kept as a safety net.

The planner uses resolution for real work: `itinerary.match_interests()` asks
`appeals_to(?X, T), located_in(?X, destination)` for each chosen interest to find candidate attractions.
`test_resolution_agrees_with_procedural_inheritance` checks that resolution and the procedural inheritance
code give identical answers for every attraction. The *Knowledge base* page lets you run queries and see the proof
steps.

## 5. Classical planning and state-space search

* **State** (`travel_domain.TripState`): day, clock time, location, visited set, stops today, lunch taken, money spent.
  It is immutable; actions return new states.
* **Actions** (operators) have explicit **preconditions** and **effects**, e.g. `op_visit`:
  - preconditions: at the attraction; not visited; open on this weekday; the whole visit fits in one opening window
    (waiting at most 90 min); lunch can still start by 14:30; it is still possible to get back to base before the
    day ends; fee plus fare home fits the remaining budget;
  - effects: time advances to the end of the visit, the attraction is marked visited, fees are added.
* Search moves forward from the initial state through applied actions (forward state-space search), with depth-first
  backtracking (`htn.HTNPlanner._seek`).

## 6. HTN task decomposition

`htn.py` is a domain-independent, total-order HTN planner in the style of SHOP. `travel_domain.py` defines the network:

```
plan_trip(n)        -> plan_day(1) ... plan_day(n), verify_must_visits
plan_day(d)         -> begin_day(d), fill_day(d), end_day(d)
fill_day(d)         -> visit_attraction(A), fill_day(d)     one method per candidate A, best first
                     | have_lunch, fill_day(d)
                     | go_back_to_base
visit_attraction(A) -> travel(A, walk), visit(A)           only for hops up to 1.2 km
                     | travel(A, cab), visit(A)
go_back_to_base     -> have_lunch, go_back_to_base          if lunch not taken yet
                     | return_to_base(walk) | return_to_base(cab)
```

When a primitive's precondition fails, the branch dies and the planner returns to the most recent compound task
with untried methods (chronological backtracking). The successful decomposition is returned as a tree and shown in the
UI under "How the planner got here".

Tests: `test_htn_backtracks_to_next_method_when_a_later_precondition_fails` (toy domain),
`test_search_failure_names_the_conflicting_must_visits` (exhaustive search on a real request).

### Search control

* **Method ordering heuristic** (`rank_candidates`): must-visits first, then interest matches, nearby stops, and
  morning/evening preferences. A non-zero seed adds small random tie-breaking; this is how *Regenerate* works.
* **Admissible pruning**: `end_day` fails if an unvisited must-visit has no open day left; optional stops are refused
  if, even with zero travel time, today's remaining "last chance" must-visits would no longer fit
  (`crowds_out_must_visits`). These bounds never overestimate, so they cannot remove a branch that leads to a plan.
* **Node limit**: the search stops after `PLANNER_NODE_LIMIT` steps and reports that it did.

## 7. Time and resource constraints

| Constraint | Where enforced |
| --- | --- |
| Opening windows (including split hours like 06:00-12:00 and 15:00-20:00) | `constraints.earliest_visit_start`, `op_visit` |
| Closed weekdays | `constraints.is_open_on`, `op_visit`, `op_end_day` |
| Activity duration | inherited `default_duration`, `op_visit` |
| Travel time between stops | `knowledge_base.estimate_leg`, `op_travel`, `op_return_to_base` |
| Daily time window and stop limit (pace) | `constraints.PACES`, `op_visit`, `m_fill_day` |
| Lunch break between 12:00 and 14:30 | `op_have_lunch`, `op_travel`, `op_visit` |
| Budget (consumable resource) | `budget.py`: fixed costs first, the rest is the activity budget checked by operators |

After the search, `constraints.validate_itinerary` re-checks the finished schedule from scratch.
`test_validator_detects_a_visit_outside_opening_hours` shows that it rejects a bad schedule.

## Failure explanations

Two layers:

1. **Pre-checks** (`itinerary.precheck`) catch clear-cut problems before search: fixed costs above the budget, a
   must-visit closed on every trip day, a visit longer than any opening window, an unreachable round trip, too many
   must-visits for the chosen pace, must-visit fees above the activity budget.
2. **Search diagnostics**: every failed precondition is counted per attraction. If the search fails, the most frequent
   concrete reasons for each must-visit are reported (e.g. "a 150-min visit would run past closing at 17:30").

## Possible extensions (not implemented)

* Planning graph (GraphPlan) to compute reachability bounds before search.
* Encoding a single day as a SAT problem and comparing with HTN search.
* Optimising (rather than satisfying) cost or travel time, e.g. with branch and bound.
