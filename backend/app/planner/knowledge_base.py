"""Knowledge base: destinations, attractions and the category (ISA) hierarchy.

Knowledge representation used here
----------------------------------
* Categories form a tree through ISA links, e.g. Temple ISA PlaceOfWorship ISA
  HeritageSite ISA Attraction (see data/categories.json).
* Every attraction is an INSTANCE of exactly one category
  (amber_fort INSTANCE_OF Fort).
* Property inheritance:
    - single-valued properties (default_duration, indoor, best_time, ...) are
      looked up on the instance first, then up the ISA chain; the most
      specific value wins (default reasoning, values can be overridden);
    - the multi-valued "interests" property accumulates: an attraction appeals
      to every interest declared on its own record and on any ancestor class.
* The same knowledge is also exported as predicate-logic facts
  (``facts_for``) so that ``logic.py`` can answer queries by resolution.

All numbers in the dataset are illustrative estimates, not live data.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
INTERESTS = ["history", "culture", "art", "spiritual", "nature", "shopping"]

# ---------------------------------------------------------------------------
# Travel model (documented estimate, identical for every destination)
# ---------------------------------------------------------------------------
ROAD_FACTOR = 1.35          # road distance ~ 1.35 x straight-line distance
CAB_SPEED_KMPH = 22.0       # average city speed for an auto/cab
CAB_OVERHEAD_MIN = 8        # finding a vehicle, parking, entry queues
WALK_SPEED_KMPH = 4.5
MAX_WALK_KM = 1.2           # walking is only offered for short hops
PEOPLE_PER_VEHICLE = 4
PEOPLE_PER_ROOM = 2


def to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def round_up_to_5(minutes: float) -> int:
    return int(math.ceil(minutes / 5.0) * 5)


@dataclass(frozen=True)
class Category:
    name: str
    parent: str | None
    properties: dict[str, Any]
    interests: tuple[str, ...]


@dataclass(frozen=True)
class Attraction:
    id: str
    name: str
    category: str
    lat: float
    lon: float
    hours: tuple[tuple[int, int], ...]      # opening windows in minutes after midnight
    closed_on: tuple[str, ...]              # weekday names
    entry_fee: int                          # per person, INR (estimate)
    description: str
    own_properties: dict[str, Any] = field(default_factory=dict)
    own_interests: tuple[str, ...] = ()


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float


@dataclass
class Destination:
    id: str
    name: str
    region: str
    summary: str
    base: Place
    costs: dict[str, Any]
    attractions: dict[str, Attraction]


class KnowledgeBase:
    """In-memory knowledge base loaded from the JSON files in ``data/``."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        raw_categories = json.loads((data_dir / "categories.json").read_text())
        self.categories: dict[str, Category] = {
            name: Category(
                name=name,
                parent=spec["isa"],
                properties=dict(spec.get("properties", {})),
                interests=tuple(spec.get("interests", [])),
            )
            for name, spec in raw_categories.items()
            if not name.startswith("_")
        }
        self.destinations: dict[str, Destination] = {}
        for path in sorted((data_dir / "destinations").glob("*.json")):
            destination = self._load_destination(json.loads(path.read_text()))
            self.destinations[destination.id] = destination
        self._check_consistency()

    # -- loading -------------------------------------------------------------
    def _load_destination(self, raw: dict[str, Any]) -> Destination:
        attractions: dict[str, Attraction] = {}
        for item in raw["attractions"]:
            # Anything that is not a structural field is an instance-level
            # property that overrides the inherited value.
            structural = {"id", "name", "category", "lat", "lon", "hours", "closed_on",
                          "entry_fee", "description", "interests", "duration"}
            own = {k: v for k, v in item.items() if k not in structural}
            if "duration" in item:
                own["default_duration"] = item["duration"]
            attractions[item["id"]] = Attraction(
                id=item["id"],
                name=item["name"],
                category=item["category"],
                lat=item["lat"],
                lon=item["lon"],
                hours=tuple((to_minutes(a), to_minutes(b)) for a, b in item["hours"]),
                closed_on=tuple(item.get("closed_on", [])),
                entry_fee=int(item["entry_fee"]),
                description=item.get("description", ""),
                own_properties=own,
                own_interests=tuple(item.get("interests", [])),
            )
        base = raw["base"]
        return Destination(
            id=raw["id"],
            name=raw["name"],
            region=raw["region"],
            summary=raw["summary"],
            base=Place(base["name"], base["lat"], base["lon"]),
            costs=raw["costs"],
            attractions=attractions,
        )

    def _check_consistency(self) -> None:
        """Fail fast on data errors instead of producing odd plans later."""
        for category in self.categories.values():
            if category.parent is not None and category.parent not in self.categories:
                raise ValueError(f"{category.name} ISA unknown class {category.parent}")
            self.lineage(category.name)  # raises on cycles
        for destination in self.destinations.values():
            for attraction in destination.attractions.values():
                if attraction.category not in self.categories:
                    raise ValueError(f"{attraction.id}: unknown category {attraction.category}")
                for start, end in attraction.hours:
                    if start >= end:
                        raise ValueError(f"{attraction.id}: bad opening window")
                for day in attraction.closed_on:
                    if day not in WEEKDAYS:
                        raise ValueError(f"{attraction.id}: bad weekday {day}")
                for interest in attraction.own_interests:
                    if interest not in INTERESTS:
                        raise ValueError(f"{attraction.id}: unknown interest {interest}")

    # -- ISA reasoning and inheritance ----------------------------------------
    def lineage(self, category_name: str) -> list[str]:
        """Category followed by all its ancestors, most specific first."""
        chain: list[str] = []
        current: str | None = category_name
        while current is not None:
            if current in chain:
                raise ValueError(f"ISA cycle at {current}")
            chain.append(current)
            current = self.categories[current].parent
        return chain

    def is_a(self, category_name: str, ancestor: str) -> bool:
        return ancestor in self.lineage(category_name)

    def get_property(self, attraction: Attraction, prop: str) -> tuple[Any, str] | None:
        """Return (value, where it came from) using most-specific-wins inheritance."""
        if prop in attraction.own_properties:
            return attraction.own_properties[prop], attraction.id
        for category_name in self.lineage(attraction.category):
            props = self.categories[category_name].properties
            if prop in props:
                return props[prop], category_name
        return None

    def all_properties(self, attraction: Attraction) -> dict[str, dict[str, Any]]:
        """Every visible property with its source, for display and debugging."""
        names: set[str] = set(attraction.own_properties)
        for category_name in self.lineage(attraction.category):
            names.update(self.categories[category_name].properties)
        result: dict[str, dict[str, Any]] = {}
        for name in sorted(names):
            found = self.get_property(attraction, name)
            if found is not None:
                result[name] = {"value": found[0], "source": found[1]}
        return result

    def interests_of(self, attraction: Attraction) -> dict[str, str]:
        """interest -> the class (or instance) that contributed it."""
        sources: dict[str, str] = {}
        for interest in attraction.own_interests:
            sources.setdefault(interest, attraction.id)
        for category_name in self.lineage(attraction.category):
            for interest in self.categories[category_name].interests:
                sources.setdefault(interest, category_name)
        return sources

    def duration_of(self, attraction: Attraction) -> int:
        found = self.get_property(attraction, "default_duration")
        assert found is not None, "Attraction class always defines default_duration"
        return int(found[0])

    # -- facts for the logic engine ---------------------------------------------
    def facts_for(self, destination_id: str) -> list[tuple[str, ...]]:
        """Ground atoms describing the hierarchy and one destination.

        Atoms are tuples: (predicate, arg1, arg2, ...).
        """
        facts: list[tuple[str, ...]] = []
        for category in self.categories.values():
            if category.parent:
                facts.append(("isa", category.name, category.parent))
            for interest in category.interests:
                facts.append(("has_interest", category.name, interest))
        destination = self.destinations[destination_id]
        for attraction in destination.attractions.values():
            facts.append(("instance_of", attraction.id, attraction.category))
            facts.append(("located_in", attraction.id, destination.id))
            for interest in attraction.own_interests:
                facts.append(("has_interest", attraction.id, interest))
            for day in WEEKDAYS:
                if day not in attraction.closed_on:
                    facts.append(("open_on", attraction.id, day))
            facts.append(("fee_band", attraction.id, "free" if attraction.entry_fee == 0 else "paid"))
        return facts


# ---------------------------------------------------------------------------
# Travel estimates
# ---------------------------------------------------------------------------
def straight_line_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometres."""
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Leg:
    mode: str           # "walk" or "cab"
    road_km: float
    minutes: int
    cost: int           # for the whole group


def estimate_leg(a: Place | Attraction, b: Place | Attraction, mode: str, travelers: int,
                 costs: dict[str, Any]) -> Leg | None:
    """Estimate one journey. Returns None if the mode is not allowed for it."""
    road_km = round(straight_line_km(a.lat, a.lon, b.lat, b.lon) * ROAD_FACTOR, 2)
    if mode == "walk":
        if road_km > MAX_WALK_KM:
            return None
        return Leg("walk", road_km, max(5, round_up_to_5(road_km / WALK_SPEED_KMPH * 60)), 0)
    vehicles = math.ceil(travelers / PEOPLE_PER_VEHICLE)
    minutes = round_up_to_5(road_km / CAB_SPEED_KMPH * 60 + CAB_OVERHEAD_MIN)
    cost = vehicles * round(costs["cab_base_fare"] + costs["cab_rate_per_km"] * road_km)
    return Leg("cab", road_km, minutes, cost)


@lru_cache(maxsize=1)
def get_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase()
