"""FastAPI application entry point.

Run from the backend/ folder:   uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .database import init_db
from .planner.knowledge_base import get_knowledge_base
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    get_knowledge_base()      # load and validate the dataset at startup
    yield


app = FastAPI(
    title="Constraint-Aware Travel Itinerary Generator",
    description="HTN planning over a local knowledge base of sample destinations.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(router)
