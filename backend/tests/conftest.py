import os

# Keep tests from creating backend/itineraries.db; API tests use their own in-memory DB.
os.environ.setdefault("DATABASE_URL", "sqlite://")
