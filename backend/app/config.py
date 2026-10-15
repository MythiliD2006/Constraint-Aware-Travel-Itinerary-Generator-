"""Settings read from environment variables (see backend/.env.example)."""

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader so no extra dependency is needed. Real env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./itineraries.db")
CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]
PLANNER_NODE_LIMIT: int = int(os.getenv("PLANNER_NODE_LIMIT", "30000"))
