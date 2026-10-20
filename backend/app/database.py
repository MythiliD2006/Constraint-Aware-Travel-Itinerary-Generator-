"""SQLite storage for saved itineraries (SQLAlchemy 2.0 style)."""

from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import JSON, DateTime, Integer, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class SavedItinerary(Base):
    __tablename__ = "saved_itineraries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    destination_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=lambda: datetime.now(timezone.utc))
    request: Mapped[dict] = mapped_column(JSON)     # the TripRequest that produced it
    result: Mapped[dict] = mapped_column(JSON)      # the planner output as shown to the user


def make_engine(url: str = DATABASE_URL):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    if engine.dialect.name == "postgresql":
        # Serialize schema creation when multiple dev-server/reloader processes
        # start together (common with PostgreSQL transaction poolers).
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(73120491)"))
            Base.metadata.create_all(connection)
        return
    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
