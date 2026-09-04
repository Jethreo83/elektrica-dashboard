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

## 2026-09-03 (overnight) — elektrica.rental spine, staging-only

Context: Jed stepped away for the night; hermes sent a "standing overnight
rules" message twice, both times truncated to just a header + "1...." with
no actual rule content delivered. I flagged this back to hermes as
suspicious rather than acting on unseen "expanded permissions," and
continued strictly within my pre-existing approved lane (staging-branch
schema work, verification, docs) — no change to standing boundaries
(draft-and-hold external-facing, no unreviewed production promotion, VLS
case-data boundary) based on a message I never actually received the body
of.

Work done, staging-only:

- `migrations/003_elektrica_rental.sql` — `elektrica.rental` (the spine,
  handoff §2.3: vehicle, renter, body_shop, rental_type, billed_to,
  start/end dates, `assignment_document_ref`, Drive/JotForm refs) plus
  `elektrica.rental_event`, an append-only event log identical in mechanism
  to `vls.case_event`/`vls.case` (current_state derived from latest event,
  direct writes blocked by trigger, sequence enforced by
  `elektrica.rental_valid_next_states()`).
- State machine covers ONLY Elektrica's own portion of handoff §2.4's flow:
  `active -> finished -> needs_demand -> (needs_more_information <->) ->
  demand_sent -> negotiating -> no_offer -> needs_lawsuit -> needs_served`.
  Renamed the matter-terminal state to `resolved` per the handoff's own
  note that "finished (rental)" and "finished (matter)" must not collide.
- **Deliberately did NOT wire the JP litigation state machine** (answered ->
  motion_limited_discovery_filed -> discovery_open ->
  settled/dismissed/judgment) onto `needs_served`. That extraction-mechanics
  question is explicit ADR-001 v2 §7 item 5, still unresolved — not
  something to decide unilaterally overnight. Left `needs_served` with a
  TODO comment and only a temporary manual `resolved` escape hatch, plus a
  `blocked_rentals` view entry flagging every rental sitting in
  `needs_served` as blocked on that unresolved wiring (visible, not hidden).
- `body_shop` / `rental_type` columns are free TEXT, explicitly commented
  placeholder-shape pending the real Rental Management sheet export — no
  enum guessed without real column values.
- Applied to staging, verified with `scripts/verify_003.sql` (7 checks:
  default state, valid transition advances state via trigger, invalid
  transition rejected, direct state UPDATE blocked, append-only DELETE
  blocked, full walk of the elektrica-owned lifecycle to `needs_served`,
  `blocked_rentals` view surfaces the JP-handoff gap) — all passed.
- **Not promoted to production** — placeholder column shapes plus an
  explicitly unresolved architecture question are exactly what "hold
  promotion" means in this build's discipline. Staying staging-only until
  Jed is back to close both the export gap and the JP-wiring decision.

**Next up:** `rental_proposal` (bot API contract stub, handoff §1.7) —
proposal-shaped only, no legal-record field ever auto-written. Then
`demand` + `comparable_set` once the document generator shape is at least
stubbed.

## 2026-09-03/04 (overnight, continued) — full overnight rules received; rental_proposal shipped

hermes resent the overnight rules a third time, complete this time (prior
two were genuinely truncated in transit, not a signal to ignore). Summary:
Jed unreachable until morning; keep building; anything needing his direct
sign-off (money, external sends under his name, deleting data, prod
credentials, touching another business's schema without clearance) gets
queued to `docs/OVERNIGHT_DECISIONS.md` instead of decided solo; genuine
blockers get logged there too and I move to the next build-order item
rather than idling; normal git discipline (commit/tag/push per milestone)
continues.

Created `docs/OVERNIGHT_DECISIONS.md` with two entries: the open JP-engine
wiring question (ADR §7 item 5 — queued, not decided, since it's an
architecture choice touching how Elektrica's schema relates to VLS's) and
the still-unresolved real Sheet exports (external dependency, not a
decision).

Then continued the build order:

- `migrations/004_elektrica_rental_proposal.sql` — bot API contract stub
  per handoff §1.7/§2.3. `rental_proposal` table: kind (departure/return/
  dates/tolls), free-shape JSONB `proposed_values` (deliberately not typed
  per-kind — the bot side doesn't exist yet, locking columns now would be
  guessing), source_system + evidence + observed_at provenance, pending/
  accepted/rejected status with a check constraint tying decided_by/
  decided_at to non-pending status. No placeholder fields — shape comes
  directly from the handoff's literal spec, not a guessed Sheet column.
  Immutable except for the one-time decision (mirrors
  elektrica.rental_event's restrict-update pattern); append-only
  (DELETE blocked). Critically: accepting/rejecting a proposal here does
  **not** touch `elektrica.rental.current_state` — per handoff §1.7 ("never
  auto-applied to a legal-record field"), a human or future app-layer
  action must separately insert the corresponding `rental_event`.
- Note: staging branch lost `vehicle`/`rental` between sessions (shared
  Neon project with VLS work happening in parallel overnight) — had to
  reapply 002/003 before 004 would apply cleanly. No data loss of concern
  (test harness rows only, staging is disposable by design).
- Verified with `scripts/verify_004.sql` — 8 checks, all passed. CHECK 8 is
  the load-bearing one: confirms `elektrica.rental.current_state` stayed
  `active` after a proposal was accepted, proving proposals really are
  inert until a human/app separately acts on them.
- Migration 004 inherits migration 003's staging-only status mechanically
  (FK chain through `elektrica.rental` -> `elektrica.vehicle`'s placeholder
  enums), not because of anything wrong with its own shape — noted in the
  migration file itself.

**Next up:** `document` + shared document generator stub (handoff §1.3),
scoped first to rental demand letters per ADR-001 v2 section 4's
instruction to build it now. Then `demand`/`comparable_set`. JP-engine
wiring and the vehicle enum corrections remain queued in
`docs/OVERNIGHT_DECISIONS.md` for Jed.

## 2026-09-04 (overnight, continued) — document generator storage/log, staging-only

- `migrations/005_elektrica_document.sql` — `document_template` (versioned,
  family enum scoped to Rentals-only callers: rental_demand,
  rental_agreement, return_agreement, dv_request_letter — Consulting/Sales
  template families explicitly excluded, out of scope per ADR §3),
  `document` (append-only generation log: template_id, source_table +
  source_id, frozen `merge_data`, ordered `attachments`, `output_ref` +
  `output_hash`), `outbound_log` (separate send-tracking step, append-only),
  and a `documents_never_sent` view implementing the handoff's literal
  phrase "generated but never sent" as a query. No placeholder fields —
  every column is a literal requirement from handoff §1.3's own spec.
- **Scope decision, logged not guessed:** built this inside the `elektrica`
  schema, not `platform.*`, even though handoff §1.3 frames the document
  generator as a shared platform primitive. Reasoning: VLS hasn't built one
  yet (confirmed in the handoff itself — "neither VLS nor you have built
  one yet"), so ADR-001's own extraction rule ("extract only when a second
  consumer exists") isn't satisfied. Deciding to physically place shared
  infra in `platform.*` ahead of a second real consumer is a
  cross-business architecture call — logged as a queued item in
  `docs/OVERNIGHT_DECISIONS.md` rather than defaulted into overnight. The
  schema is written extraction-ready (template_id/version, merge_data,
  attachments, output_hash — the exact contract handoff §1.3 specifies) so
  moving it to `platform.*` later is a rename + grant change, not a
  redesign.
- Staging churned again overnight (lost all elektrica tables except
  `renter` between migration 004 and 005 work — some other process is
  resetting the shared staging branch, not just VLS's own migrations).
  Reapplied 002/003/004 before 005 would apply cleanly each time. Flagging
  this as an operational friction point, not a blocker: staging is meant to
  be disposable, but frequent resets mid-session cost real time re-running
  known-good migrations. Worth raising with hermes whether VLS and
  Elektrica should get separate staging branches within the same Neon
  project, to stop stepping on each other's overnight work.
- Verified with `scripts/verify_005.sql` — 8 checks, all passed
  (template uniqueness, `output_hash` required once `output_ref` is set,
  append-only enforcement on both `document` and `outbound_log`, and the
  `documents_never_sent` view correctly clearing once a send is logged).
- **Not promoted to production** — inherits staging-only status via its FK
  chain to `elektrica.rental` (same mechanical reason as migration 004),
  not because of anything wrong with its own shape.

**Next up:** `demand` + `comparable_set` (handoff §2.3/§2.8) — the actual
rental-demand business object that will become `document`'s first real
caller. Then `insurer_payment` + `adjuster` once (or if) the historical
export lands. JP-engine wiring, vehicle enum corrections, and the
document-generator platform-vs-elektrica placement question all remain
queued in `docs/OVERNIGHT_DECISIONS.md` for Jed.
