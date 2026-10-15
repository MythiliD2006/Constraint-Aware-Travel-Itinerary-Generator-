"""REST endpoints. All planning happens in app.planner; routes only translate HTTP."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import PLANNER_NODE_LIMIT
from .database import SavedItinerary, get_session
from .planner.knowledge_base import INTERESTS, KnowledgeBase, get_knowledge_base, to_hhmm
from .planner.itinerary import DISCLAIMER, RequestError, TripRequest, plan_trip
from .planner.logic import RULES, LogicEngine, format_atom, parse_query
from .schemas import PlanRequest, QueryRequest, SavedDetail, SavedSummary, SaveRequest

router = APIRouter(prefix="/api")


def kb_dep() -> KnowledgeBase:
    return get_knowledge_base()


def _destination(kb: KnowledgeBase, destination_id: str):
    destination = kb.destinations.get(destination_id)
    if destination is None:
        raise HTTPException(404, f"Unknown destination '{destination_id}'")
    return destination


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/destinations")
def list_destinations(kb: KnowledgeBase = Depends(kb_dep)) -> list[dict[str, Any]]:
    return [{"id": d.id, "name": d.name, "region": d.region, "summary": d.summary,
             "base": d.base.name, "attraction_count": len(d.attractions)}
            for d in kb.destinations.values()]


@router.get("/destinations/{destination_id}")
def destination_detail(destination_id: str, kb: KnowledgeBase = Depends(kb_dep)) -> dict[str, Any]:
    destination = _destination(kb, destination_id)
    attractions = []
    for a in destination.attractions.values():
        attractions.append({
            "id": a.id, "name": a.name, "category": a.category,
            "lineage": kb.lineage(a.category),
            "description": a.description,
            "hours": [f"{to_hhmm(s)}-{to_hhmm(e)}" for s, e in a.hours],
            "closed_on": list(a.closed_on),
            "entry_fee": a.entry_fee,
            "duration": kb.duration_of(a),
            "interests": [{"interest": t, "source": src} for t, src in kb.interests_of(a).items()],
            "properties": kb.all_properties(a),
        })
    return {"id": destination.id, "name": destination.name, "region": destination.region,
            "summary": destination.summary, "base": destination.base.name,
            "costs": destination.costs, "attractions": attractions,
            "interests": INTERESTS, "disclaimer": DISCLAIMER}


@router.get("/knowledge/{destination_id}")
def knowledge(destination_id: str, kb: KnowledgeBase = Depends(kb_dep)) -> dict[str, Any]:
    destination = _destination(kb, destination_id)
    facts = kb.facts_for(destination.id)
    counts: dict[str, int] = {}
    for fact in facts:
        counts[fact[0]] = counts.get(fact[0], 0) + 1
    return {
        "classes": [{"name": c.name, "parent": c.parent, "properties": c.properties,
                     "interests": list(c.interests),
                     "instances": [a.id for a in destination.attractions.values() if a.category == c.name]}
                    for c in kb.categories.values()],
        "rules": [str(rule) for rule in RULES],
        "fact_counts": counts,
        "sample_facts": [format_atom(f) for f in facts if f[0] in ("instance_of", "isa")][:12],
        "example_queries": [
            "subclass_of(Temple, ?C)",
            "member_of(?X, HeritageSite)",
            f"appeals_to(?X, nature), located_in(?X, {destination.id})",
            f"candidate(?X, spiritual, {destination.id}, monday)",
            "instance_of(?X, ?C), subclass_of(?C, PlaceOfWorship)",
        ],
    }


@router.post("/knowledge/query")
def run_query(body: QueryRequest, kb: KnowledgeBase = Depends(kb_dep)) -> dict[str, Any]:
    _destination(kb, body.destination_id)
    try:
        goals = parse_query(body.query)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    engine = LogicEngine(kb.facts_for(body.destination_id))
    answers = engine.ask(goals, limit=100)
    has_vars = any(term.startswith("?") for goal in goals for term in goal[1:])
    return {"query": [format_atom(g) for g in goals], "proved": bool(answers),
            "has_variables": has_vars, "answers": answers, "inferences": engine.inferences}


def _to_trip_request(body: PlanRequest) -> TripRequest:
    return TripRequest(**body.model_dump())


@router.post("/plan")
def create_plan(body: PlanRequest, kb: KnowledgeBase = Depends(kb_dep)) -> dict[str, Any]:
    try:
        return plan_trip(kb, _to_trip_request(body), node_limit=PLANNER_NODE_LIMIT)
    except RequestError as error:
        raise HTTPException(422, str(error)) from error


# ---- Saved itineraries -----------------------------------------------------
def _summary(row: SavedItinerary) -> dict[str, Any]:
    return {"id": row.id, "title": row.title, "destination_id": row.destination_id,
            "destination_name": row.result["destination"]["name"], "created_at": row.created_at,
            "days": row.request["days"], "total_cost": row.result["budget"]["total"],
            "budget": row.request["budget"]}


@router.post("/itineraries", response_model=SavedDetail, status_code=201)
def save_itinerary(body: SaveRequest, kb: KnowledgeBase = Depends(kb_dep),
                   session: Session = Depends(get_session)) -> dict[str, Any]:
    # The server re-runs the planner instead of trusting a client-sent schedule,
    # so a saved itinerary is always one the planner actually produced.
    try:
        result = plan_trip(kb, _to_trip_request(body.request), node_limit=PLANNER_NODE_LIMIT)
    except RequestError as error:
        raise HTTPException(422, str(error)) from error
    if result["status"] != "ok":
        raise HTTPException(422, "Only feasible itineraries can be saved")
    row = SavedItinerary(title=body.title.strip(), destination_id=body.request.destination_id,
                         request=body.request.model_dump(mode="json"), result=result)
    session.add(row)
    session.commit()
    return {**_summary(row), "request": row.request, "result": row.result}


@router.get("/itineraries", response_model=list[SavedSummary])
def list_itineraries(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.scalars(select(SavedItinerary).order_by(SavedItinerary.created_at.desc())).all()
    return [_summary(row) for row in rows]


@router.get("/itineraries/{itinerary_id}", response_model=SavedDetail)
def get_itinerary(itinerary_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    row = session.get(SavedItinerary, itinerary_id)
    if row is None:
        raise HTTPException(404, "Itinerary not found")
    return {**_summary(row), "request": row.request, "result": row.result}


@router.delete("/itineraries/{itinerary_id}", status_code=204)
def delete_itinerary(itinerary_id: int, session: Session = Depends(get_session)) -> None:
    row = session.get(SavedItinerary, itinerary_id)
    if row is None:
        raise HTTPException(404, "Itinerary not found")
    session.delete(row)
    session.commit()
