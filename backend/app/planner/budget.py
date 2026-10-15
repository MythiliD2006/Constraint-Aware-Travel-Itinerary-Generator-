"""Budget calculations.

The budget is treated as a consumable resource:

    total = accommodation + food + entry fees + local transport

Accommodation and food do not depend on which attractions are chosen, so
they are computed up front ("fixed costs"). Whatever is left is the
*activity budget* that the planner may spend on entry fees and transport;
primitive actions check it in their preconditions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .knowledge_base import PEOPLE_PER_ROOM, Destination


def rupees(amount: int) -> str:
    """Indian digit grouping: 125000 -> ₹1,25,000."""
    digits = str(abs(amount))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join(([head] if head else []) + groups) + "," + tail
    return f"{'-' if amount < 0 else ''}₹{digits}"


@dataclass
class FixedCosts:
    nights: int
    rooms: int
    accommodation: int
    food: int

    @property
    def total(self) -> int:
        return self.accommodation + self.food


def fixed_costs(destination: Destination, days: int, travelers: int, tier: str) -> FixedCosts:
    """Accommodation for (days - 1) nights and food for every day.

    A one-day trip is treated as a day trip with no overnight stay.
    """
    nights = max(days - 1, 0)
    rooms = math.ceil(travelers / PEOPLE_PER_ROOM)
    accommodation = nights * rooms * destination.costs["accommodation_per_room_night"][tier]
    food = days * travelers * destination.costs["food_per_person_day"][tier]
    return FixedCosts(nights, rooms, accommodation, food)


def summarize(destination: Destination, days: int, travelers: int, tier: str,
              budget: int, entry_fees: int, transport: int) -> dict[str, Any]:
    fixed = fixed_costs(destination, days, travelers, tier)
    total = fixed.total + entry_fees + transport
    return {
        "currency": "INR",
        "limit": budget,
        "accommodation": fixed.accommodation,
        "food": fixed.food,
        "entry_fees": entry_fees,
        "local_transport": transport,
        "total": total,
        "remaining": budget - total,
        "within_budget": total <= budget,
        "nights": fixed.nights,
        "rooms": fixed.rooms,
        "tier": tier,
        "notes": [
            f"{fixed.nights} night(s) x {fixed.rooms} room(s) at the {tier} rate.",
            f"Food estimated per person per day for {travelers} traveller(s).",
            "Entry fees are per-person estimates; transport assumes shared autos/cabs.",
        ],
    }


def cheapest_trip_cost(destination: Destination, days: int, travelers: int) -> int:
    """Lowest possible fixed cost (budget tier), used in failure suggestions."""
    return fixed_costs(destination, days, travelers, "budget").total
