"""
Database setup for the Elektrica Rentals dashboard (Phase 1).

Scope note (read this before touching Neon/Postgres anything):
This app is a SEPARATE track from the elektrica.* schema on the shared Neon
Postgres project (aged-art-92489373) that a prior session built out via
migrations/001-006 in this same repo, reconciled against
docs/ADR-001-elektrica-rentals-v2.md (the "claim-generation machine" scope,
shared platform.person/JP-engine with VLS). That work is real, committed,
and partially promoted to production -- but it is NOT what Jed's Phase 1
instruction asked for. Jed's own words for this task: "FastAPI + SQLite or
whatever you specified" and named entities (Vehicle, Customer, Lease,
Payment, Incident, ComplianceItem) that match the ORIGINAL, simpler
workspace/PLAN.md draft, not the v2 handoff-scope document.

Decision (logged in LOG.md too): build exactly what this instruction asks
for -- a local SQLite-backed FastAPI app with the six original entities --
as its own self-contained layer. Do NOT touch the elektrica.* Postgres
schema, do NOT open a connection to the Neon project, do NOT read/write
VLS/platform.* anything. If Jed wants these two tracks reconciled or one
abandoned, that's a decision for him, flagged in LOG.md as an open question.

This module deliberately uses a local file-based SQLite database
(data/elektrica.db) with no network calls at all.
"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{(DATA_DIR / 'elektrica.db').as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a DB session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables if they don't exist yet.

    Phase 1 decision: no migration tool (Alembic) yet -- SQLite + a single
    create_all() call is sufficient for a single-developer local v1. Logged
    as an open question in LOG.md for when the schema needs to evolve
    without wiping data.
    """
    from app import models  # noqa: F401  (ensures models are registered on Base)

    Base.metadata.create_all(bind=engine)
