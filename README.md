# Elektrica Dashboard

Rental claim-generation dashboard for Elektrica Rentals (Elektrica Holdings
LLC) — the third product on the same shared platform as VLS Dashboard.
See `docs/ADR-001-elektrica-rentals-v2.md` (approved by Jed, 2026-09-03) for
scope, architecture, and data model.

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

- `demand`, `comparable_set`, shared document generator (rental demand
  letters as first real caller)
- `outbound_log`, `communication` timeline
- `insurer_payment` + `adjuster`, historical import
- Compliance + lightweight Financials (bot's original v1 items)
- Backend/API server, frontend (deliberately last, per ADR-001)
