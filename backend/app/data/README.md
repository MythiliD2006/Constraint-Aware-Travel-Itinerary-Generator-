# Sample dataset

The planner works entirely from these local JSON files; no external API is called.

**Every number here is an illustrative estimate** assembled for a college project.
Entry fees, opening hours, closed days, room rates, food costs and cab fares are
approximations chosen to be internally consistent, not live prices or availability.
Check official sources before relying on any of them for a real trip.

## Files

| File | Contents |
| --- | --- |
| `categories.json` | The class hierarchy (ISA links) shared by all destinations, with inheritable properties and interests. |
| `destinations/<id>.json` | One destination: base location, cost table and attractions. |

## Attraction fields

| Field | Meaning |
| --- | --- |
| `id`, `name` | Identifier used by the planner / display name. |
| `category` | Class the attraction is an instance of (must exist in `categories.json`). |
| `lat`, `lon` | Approximate coordinates, used only to estimate travel time. |
| `hours` | One or more opening windows `[["HH:MM","HH:MM"], ...]`. A visit must fit inside a single window. |
| `closed_on` | Weekdays (lower-case) the attraction is closed. |
| `entry_fee` | Per-person fee in INR (estimate). |
| `duration` | Optional. Visit length in minutes; if omitted it is inherited from the category (`default_duration`). |
| `interests` | Optional. Extra interests for this instance on top of the inherited ones. |
| other keys | Instance-level properties that override inherited ones (e.g. `best_time`). |

## Inheritance rules

* Single-valued properties (`default_duration`, `indoor`, `best_time`, `dress_code`, ...):
  the instance's own value wins, otherwise the nearest ancestor class that defines it.
* `interests` accumulate: an attraction appeals to its own interests plus those of every ancestor.

## Travel and cost model

Defined in `app/planner/knowledge_base.py` and `app/planner/budget.py`:

* road distance = straight-line distance x 1.35
* cab: 22 km/h average + 8 min overhead, rounded up to 5 min; fare = base fare + rate per km, one vehicle per 4 people
* walking: 4.5 km/h, offered only for hops up to 1.2 km, free
* accommodation: (days - 1) nights x ceil(travellers / 2) rooms x tier rate
* food: days x travellers x tier rate per person per day

## Adding a destination

Copy an existing file in `destinations/`, keep the same structure and run `pytest`;
`KnowledgeBase` validates categories, weekdays, interests and opening windows on load.
