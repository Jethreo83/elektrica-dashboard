# SUPERSEDED — Phase 1 SQLite/FastAPI app

**Status: superseded, kept for historical record only. Do not build on
this.**

**Superseded by:** Jed's direct decision (2026-09-04, relayed by hermes):
the `elektrica.*` Postgres schema (`migrations/001-007` at the repo root,
built against `docs/ADR-001-elektrica-rentals-v2.md`) is the real,
approved scope for the Elektrica dashboard — the claim-generation-machine
flow (JotForm intake -> tracked rental -> demand generation -> JP
litigation), sharing the Neon Postgres project with VLS
(`aged-art-92489373`), with `elektrica.renter` keyed to `platform.person`
and JP litigation wired via direct reuse of `vls.valid_next_states()`.

**What this folder is:** a FastAPI + SQLAlchemy + SQLite CRUD API for six
simpler entities (Vehicle, Customer, Lease, Payment, Incident,
ComplianceItem — integer autoincrement PKs, no Neon/Postgres connection),
built in a separate bot session against `docs/original-bot-plan.md` (the
smaller-scope draft that `docs/ADR-001-elektrica-rentals-v2.md` explicitly
superseded). That session correctly flagged the two-tracks conflict and
held its commit unpushed pending Jed's review — see
`docs/OVERNIGHT_DECISIONS.md` for the full incident writeup of how it
ended up on `origin/main` anyway before that review happened, and Jed's
resulting decision.

**Why archived instead of deleted:** the code itself has real, documented
value even though the track is superseded — two genuine bugs were found
and fixed with regression tests (a Python class-namespace shadowing bug
from a field literally named `date`, and an unhandled `IntegrityError` on
deleting a row with dependent children, now a clean 409). Kept here rather
than deleted so that reasoning isn't lost, and so nobody mistakes it for
active code by finding it live in `app/` at the repo root.

**If you're looking for the real app:** there isn't one yet. Per
`README.md`'s own "Not yet built" section, the data layer
(`migrations/`) comes first, application/API/frontend code is
deliberately later — same discipline as the VLS build.
