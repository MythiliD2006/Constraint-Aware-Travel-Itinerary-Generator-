# Constraint-Aware Travel Itinerary Generator Using HTN Planning

A web application that builds day-by-day travel itineraries with a **Hierarchical Task Network (HTN) planner**
written in Python. The planner decomposes a trip into days and stops, checks opening hours, travel time, a
daily time window, a lunch break and the budget at every step, and backtracks when a choice leads to a dead end.
When no itinerary is possible it explains which constraint is in the way.

No LLM or paid API is involved: the schedule comes entirely from the planner and a small local dataset.

> The sample data (three destinations: Jaipur, Mysuru, Puducherry) is a curated set of **illustrative
> estimates**. Prices, opening hours and travel times are not live data. See
> [`backend/app/data/README.md`](backend/app/data/README.md).

## What it does

1. Choose a destination, start date, number of days, travellers, budget, stay tier, pace and interests;
   optionally mark attractions as must-visit or skip.
2. The backend runs the HTN planner and returns a schedule for each day.
3. The UI shows each day on a time axis with travel legs, waits and the lunch break, plus the cost breakdown.
4. Every chosen attraction comes with the reasons it was chosen; every other attraction with the reason it was left out.
5. The finished schedule is re-checked by an independent validator (opening hours, travel times, day window,
   budget, must-visit/excluded).
6. *Regenerate* asks for an alternative ordering of equally ranked optional stops; *Save* stores the itinerary in SQLite.
7. The *Knowledge base* page shows the class hierarchy, inherited properties and lets you run logic queries.

## Project structure

```
backend/
  app/
    main.py            FastAPI app, CORS
    routes.py          REST endpoints
    schemas.py         Pydantic request/response models
    database.py        SQLAlchemy model + SQLite session
    config.py          environment variables
    data/              sample dataset (categories + destinations) and its documentation
    planner/
      knowledge_base.py  ISA hierarchy, property inheritance, facts, travel-time model
      logic.py           unification + SLD resolution (Datalog subset)
      htn.py             generic HTN planner: decomposition, backtracking, decomposition tree
      travel_domain.py   tasks, methods and primitive operators (preconditions/effects)
      constraints.py     time constraints and the independent itinerary validator
      budget.py          cost calculations
      itinerary.py       request -> pre-checks -> search -> validation -> explanations
  tests/               pytest suite (knowledge/logic, planner, API)
frontend/
  src/
    api/               axios client and TypeScript types
    components/        form, day timeline, itinerary view, nav, status views
    pages/             plan, saved list/detail, knowledge base
    lib/format.ts      formatting helpers
docs/ACADEMIC_NOTES.md how each AI concept is implemented, with pointers into the code
```

## Running locally

Requirements: Python 3.11+ and Node.js 20+.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional; defaults work for local use
uvicorn app.main:app --reload --port 8000
```

API docs are then at http://localhost:8000/docs. Saved itineraries go to `backend/itineraries.db`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./itineraries.db` | SQLAlchemy database URL |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Frontend origins allowed to call the API |
| `PLANNER_NODE_LIMIT` | `30000` | Maximum decomposition steps per planning request |

### Frontend

```bash
cd frontend
npm install
cp .env.example .env               # sets VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open http://localhost:5173. For a production build: `npm run build` (output in `frontend/dist`).

### Tests

```bash
cd backend
pytest
```

## REST API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/destinations` | List sample destinations |
| GET | `/api/destinations/{id}` | Attractions with hours, fees, ISA lineage and inherited properties |
| GET | `/api/knowledge/{id}` | Class hierarchy, rules and fact counts |
| POST | `/api/knowledge/query` | Run a logic query, e.g. `member_of(?X, HeritageSite)` |
| POST | `/api/plan` | Generate an itinerary (returns `status: "ok"` or `"infeasible"` with reasons) |
| POST | `/api/itineraries` | Save an itinerary (the server re-runs the planner for the given request) |
| GET | `/api/itineraries` | List saved itineraries |
| GET | `/api/itineraries/{id}` | Get one saved itinerary |
| DELETE | `/api/itineraries/{id}` | Delete a saved itinerary |

## Limitations

- Only three sample destinations with 11 attractions each; all values are estimates.
- Travel time is a straight-line estimate (x1.35 road factor, fixed average speed), not real routing or traffic.
- One fixed base per destination; the stay is not chosen or located by the planner.
- The planner looks for a *feasible* itinerary guided by a heuristic, not an optimal one.
- No user accounts: saved itineraries are shared by everyone using the same backend.
- Planning graphs and SAT-based planning are not implemented; they are listed as possible extensions in
  [`docs/ACADEMIC_NOTES.md`](docs/ACADEMIC_NOTES.md).
