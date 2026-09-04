# Elektrica Dashboard

Rental claim-generation dashboard for Elektrica Rentals (Elektrica Holdings
LLC) — the third product on the same shared platform as VLS Dashboard.
See `docs/ADR-001-elektrica-rentals-v2.md` (approved by Jed, 2026-09-03) for
scope, architecture, and data model.

## Resolved: this repo briefly had two build tracks; v2 Postgres won

An earlier session built a smaller-scope FastAPI + SQLite CRUD app against
the *original* pre-v2 ADR draft, in parallel with the `elektrica.*`
Postgres schema below. Jed's decision (2026-09-04, relayed by hermes): the
v2 claim-generation-machine scope on Postgres — everything in
`migrations/`, this README's main content — is the real, approved
architecture. The SQLite track is superseded and archived at
`docs/superseded/phase1-sqlite-app/` (kept for its two documented bug
fixes, not as active code). Full incident writeup of how that commit
briefly ended up on `origin/main` before Jed's review: `docs/OVERNIGHT_DECISIONS.md`.



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
- **`elektrica.staff_user`** (`migrations/011_elektrica_staff_user.sql`)
  — staff/role table for the shell launcher's Elektrica door, modeled on
  `vls.staff_user`/`collision.staff_user`. Role enum (`owner`, `staff`)
  confirmed final by Jed — no placeholder fields. Verified against a
  staging branch mirroring production exactly before promoting — see
  `scripts/verify_011.sql`.

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
- **`platform.document_template` / `platform.document` / `platform.outbound_log`**
  (`migrations/005_elektrica_document.sql`, relocated by
  `migrations/009_platform_document_generator.sql`) — document generator
  storage/log layer, per `docs/SHARED_CONVENTIONS.md` convention #2: one
  shared primitive across all projects, living in `platform.*`, not built
  inside any one project's schema. Originally built in `elektrica` (a
  wrong call, corrected once the actual house convention was read — see
  `docs/OVERNIGHT_DECISIONS.md`). Append-only generation log with
  output-hash enforcement; `platform.documents_never_sent` view
  implements the handoff's literal "generated but never sent" visibility
  requirement. `elektrica_app` is the only real caller today; `vls_app`
  gets granted access when VLS has its own first real caller, not before.
- **`elektrica.demand` + `elektrica.comparable_set`** (`migrations/006_elektrica_demand.sql`)
  — the demand object (handoff §2.3) and its frozen market-comparable
  snapshot (§2.8). `demand_type` and the `prior_demand_id`
  shortfall-pre-fill chain are handoff-literal; `demand.status`'s value
  list and `carrier_name`/`adjuster_name` are placeholder (no
  insurance_carrier/adjuster tables yet). `comparable_set` is immutable
  from creation. `aging_demands` view implements the "45 days with no
  offer" aging signal. Staging-only.
- **JP litigation wiring** (`migrations/007_elektrica_jp_litigation.sql`)
  — `elektrica.rental.vls_case_id` (FK to `vls.case`) + a new
  `in_litigation` state, per Jed's decision to reuse
  `vls.valid_next_states()` directly rather than fork it (resolves
  ADR-001 v2 §7 item 5). Zero new JP transition logic in the elektrica
  schema — Elektrica's litigation is driven entirely through `vls.case`/
  `vls.case_event`. Verified the real VLS JP discovery trap fires
  correctly on a case created from Elektrica's own schema. Still
  staging-only (inherited from `elektrica.rental`), but this piece itself
  has no placeholder fields.
- **`elektrica.payment` + `elektrica.toll` + `elektrica.compliance_item`**
  (`migrations/008_elektrica_payment_toll_compliance.sql`) — payment/toll
  are handoff-literal (§1.6/§2.3), append-only; compliance_item is the
  bot's original v1 scope (dealer license, renewal reminders) retained
  per ADR-001 v2 §3. `compliance_items_expiring_soon` and
  `vehicle_revenue_summary` views implement the original plan's reminder
  and lightweight-financials requirements as queries. No placeholder
  fields of its own. Staging-only.
- **`platform.communication`** (`migrations/010_platform_communication.sql`)
  — the shared communication timeline (handoff §1.5/§2.6, shared-conventions
  #4): polymorphic attachment to a domain record (same pattern as
  `platform.document`), propose-then-confirm `match_status` for inbound
  carrier email matched by claim number (never auto-filed). Built directly
  in `platform.*` from day one (learned from migration 005/009's
  relocation) since the shared-conventions doc already names both
  Elektrica and Complete Collision as callers. No placeholder fields.
  Staging-only, awaiting Jed's review (new schema, not a drift correction).

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

- `insurer_payment` + `adjuster`, historical import (export-blocked)
- Backend/API server, frontend (deliberately last, per ADR-001)
