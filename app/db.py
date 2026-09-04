"""Database connection helper for the Elektrica app layer.

Same discipline as Complete Collision's app/db.py (same repo family,
copied pattern deliberately, not reinvented): the connection string is
read from an environment variable NAME passed in by the caller, never a
literal value baked into code, so it never lands in shell history /
source control / process listings.

IMPORTANT -- role/grant gap, flagged rather than silently worked around:
migrations/001_elektrica_renter.sql deliberately does NOT grant
elektrica_app INSERT on platform.person ("elektrica_app may not write new
person rows directly -- creation goes through the identity service's
match-before-create flow"). No identity-service API exists in this
codebase yet. This means:
  - Connecting as `elektrica_app`: INSERT into platform.person will be
    rejected by Postgres (no grant) -- intended production posture until
    an identity-service integration exists.
  - Connecting as `neondb_owner` (or another privileged role): INSERT
    will succeed -- fine for admin scripts/CSV backfills run by a human,
    NOT how the eventual live backend should authenticate day to day.
This module does not choose a role for you.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


def get_connection(env_var_name: str):
    """Open a new connection using the connection string held in the
    named environment variable. Raises a clear error if unset rather than
    silently trying a default."""
    conn_string = os.environ.get(env_var_name)
    if not conn_string:
        raise RuntimeError(
            f"Environment variable {env_var_name!r} is not set. Refusing to "
            "guess a default connection -- pass the env var name that holds "
            "the Neon connection string for the branch/role you intend to "
            "use (staging vs production, elektrica_app vs neondb_owner)."
        )
    return psycopg2.connect(conn_string)


@contextmanager
def cursor(env_var_name: str, autocommit: bool = False):
    """Context manager yielding a RealDictCursor; commits on clean exit,
    rolls back on exception. autocommit=False by default so multi-step
    repository functions (e.g. rental_event insert + derived state read)
    are transactional."""
    conn = get_connection(env_var_name)
    conn.autocommit = autocommit
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        conn.close()
