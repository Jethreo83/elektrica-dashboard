# Elektrica Dashboard

Rental claim-generation dashboard for Elektrica Rentals (Elektrica Holdings
LLC) — the third product on the same shared platform as VLS Dashboard.
See `docs/ADR-001-elektrica-rentals-v2.md` (approved by Jed, 2026-09-03) for
scope, architecture, and data model.

## IMPORTANT: two parallel tracks exist in this repo right now

This repo currently holds **two different, not-yet-reconciled build
tracks** for Elektrica. Read this section before touching either one.

1. **`elektrica.*` Postgres schema** (migrations/001-006, this README's
   original content below) — built against `docs/ADR-001-elektrica-rentals-v2.md`
   ("v2"), the larger claim-generation-machine scope reconciled with VLS's
   handoff doc. Lives on the shared Neon project `aged-art-92489373`.
   Migration 001 is promoted to production; 002-006 are staging-only.
   No application code was ever built against this schema.

2. **`app/` FastAPI + SQLite Phase 1 scaffold** (added the session Jed said
   "ADR-001 plan is approved, begin Phase 1 implementation" and named
   entities Vehicle/Customer/Lease/Payment/Incident/ComplianceItem) — built
   against the **original**, smaller-scope `docs/original-bot-plan.md`
   draft, not the v2 document. Fully local, SQLite-backed, no Postgres/Neon
   connection at all. See `app/` section below.

**Open question for Jed (flagged, not resolved unilaterally):** these two
tracks model overlapping concepts (Vehicle vs. `elektrica.vehicle`,
Lease/Customer vs. `elektrica.rental`/`elektrica.renter`) with incompatible
primary-key conventions (integer autoincrement vs. UUID-keyed to
`platform.person`) and no data compatibility between them. Jed's Phase 1
instruction named the original doc's simpler entities verbatim, so that's
what got built — but this needs a real reconciliation decision (migrate one
into the other? keep both — one for internal ops, one for the claim
machine? drop one?) before either track goes much further. Logged in
`workspace/LOG.md` in the bot's Hermes profile as an open question.

## Phase 1 app (`app/`) — local FastAPI + SQLite CRUD API

Status: **built and tested this session.** Local-only, no auth, no
deployment, no external exposure — per standing rule, nothing here has been
pushed anywhere externally beyond this git repo (and this repo itself
hasn't been pushed since Phase 1 started; see LOG.md for exact commit/push
status at hand-off).

Entities implemented (matching `docs/original-bot-plan.md` section 4):
Vehicle, Customer, Lease, Payment, Incident, ComplianceItem. Full CRUD
(create/list/get/patch/delete) for each, plus:
- FK validation on create/update (e.g. a Lease's `vehicle_id`/`customer_id`
  must exist) — returns 422, not a DB-level crash.
- FK-dependency guards on delete (e.g. can't delete a Vehicle that still
  has Leases pointing at it) — returns 409 with an explanation, not a bare
  500. (This was a real bug caught during manual testing this session —
  see LOG.md.)
- `GET /summary` — at-a-glance fleet/lease/payment/incident/compliance
  counts, matching the original plan's "Reporting / home view" item.
- `GET /health` — liveness check.
- Auto-generated interactive API docs at `/docs` (FastAPI/Swagger UI).

Run locally:
```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8420
```
Then visit `http://127.0.0.1:8420/docs`. Data persists to
`data/elektrica.db` (gitignored, created automatically on first run).

Run the test suite (11 tests, all passing as of this session — includes
regression tests for the delete-dependency bug above):
```bash
python -m pytest tests/ -v
```

Not yet built for this track: any frontend/UI (API only so far), auth
(single-user local tool, fine for now but flagged), Alembic/migration
tooling (schema changes currently require recreating the SQLite file — see
`app/database.py` docstring), soft-delete/audit history.

---

## `elektrica.*` Postgres schema track (original README content, v2 ADR)

## Status (as of migration 001, tag `elektrica-migration-001`)

**No application/API/frontend exists yet** — data layer only, same
build-order discipline as VLS (schema first).

### Schema — production (Neon project `aged-art-92489373`)

- **`elektrica.renter`** — Elektrica's own party table, keyed to
  `platform.person` (shared with VLS). Identical pattern to `vls.client`.
- **RLS on `platform.person`** — `elektrica_app` role sees a person row only
  if a matching `elektrica.renter` row exists, same mechanism as
  `vls_app` / `vls.client` (VLS migration 004). Verified live: cross-schema
  visibility, blocked direct INSERT, identity-service bypass — see
  `scripts/verify_001.sql`.

### Schema — staging only, NOT promoted

- **`elektrica.vehicle`** (`migrations/002_elektrica_vehicle.sql`) —
  `class` and `tracking_system` columns are confirmed real (Jed,
  2026-09-03), but their **enum value sets are placeholder**, taken from
  handoff prose, pending the real Fleet sheet export (blocked on Elektrica
  Google OAuth restoration — see `docs/BUILD_LOG.md`). File carries an
  explicit DO-NOT-PROMOTE banner. Applied to staging for continued dev only.
- **`elektrica.rental` + `elektrica.rental_event`** (`migrations/003_elektrica_rental.sql`)
  — the spine (handoff §2.3) plus an append-only event log, same pattern as
  `vls.case`/`vls.case_event`. Covers only Elektrica's own lifecycle portion
  (`active` through `needs_served`); deliberately does not wire the JP
  litigation state machine onto `needs_served` — that's an open
  architecture question (ADR-001 v2 §7 item 5, queued in
  `docs/OVERNIGHT_DECISIONS.md`). `body_shop`/`rental_type` are
  placeholder-shape free text pending the real Rental Management sheet
  export. Staging-only.
- **`elektrica.rental_proposal`** (`migrations/004_elektrica_rental_proposal.sql`)
  — bot API contract stub (handoff §1.7). No placeholder fields — shape
  taken directly from the handoff spec. Immutable except a one-time
  pending -> accepted/rejected decision; accepting a proposal never
  auto-writes `elektrica.rental`, by design. Inherits staging-only status
  mechanically via its FK to `elektrica.rental`.
- **`elektrica.document_template` / `elektrica.document` / `elektrica.outbound_log`**
  (`migrations/005_elektrica_document.sql`) — document generator
  storage/log layer (handoff §1.3), scoped to Rentals template families
  only. Built inside `elektrica`, not `platform.*` — queued as an open
  placement decision in `docs/OVERNIGHT_DECISIONS.md` since VLS hasn't
  built a document generator yet (ADR-001's extraction rule isn't
  satisfied). Append-only generation log with output-hash enforcement;
  `documents_never_sent` view implements the handoff's literal
  "generated but never sent" visibility requirement. Staging-only.
- **`elektrica.demand` + `elektrica.comparable_set`** (`migrations/006_elektrica_demand.sql`)
  — the demand object (handoff §2.3) and its frozen market-comparable
  snapshot (§2.8). `demand_type` and the `prior_demand_id`
  shortfall-pre-fill chain are handoff-literal; `demand.status`'s value
  list and `carrier_name`/`adjuster_name` are placeholder (no
  insurance_carrier/adjuster tables yet). `comparable_set` is immutable
  from creation. `aging_demands` view implements the "45 days with no
  offer" aging signal. Staging-only.

Full narrative, decisions, and verification results: `docs/BUILD_LOG.md`.

## Deploy process

Identical discipline to VLS dashboard: every migration applied to the Neon
`staging` branch first, verified with a companion `scripts/verify_NNN.sql`
by direct query (not exit code), staging reset to a clean mirror of
production, then promoted — but **only once any placeholder fields in that
migration are confirmed against real source data**. Migrations with
placeholder fields stay staging-only indefinitely until corrected.

```bash
# apply to staging
neon connection-string staging --project-id aged-art-92489373 \
  --database-name neondb --role-name neondb_owner --psql -- -f migrations/00N_x.sql

# verify
neon connection-string staging --project-id aged-art-92489373 \
  --database-name neondb --role-name neondb_owner --psql -- -f scripts/verify_00N.sql

# reset staging clean, then promote (confirmed migrations only)
neon branches reset staging --project-id aged-art-92489373 --parent
neon connection-string production --project-id aged-art-92489373 \
  --database-name neondb --role-name neondb_owner --psql -- -f migrations/00N_x.sql
```

## Shared platform

Same Neon Postgres project as VLS Dashboard (`aged-art-92489373`).
`elektrica.renter` references `platform.person` cross-schema, same pattern
as `vls.client`. The JP court state machine (`vls.valid_next_states()`,
VLS migration 002) will be imported as a dependency for Elektrica Rentals'
JP-only litigation branch, not forked.

## Not yet built

- `communication` timeline (comms auto-matching, handoff §2.6)
- `insurer_payment` + `adjuster`, historical import
- Compliance + lightweight Financials (bot's original v1 items)
- Backend/API server, frontend (deliberately last, per ADR-001)
