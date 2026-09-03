# Elektrica Dashboard — Build Log

Running log of decisions and file changes, for Jed's review without needing
to re-read full agent transcripts.

## 2026-09-03 — ADR-001 v2 read, build not yet started

- Read `docs/ADR-001-elektrica-rentals-v2.md` (approved) and
  `docs/ELEKTRICA_HANDOFF_2026-09-03.md` in full. Adopting v2 as the
  canonical scope document going forward; my own `docs/original-bot-*.md`
  stays as historical record only.
- Verified current repo state: `migrations/` and `scripts/` are empty — no
  schema or app code exists yet.
- Verified export status: checked `~/Downloads/elektrica_exports/` (Kay's
  `CLAUDE_TO_KAY_006` deliverables). Only
  `DATABASE_MAP_elektrica_SKELETON.md` and `INTEGRATION_INVENTORY.md` exist,
  both explicitly self-marked as PARTIAL/SKELETON, built from static Python
  code analysis, not from actual Sheets access (Elektrica Google OAuth still
  not restored on Kay's host). **No CSV exports of Fleet, the insurance
  carrier database, or insurer-payment history exist yet.**
- Per ADR-001 v2 §6 build order, step 1 ("export & inspect real Sheets")
  blocks step 3+ (writing real `elektrica.vehicle` / `insurance_carrier` /
  `insurer_payment` migration SQL). Holding schema work rather than guessing
  column names, per the ADR's own explicit instruction (§5: "validate field
  names against the real Sheets/Fleet-tab export before finalizing migration
  SQL").
- Flagged a standing-boundary question to Jed directly (not assumed):
  reading VLS migration 002/004 in the VLS repo for the JP-state-machine and
  RLS patterns, as instructed in the ADR/handoff. My profile's hard rule is
  to ask before touching anything VLS-related, even generic schema/trigger
  code with no client data in it, so that's pending his explicit answer.
- No app code, migrations, verify scripts, or deployments created.

**Next up once unblocked:** `elektrica.vehicle`, `elektrica.renter`,
`elektrica.rental` core tables on a Neon staging branch, each with a
companion `verify_NNN.sql`, per the same discipline as the VLS build.

## 2026-09-03 (later) — Unblocked by Jed via hermes; first real migrations shipped

Jed's answers relayed by hermes:
1. Cleared to read VLS migrations directly — the VLS boundary is about case
   DATA, not schema/SQL with zero client data. Read
   `vls-dashboard/migrations/002_vls_court_rules.sql` (case type enums,
   `fee_shifting_eligible` compute trigger, `valid_next_states()` JP/District
   state machine incl. the JP discovery trap, append-only `case_event`
   enforcement) and `004_platform_rls.sql` (`platform.person`,
   `platform.person_merge`, `vls.client` party-table pattern, RLS with
   `FORCE ROW LEVEL SECURITY`, per-app Postgres role + SELECT-only policy
   keyed off the app's own party table).
2. Real Fleet/carrier/insurer-payment exports still not available (Elektrica
   OAuth restoration pending, no ETA) — proceed anyway using ADR §5's
   column names/shapes as working schema, staging-only, explicitly commented
   confirmed-vs-placeholder per field, do not promote placeholder fields to
   production.
3. The three open §7 items (UIM trigger, Authorize.net scope, self-pay
   payer) don't block vehicle/rental/renter/case_event core work — proceed,
   revisit at the payment tables.

Work done, following the VLS deploy-safety discipline (staging apply ->
verify by direct query -> reset staging -> promote -> tag):

- `migrations/001_elektrica_renter.sql` — `elektrica` schema,
  `elektrica.renter` (party table keyed to `platform.person`, identical
  pattern to `vls.client`), `elektrica_app` Postgres role, RLS SELECT policy
  on `platform.person` scoped to rows with a matching `elektrica.renter` row.
  No placeholder fields. Applied to staging, verified with
  `scripts/verify_001.sql` (6 checks: person visibility both directions,
  `elektrica_app` blocked from direct `platform.person` INSERT,
  `platform_identity_service` sees everyone, `elektrica_app` can read/write
  its own schema, one-row-per-person constraint) — all passed. Staging
  reset to a clean mirror of production. **Promoted to production** and
  confirmed live (0 rows, schema present, table structure correct).
- `migrations/002_elektrica_vehicle.sql` — `elektrica.vehicle` with `class`,
  `status`, `tracking_system`, bot-maintained `current_position` JSONB.
  Every enum's value set is explicitly commented PLACEHOLDER pending the
  real Fleet export, with a DO-NOT-PROMOTE banner at the top of the file.
  `vehicle.class` and `vehicle.tracking_system` columns themselves are
  marked CONFIRMED REAL (Jed) — only their enum value lists are guesses.
  Applied to staging, verified with `scripts/verify_002.sql` (vin
  uniqueness, `elektrica_app` grants, default status) — all passed.
  **Staging-only, not promoted.** Left applied on staging for continued dev
  work on `rental` next.
- Confirmed final state: production `elektrica` schema has `renter` only;
  staging has `renter` + `vehicle`. Verified by direct `\dt elektrica.*` on
  both branches, not by trusting migration exit codes.
- Commit tagged `elektrica-migration-001` on promotion.

**Next up:** `elektrica.rental` (the spine — vehicle/renter/assignment_document_id
per handoff §2.3), then `rental_proposal` + bot API stub, then wire the JP
court engine as an imported dependency (not a fork) referencing VLS
migration 002's `valid_next_states()` pattern for the JP-only branch Elektrica
uses. Vehicle enum values to be corrected once the real Fleet export lands
(tracked as a blocking follow-up, not forgotten).
