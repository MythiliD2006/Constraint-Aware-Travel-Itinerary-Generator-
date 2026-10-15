"""Pydantic request/response schemas for the REST API."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Interest = Literal["history", "culture", "art", "spiritual", "nature", "shopping"]


class PlanRequest(BaseModel):
    destination_id: str = Field(examples=["jaipur"])
    start_date: date
    days: int = Field(ge=1, le=7)
    travelers: int = Field(ge=1, le=8)
    budget: int = Field(ge=500, le=1_000_000, description="Total trip budget in INR")
    accommodation: Literal["budget", "standard", "comfort"] = "standard"
    pace: Literal["relaxed", "moderate", "packed"] = "moderate"
    interests: list[Interest] = []
    must_visit: list[str] = []
    exclude: list[str] = []
    seed: int = Field(default=0, ge=0, le=10_000,
                      description="0 = default ordering; other values reorder equally ranked stops")

    @field_validator("interests", "must_visit", "exclude")
    @classmethod
    def no_duplicates(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class SaveRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    request: PlanRequest


class SavedSummary(BaseModel):
    id: int
    title: str
    destination_id: str
    destination_name: str
    created_at: datetime
    days: int
    total_cost: int
    budget: int


class SavedDetail(SavedSummary):
    request: dict[str, Any]
    result: dict[str, Any]


class QueryRequest(BaseModel):
    destination_id: str
    query: str = Field(min_length=3, max_length=300, examples=["appeals_to(?X, history)"])
