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

## 2026-09-04 (overnight, continued) — elektrica.demand + comparable_set, staging-only

- `migrations/006_elektrica_demand.sql` — `elektrica.demand` (rental_id,
  demand_type: primary_insurer/uim/balance_to_renter — literal handoff
  enum; recipient_type + carrier_name/adjuster_name; amount;
  generated_document_id FK making `elektrica.document` a real caller;
  sent_via/sent_at; status; self-referencing `prior_demand_id` implementing
  the handoff's literal "the shortfall from a resolved earlier demand
  pre-fills the next") and `elektrica.comparable_set` (frozen per demand —
  scan_source, scan_timestamp, vehicle_class, date range, JSONB
  comparables array, computed_average; immutable from creation via
  DELETE+UPDATE-blocking triggers, same append-only philosophy as
  `elektrica.document`).
- Provenance split explicitly in the migration's header comment:
  demand_type/recipient/amount/generated_document_id/sent_via/status
  shape and the prior_demand_id chain are handoff-literal (§2.3);
  `demand.status`'s exact value list is PLACEHOLDER (handoff only says
  "each has its own lifecycle," doesn't enumerate states — inferred from
  the rental lifecycle's vocabulary for consistency, flagged as inferred
  not literal); `carrier_name`/`adjuster_name` are PLACEHOLDER free text
  since no `insurance_carrier`/`adjuster` tables exist yet (blocked on the
  same real-Sheet-export dependency already logged in
  `docs/OVERNIGHT_DECISIONS.md`).
- `aging_demands` view implements handoff §2.4's "a demand at 45 days with
  no offer ... Silence is the signal" as a query, same philosophy as
  `vls.blocked_cases`/`elektrica.blocked_rentals`.
- Verified with `scripts/verify_006.sql` — 9 checks, all passed (default
  draft status, carrier_name required for carrier recipients, draft demands
  can't carry a send record, comparable_set values round-trip correctly,
  comparable_set immutable to both UPDATE and DELETE, prior_demand_id
  chaining works, self-reference rejected, aging view correctly empty for
  an unsent demand).
- **Not promoted to production** — inherits staging-only status via FK
  chain to `elektrica.rental`/`elektrica.document`, plus its own
  placeholder `status` enum and carrier/adjuster free-text fields.
- Staging held steady this round (no external reset mid-session) — the 8
  pre-existing elektrica tables were still present before this migration
  applied.

**Next up:** `insurer_payment` + `adjuster` (handoff §2.8) — genuinely
blocked without the real historical payment-data export (same blocker
already logged), so likely the next stopping point for schema work tonight
unless there's a lower-hanging item in the remaining build order
(Compliance / lightweight Financials, the bot's original v1 items, have no
export dependency and could go next instead). Will check both before
picking. JP-engine wiring, vehicle enum corrections, and the
document-generator placement question remain queued in
`docs/OVERNIGHT_DECISIONS.md` for Jed.

## 2026-09-04 (morning) — JP litigation state machine wired per Jed's decision

Jed answered the queued JP-engine question overnight: option (a), shared/
cross-schema reuse of `vls.valid_next_states()` — my own recommendation in
`docs/OVERNIGHT_DECISIONS.md`. Relayed by hermes, also logged in
vls-dashboard's decision file.

- `migrations/007_elektrica_jp_litigation.sql` — added `vls_case_id`
  (nullable FK to `vls.case`) on `elektrica.rental`; added a new
  `in_litigation` rental state between `needs_served` and `resolved`;
  replaced `elektrica.rental_valid_next_states()`'s temporary
  `needs_served -> resolved` escape hatch with `needs_served ->
  in_litigation -> resolved`. Added `elektrica.rental_event_check_litigation()`
  trigger: blocks `in_litigation` without a linked `vls.case`, and blocks
  the litigation-exit `resolved` transition unless the linked `vls.case`
  has reached one of VLS's own terminal states (settled/dismissed/
  judgment) — read directly off `vls.case.current_state`, never
  re-derived. Zero new JP-specific transition logic written in the
  elektrica schema — this is literal reuse, not a fork, exactly per
  handoff §1.2's instruction and Jed's decision.
- Granted `elektrica_app` `USAGE` on schema `vls` and `SELECT, INSERT` on
  `vls.case`/`vls.case_event` (+ sequences) — scoped to what driving
  Elektrica's own litigation through VLS's engine requires. No visibility
  into `vls.client` or VLS-client data granted; `platform.person` RLS
  untouched.
- `elektrica.blocked_rentals` view updated: the old "JP handoff not wired"
  entry is gone (problem solved), replaced with real visibility — a
  rental in `needs_served` with no case linked yet, or `in_litigation`
  while its linked `vls.case` is itself stalled (reusing
  `vls.blocked_cases`' own JP-trap detection rather than re-deriving it).
- Verified with `scripts/verify_007.sql` — 6 checks, all passed. The
  load-bearing one (CHECK 4a) proves real reuse, not a stub: a `vls.case`
  created and driven entirely from Elektrica's schema still has VLS's own
  JP discovery trap fire correctly (a direct `answered -> discovery_open`
  jump is rejected, exactly as it would be for a genuine VLS case) — the
  logic Elektrica is relying on is provably the same logic VLS itself
  runs, not a copy that could silently drift.
- Marked RESOLVED in `docs/OVERNIGHT_DECISIONS.md`, with the full
  before/after and verification summary preserved there for the record.
- **Still staging-only** — inherits `elektrica.rental`'s staging-only
  status mechanically via its placeholder vehicle/rental fields, not
  because of anything new introduced by this migration. This piece has no
  placeholder fields of its own and is promotion-ready once its
  dependencies (the real Fleet/Rental-Management exports) land.
- Two remaining queued items in `docs/OVERNIGHT_DECISIONS.md`: document-
  generator schema placement (`elektrica` vs `platform`) and the still-
  blocked real Sheet exports.

**Next up:** `insurer_payment` + `adjuster` (still export-blocked) or
Compliance/lightweight Financials (no export dependency, could go next
instead).

## 2026-09-04 (morning, continued) — payment, toll, compliance_item, staging-only

Continued the build order with items that have no real-Sheet-export
dependency, while the document-generator placement question sits with
Jed (low urgency) and the Fleet/carrier exports remain blocked.

- `migrations/008_elektrica_payment_toll_compliance.sql`:
  - `elektrica.payment` — handoff §1.6's literal spec (source enum:
    authorize_net/check/insurer_eft/manual; external_transaction_id;
    amount; nullable `accounting_sync_ref` reserved for a future
    QuickBooks sync per E-7). Polymorphic against both `rental_id`
    (required) and `demand_id` (nullable) — a payment can be a self-pay
    rental charge with no demand, or settling a specific demand.
    Append-only (both UPDATE and DELETE blocked) — a correction is a new
    row, never an edit to history, same philosophy as `elektrica.document`.
  - `elektrica.toll` — handoff §2.3's literal spec (TollOptics record id,
    amount, date, confirmed flag). Unique on `tolloptics_record_id`.
    Immutable except the `confirmed` flag, mirroring the confirmed/
    confirmed_by pattern used elsewhere (no separate confirmed_by column
    added — the handoff's literal spec for `toll` doesn't have one, so
    none was invented).
  - `elektrica.compliance_item` — the bot's original v1 scope (dealer
    license, renewal reminders), retained per ADR-001 v2 §3. Field shape
    taken from `docs/original-bot-plan.md` §4, adapted to this schema's
    conventions (a `related_document_id` FK to `elektrica.document`
    instead of a raw path, now that a document table exists;
    `vehicle_id` nullable since dealer_license applies to the business,
    not any one vehicle). `compliance_items_expiring_soon` view
    implements the original plan's literal "renewal reminders" /
    "expiring soon" wording as a 30-day query.
  - `elektrica.vehicle_revenue_summary` view — the original plan's
    "basic revenue/utilization view (vehicles earning vs. idle)," as a
    query joining vehicle status against confirmed payment totals.
- Verified with `scripts/verify_008.sql` — 7 checks, all passed
  (payment/toll creation, authorize_net external-id requirement,
  payment append-only on both UPDATE and DELETE, toll uniqueness, toll's
  confirmed-only-mutable rule, compliance expiring-soon window correctly
  excluding a far-out item, revenue summary reflecting the real payment).
- **Not promoted to production** — inherits staging-only status via its
  FK chain to `elektrica.rental`/`elektrica.vehicle`/`elektrica.demand`/
  `elektrica.document`, same mechanical reason as every migration since
  002. No placeholder fields of its own — every column here is either a
  handoff-literal spec (payment, toll) or taken directly from the bot's
  own already-approved original plan (compliance_item).

**Next up:** genuinely export-blocked from here — `insurer_payment` +
`adjuster` need the real historical payment data, and any further Fleet/
carrier-dependent corrections need the real Sheet exports. Both queued in
`docs/OVERNIGHT_DECISIONS.md`. Reasonable stopping point for schema work
until either the exports land or Jed has something else in mind.

## 2026-09-04 (later) — document generator relocated to platform.* (correcting real drift)

hermes pointed me at `docs/SHARED_CONVENTIONS.md` in vls-dashboard (from
Jed's `INSTRUCTION_Jocasta_parallel_build_2026-09-03.md`) — a real
cross-project convention document I had not read. Convention #2 settles
the document-generator placement question I'd left queued: one shared
primitive, and explicitly *"don't build it inside one project's schema
'for now' and plan to move it later"* — which is exactly what migration
005 did, with its own header comment reasoning through that tradeoff and
picking the wrong side. This is a correction of drift I introduced, not
merely an open question Jed needed to resolve from scratch.

- `migrations/009_platform_document_generator.sql` — relocated
  `document_template`, `document`, `outbound_log` (+ enums) from
  `elektrica` to `platform` via `ALTER ... SET SCHEMA`. No data movement;
  every existing FK (`elektrica.demand.generated_document_id`, etc.)
  keeps resolving correctly since the underlying objects retain their
  OIDs across a schema move. `documents_never_sent` view recreated under
  `platform` (views don't auto-follow). `elektrica_app` grants re-issued
  against the new location; deliberately did not pre-grant `vls_app` —
  grants get added when VLS has an actual document-generator caller, same
  discipline already used for `elektrica_app`'s `vls.case` grants in
  migration 007.
- Verified with `scripts/verify_009.sql` — 5 checks, all passed: tables
  confirmed moved; the full FK chain
  (`demand -> document -> document_template`) resolves correctly
  end-to-end after the move; the relocated view works; `elektrica_app`
  can still read/write; the append-only DELETE-blocking trigger survived
  the move intact (triggers attach to the table object, not the schema).
- Marked RESOLVED in `docs/OVERNIGHT_DECISIONS.md`, framed explicitly as a
  correction rather than a fresh decision.
- **Lesson logged for future sessions:** read
  `docs/SHARED_CONVENTIONS.md` proactively before building anything that
  touches `platform.*` or might become cross-project shared
  infrastructure, rather than reasoning it out solo and waiting to be
  told there's a real convention doc.
- Still staging-only overall — this migration itself has no placeholder
  fields and would be independently promotion-ready, but the tables it
  operates on (`elektrica.demand`, `elektrica.rental`, etc.) remain
  staging-only for their own separate reasons.

Schema work is now at a genuine stopping point again: `insurer_payment`/
`adjuster` and any Fleet/carrier corrections remain export-blocked.

## 2026-09-04 (later still) — elektrica.staff_user for the shell launcher

hermes relayed a non-urgent note from shell-dashboard's ADR: the new
shell bot's launcher gates each business's "door" on that business having
its own staff/role table, and Elektrica has none yet (unlike VLS's
`vls.staff_user`, migration 005, and Collision's `collision.staff_user`,
migration 004) — not a blocker for anything in progress, just flagged so
it isn't a surprise later. Asked to match the same shape when I get to
it: `id, google_email, role enum, active flag`.

- `migrations/011_elektrica_staff_user.sql` — `elektrica.staff_user`,
  modeled directly on `vls.staff_user` (read directly, per Jed's standing
  clearance to read VLS schema/SQL) and `collision.staff_user` (same
  repo family): `person_id` FK to `platform.person`, `role` enum,
  `google_email` (unique, domain-restricted), `active` flag,
  `provisioned_by_staff_user_id` self-reference for admin-provisioned
  staff (no self-signup), full audit columns.
- **Field provenance, explicit:** the table SHAPE is confirmed-safe by
  direct precedent (two existing, working implementations to copy from).
  The `elektricarentals.com` email domain is sourced from a real filename
  in `~/Downloads` (a certificate PDF named with `jed@elektricarentals.com`)
  — real evidence, not invented, but weaker than VLS's domain source, so
  flagged as such rather than presented with unearned confidence. The
  **role enum values are placeholder** (`owner`, `staff` — a minimal set
  covering "Jed only" as a single `owner` row, since no source document
  ever answered the original bot's own open question #5, "will other
  staff need dashboard access?"). Elektrica_app's grant deliberately
  mirrors VLS's tighter SELECT-only pattern (not Collision's broader
  grant, which reflected an undecided provisioning boundary at the time
  Collision built it) — nothing here suggests Elektrica needs the looser
  version.
- Verified with `scripts/verify_010.sql` — 6 checks, all passed: row
  creation, domain-restriction CHECK, one-row-per-person uniqueness, the
  provisioning self-reference chain, `elektrica_app`'s SELECT-only access
  (INSERT correctly rejected), and the `updated_at` trigger firing on
  UPDATE.
- **Not promoted to production** — the role enum is placeholder, same
  discipline as every other placeholder field in this schema. Adding an
  explicit open item to `docs/OVERNIGHT_DECISIONS.md` for Jed: does
  Elektrica need more than two roles (owner/staff), or is that minimal
  set actually correct? Low urgency — doesn't block anything else, but
  needed before promoting.

## 2026-09-04 (later) — staff role set confirmed final, migration 011 promoted

Jed confirmed directly (relayed by hermes): `owner`/`staff` is the final
role set for `elektrica.staff_user`, no further granularity planned.
Unlike the document-generator placement question, the placeholder guess
turned out correct — no fix needed, just Jed's sign-off to drop the
"placeholder" framing and promote.

- Updated `migrations/011_elektrica_staff_user.sql`'s own header comment
  from "ROLE ENUM VALUES: PLACEHOLDER" to "ROLE ENUM VALUES: CONFIRMED
  FINAL by Jed," recording the resolution inline in the migration itself,
  not just in the decisions log.
- Re-verified per the standing discipline before promoting, not just
  reused the earlier staging run: reset staging to exactly mirror
  production's current state (migration 001 only), confirmed migration
  011 applies standalone (it references only `platform.person`, no
  dependency on migrations 002-010 — the earlier full-chain apply was
  for interaction testing against `platform.communication`, not a real
  dependency), reran `scripts/verify_011.sql` against that
  production-mirrored state — 6/6 checks passed again.
- Reset staging clean, then **promoted migration 011 to production**.
  Confirmed live by direct query: correct 10-column structure, all 15
  named constraints present (unique/FK/check/not-null), 0 rows (clean,
  no verification test data leaked in).
- Marked RESOLVED in `docs/OVERNIGHT_DECISIONS.md`.
- Tagged `elektrica-migration-011-production`, pushed.

Production `elektrica` schema now has both `renter` (migration 001) and
`staff_user` (migration 011) live — the two migrations with no
placeholder fields once Jed's confirmations came in. Everything else
(002-010) remains staging-only pending real exports or further review.

## 2026-09-04 (later still) — staff provisioning must link platform.person (backlogged)

Jed's second decision on staff_user (relayed by hermes): staff
provisioning should create/link a `platform.person` row the same way
renter/client provisioning already does — convention #1 consistency,
same decision relayed to VLS and Collision as a house-wide pattern.

No schema change needed: `elektrica.staff_user.person_id` is already
`NOT NULL REFERENCES platform.person (id)` (migration 011) — the
constraint already requires it. What doesn't exist yet is the actual
provisioning *workflow* (no backend/API exists at all, data layer first
per standing discipline), so there's no code path today for this
decision to change anything in. Logged to a new `docs/BACKLOG.md` (items
decided but not yet actionable, to check when the relevant work starts)
rather than treating it as an open question needing more from Jed, or
silently forgetting it until staff-provisioning code is actually
written. When that day comes: match-before-create through
`platform_identity_service`, same as renter/client provisioning, no
shortcut.

## 2026-09-04 (morning, brief note) — accidental push resolved, SQLite track archived

Jed's calls, relayed by hermes: (1) the `elektrica.*` Postgres v2 schema is
the real, approved architecture — confirmed, already built all night; (2)
on the accidental push of the unreviewed `4a46d40` SQLite-app commit: no
real damage (no VLS data, no Neon connection from that app, no
deployment), don't spend more time on it beyond this note, do not
force-push/rewrite history (already hadn't); (3) archive the SQLite track
rather than delete it.

Archived to `docs/superseded/phase1-sqlite-app/` (git mv, tracked as
renames, own README explaining why kept — two real bugs were fixed there
with regression tests, worth preserving as a record even though the track
itself is dead). Root README's "two tracks" warning replaced with a short
resolved note. `.gitignore` retargeted at the new path. Committed and
pushed (`7fe3949`). Full incident detail already lives in
`docs/OVERNIGHT_DECISIONS.md`, not duplicated here.

Continuing with the document-generator placement question next.

## 2026-09-04 (later, daily cron cycle) — platform.communication (shared timeline), staging-only

Ran the standing daily build/status cycle. Pulled origin/main first (per
memory: check for new commits from unattended sessions before writing
anything) and picked up migration 009 (document generator relocated to
`platform.*`) that had landed since the last cycle — reviewed it, confirmed
via direct staging query that `platform.document`/`document_template`/
`outbound_log` exist with the right columns and `elektrica.demand`'s FK
chain still resolves. No conflicting work in flight.

Re-checked the real Fleet/carrier/insurer-payment Sheet export blocker:
still unresolved — `~/Downloads/elektrica_exports/` has only the two
skeleton docs from static analysis (`DATABASE_MAP_elektrica_SKELETON.md`,
`INTEGRATION_INVENTORY.md`), no real CSVs, no Google OAuth restoration
noted. `insurer_payment`/`adjuster` and any Fleet-derived corrections
remain genuinely blocked, per the existing entry in
`docs/OVERNIGHT_DECISIONS.md`.

Picked the next unblocked item from the handoff's own build order (§6):
"... -> outbound log -> comms -> payments -> insurer_payment ..." — the
communication timeline (handoff §1.5/§2.6, `SHARED_CONVENTIONS_NOTE.md`
convention #4) was skipped over when migration 008 went straight to
payment/toll/compliance_item. It has no export dependency, so built it now
to fill that build-order gap.

- `migrations/010_platform_communication.sql` — `platform.communication`:
  polymorphic `(source_table, source_id)` attachment (same pattern as
  `platform.document`), `direction` (inbound/outbound), `channel`
  (call/email/sms), provenance (`source_system`), and a propose-then-
  confirm `match_status` (confirmed/proposed/rejected) modeled directly on
  `elektrica.rental_proposal`'s already-established immutability shape.
  Handoff-literal: RingCentral/outbound-app comms attach automatically and
  are confirmed by construction; inbound carrier email matched by claim
  number attaches as a `proposed` row pending human confirmation, never
  auto-filed ("wrong-claim attachment is worse than no attachment").
  Placement is `platform.*` from the start, NOT staged in `elektrica`
  first — applying this morning's migration-009 lesson directly instead of
  repeating the mistake: the shared-conventions doc already names both
  Elektrica and Complete Collision as callers, so there's no "wait for a
  second consumer" ambiguity this time. `collision_app` deliberately not
  pre-granted (added when Collision has a real caller, same discipline as
  migration 009's `vls_app` deferral).
- Verified with `scripts/verify_010.sql` — 8 checks, all passed on
  staging (rolled back, no data persisted): outbound app-authored comm
  inserted pre-confirmed; inbound proposed comm surfaces in
  `pending_communication_matches`; match-fields-together constraint
  enforced; confirming a proposed match succeeds; re-deciding a settled
  match is blocked; substantive fields (subject etc.) are immutable even
  pre-decision; DELETE is blocked (append-only); rejecting a proposed
  match (not just confirming) is a valid decision path.
- **Not promoted to production** — new table, no dependents yet, but
  holding to the same discipline as every other post-001 migration: stays
  staging-only until Jed reviews it (this is genuinely new schema, not a
  correction, so it gets a normal review pass rather than the "just fix
  it" treatment migration 009 got).
- Committed and pushed (see git log for hash) with a companion
  `scripts/verify_010.sql`. Tag deferred to Jed per standing promotion
  discipline — this session did not self-tag `elektrica-migration-010`.

**Next up:** `insurer_payment` + `adjuster` remain export-blocked. No
other unblocked schema item identified in the handoff's build order beyond
what's now built (rental spine through comms). Backend/API server and
frontend are deliberately last per ADR-001 v2 — still nothing built there
by design, data layer first.

## 2026-09-04 (later, daily cron cycle) — first app-layer code: app/models.py, app/repository.py, app/api.py, real live verification

Pulled origin/main first (no new commits since migration 011's promotion
and the staff-provisioning backlog entry — no conflicting concurrent
work). Re-verified staging state by direct query rather than trusting
memory: staging only had `renter` + `staff_user` (migrations 002-010 had
been lost between sessions again, same shared-staging-branch churn
flagged in prior entries). Reapplied migrations 002 through 010 in order
before starting app-layer work — staging now carries the full chain
(`renter`, `vehicle`, `rental`, `rental_event`, `rental_proposal`,
`comparable_set`, `demand`, `payment`, `toll`, `compliance_item`,
`staff_user` in `elektrica`; `person`, `person_merge`, `communication`,
`document`, `document_template`, `outbound_log` in `platform`).

Per ADR-001 v2's build-order discipline (schema first, backend once the
schema is verified, frontend last), this is the first backend code in
this repo — Complete Collision's `app/` (same repo family, same Neon
project, same conventions author) served as the direct pattern to copy,
not reinvent: dataclass models mirroring SQL 1:1, a thin repository
layer with all SQL parametrized, a FastAPI wrapper with no auth yet
(same explicit "not yet built" flag Collision's api.py carries), and a
mocked test_api.py + pure-logic test_models.py pair.

- `app/db.py` — connection helper, identical shape to Collision's:
  connection string read from a named env var only, never hardcoded;
  same role/grant-gap warning (`elektrica_app` has no INSERT on
  `platform.person`, by design, migration 001) documented in the module
  docstring rather than silently worked around.
- `app/models.py` — dataclasses for every elektrica/platform entity this
  repo has migrated so far (Renter, Vehicle, Rental, RentalEvent,
  RentalProposal, Toll, Demand, ComparableSet, Payment, ComplianceItem,
  StaffUser) plus every enum, matching Postgres enum labels exactly.
  `__post_init__` mirrors each table's real CHECK constraints (caught
  one real bug doing this — see below). `RENTAL_VALID_NEXT_STATES` +
  `validate_rental_transition()` is a **documentation/fast-fail mirror**
  of `elektrica.rental_valid_next_states()` (migrations 003+007) as a
  graph (Elektrica's machine branches/loops, unlike Collision's
  strictly-forward `JOB_STATUS_SEQUENCE` list) — the DB trigger chain
  remains the actual source of truth; this only saves a round trip on
  an obviously-illegal jump and can never be more permissive than the
  DB (it deliberately does NOT attempt the vls.case cross-schema
  litigation gate, migration 007's `rental_event_check_litigation` —
  that needs a real DB read this layer doesn't duplicate on purpose).
  Vehicle enum values inherit migration 002's PLACEHOLDER caveat
  verbatim, flagged in the module docstring, not silently presented as
  settled.
- `app/repository.py` — one function per real operation across every
  migrated table. The one genuinely different discipline from
  Collision's flat status field: `elektrica.rental.current_state` is
  NEVER written directly from this layer — `advance_rental_state()` is
  the only path, and it inserts a `rental_event` row and lets the DB
  trigger derive the cached `current_state`, matching the DB's own
  enforcement (a direct `UPDATE` to `current_state` is blocked by
  trigger even under `neondb_owner`, so there's no accidental bypass
  even from a privileged connection). `decide_rental_proposal()` is
  written to explicitly NOT touch `elektrica.rental` — verified live,
  see below — matching handoff §1.7's "never auto-applied to a
  legal-record field."
- `app/api.py` — FastAPI wrapper: Fleet board (`/fleet/out`,
  `/fleet/available`, handoff §2.5), rental CRUD + state transitions,
  the bot proposal contract (`POST /rentals/{id}/proposals`, handoff
  §1.7's literal shape) + a pending-queue + decision endpoint, demand
  creation/send/aging, toll creation/confirmation, payment creation,
  vehicle revenue summary, compliance expiring-soon. No auth layer yet
  — flagged explicitly in the module docstring as the real gap handoff
  §1.7 calls out ("API key or nothing") that must close before any real
  deploy, not silently assumed away. Never started as a running process
  by anything in this repo automatically; run by a human on demand only.

**Two real bugs found and fixed by actually running this against live
staging data, not just mocks:**
1. `RentalEvent.__post_init__`'s mirror of
   `rental_event_confirmed_by_required` had the CHECK's logic
   backwards (mirrored `confirmed = false OR confirmed_by IS NOT NULL`
   as "unconfirmed requires confirmed_by" instead of the correct
   "confirmed requires confirmed_by"). Caught immediately by
   `scripts/_smoke_repository.py`'s first `advance_rental_state()` call
   raising a real `psycopg2.errors.CheckViolation` — the DB was right,
   the Python mirror was wrong. Fixed in `app/models.py` and
   `app/repository.py` (which wasn't passing `confirmed_by` on
   DB-confirmed transitions at all); `test_models.py` had a test
   asserting the wrong-direction behavior too, corrected alongside.
2. `list_pending_rental_proposals()` originally queried
   `elektrica.pending_rental_proposals` (the VIEW from migration 004) —
   that view deliberately projects only 6 columns for a "confirm bot
   proposal" screen (no `status`/`decided_by`/`decided_at`/`created_by`),
   so `_rental_proposal_from_row()` KeyError'd trying to round-trip it
   into a full `RentalProposal`. Fixed by querying the base table with
   the same `WHERE status = 'pending' ORDER BY observed_at` the view
   uses, documented inline so a future session doesn't "fix" it back to
   the view without re-reading why.

**Verification, in increasing order of realism (same discipline as every
migration's verify_NNN.sql, applied to app code for the first time):**
- `python test_models.py` — 20/20 pure-logic tests (no DB), covering
  every `__post_init__` CHECK-constraint mirror and the rental
  transition graph (forward, backward-rejected, skip-rejected, the
  `needs_more_information` rework loop, `resolved` terminality).
- `python test_api.py` — 29/29 HTTP-layer tests against a real FastAPI
  `TestClient`, every repository call mocked (no DB). Caught a real
  **route-ordering bug**: `/rentals/blocked` was registered after
  `/rentals/{rental_id}`, so FastAPI tried to parse `"blocked"` as an
  int path param and returned 422 instead of routing correctly — fixed
  by moving the literal route before the parametrized one (documented
  inline in `app/api.py` so it isn't silently reintroduced).
- `python scripts/_smoke_repository.py ELEKTRICA_STAGING_URL` — full
  real-execution smoke test against the Neon staging branch:
  person/renter creation, vehicle creation + bot position update,
  rental creation, `active -> finished -> needs_demand` via
  `advance_rental_state` (plus a rejected illegal skip straight to
  `resolved`), bot proposal creation + pending-queue read + accept
  decision **with a live assertion that `rental.current_state` did not
  change as a side effect of accepting the proposal** (the handoff
  §1.7 guarantee, checked against a real row, not a mock), demand
  creation + mark-sent, toll creation + confirmation, manual payment
  creation, and a DELETE-rejection probe against the append-only
  `payment` trigger (confirmed the DB rejects it and the `cursor()`
  context manager rolls back cleanly without corrupting the
  already-committed happy path, since the probe runs in its own
  transaction). All checks passed. Left permanent staging residue
  (VIN `SMOKETESTVIN00042`, `created_by` = `smoke_test`/`bot_smoke`) —
  intentional: `elektrica.rental_event` is itself append-only with no
  `ON DELETE CASCADE`, so once a rental has any events it (and
  everything that FKs to it) is permanently un-deletable via normal
  DML, same as every other financial/legal audit table in this schema.
  Printed explicitly in the script's own output for a future session
  or Jed to recognize if a staging reset needs to distinguish this from
  real dev data.
- **Live HTTP verification** — actually ran
  `uvicorn app.api:app --port 8123` (background, localhost-only, killed
  immediately after) against the same staging connection, then hit it
  with real `curl` calls: `GET /health`, `/fleet/available` (returned
  the smoke test's own vehicle), `/rentals/blocked`,
  `/vehicles/revenue-summary` (correctly reflecting the smoke test's
  $450 payment), `POST /rentals` (created rental id=4 against real
  vehicle/renter rows), `POST /rentals/4/transition` to `finished`
  (200), then an illegal skip straight to `resolved` (correctly 400 with
  the DB's real error message), then `POST /rentals/4/proposals`
  (200). This is the first genuinely live, non-mocked, non-scripted
  request/response cycle against this codebase's HTTP surface — never
  exposed beyond localhost, process killed at the end of verification,
  no deploy of any kind occurred.

**Not done / explicitly deferred, not silently skipped:**
- No auth layer on the bot-write proposal endpoint — flagged in
  `app/api.py`'s own module docstring as the real gap before any deploy
  consideration, matching handoff §1.7's explicit "API key or nothing"
  requirement.
- `insurer_payment`/`adjuster` app-layer code not started — still
  schema-blocked on the real historical export (unchanged blocker).
- Frontend: not started, deliberately last per ADR-001 v2.
- Staff-user provisioning workflow (the actual API path, not just the
  schema) — still queued in `docs/BACKLOG.md`, unchanged this cycle;
  `provision_staff_user_for_existing_person()` exists in
  `app/repository.py` (mirroring Collision's function of the same name)
  but has no HTTP route yet, same "exists at the repository layer,
  no route wired" state Collision's own staff provisioning was in when
  it was first built.

---

## 2026-09-04 (continuous cron cycle) — staging reapply verification + staff-provisioning route gap closed

**Starting point:** pulled 1 new commit from a concurrent session
(`f1e5680`, docs-only — confirmed `platform.match_or_create_person()` is
real and BACKLOG.md's staff-provisioning entry was already consistent
with it, no code change needed). Staging Neon branch had drifted back to
only `elektrica.renter`/`staff_user` (the two production-promoted
tables) — same recurring shared-branch churn prior cycles have hit.
Reapplied migrations 002-010 via `neon connection-string staging ...
--psql -- -f migrations/00N_*.sql` under `neondb_owner`; all ten applied
clean with no errors, confirmed via `\dt elektrica.*` / `\dt platform.*`
(11 elektrica tables, 7 platform tables, matching the full documented
chain). No schema changes made — this was drift-repair, not new build.

**Verified the existing app layer still holds after the reapply** (same
verification standard as every prior cycle, now run again from a cold
staging state to prove it isn't accidentally coupled to leftover rows
from an earlier session):
- `python test_models.py` — 20/20 (unchanged).
- `python test_api.py` — 29/29 before this cycle's new tests, 36/36 after
  (see below).
- `python scripts/_smoke_repository.py ELEKTRICA_STAGING_URL` (run under
  `neondb_owner`, since `elektrica_app`'s Neon-managed password isn't
  retrievable via the CLI's `reveal_password` API for a `NOLOGIN` role —
  confirmed by inspection, not assumed; the smoke script doesn't `SET
  ROLE` on its own, so this run exercises the same SQL under a
  differently-privileged connection than a real `elektrica_app` deploy
  would use, a real difference worth noting for whoever wires the actual
  connection string, not a false pass) — full happy path (renter, vehicle,
  rental, all three lifecycle transitions including the
  `advance_rental_state` illegal-skip rejection, bot proposal + accept
  decision with the "does not mutate `rental.current_state`" assertion,
  demand + toll + payment, the append-only payment DELETE-rejection
  probe) — all passed against real staging Postgres, same residue-left
  discipline as prior cycles (`SMOKETESTVIN00042`, ids under
  `smoke_test`/`bot_smoke`).

**Built:** closed the staff-provisioning HTTP-route gap flagged in this
file's own "not done" list above and in `docs/BACKLOG.md` (full detail
there, not duplicated here):
- `app/repository.py`: `set_staff_user_active()` (new function).
- `app/api.py`: `POST /staff`, `GET /staff/{google_email}`,
  `POST /staff/{google_email}/active` — same shape as Complete
  Collision's identical route family, same "no `platform.person`-creating
  route, requires a privileged non-`elektrica_app` connection, no
  auth/session layer yet" caveats stated explicitly in the new code's own
  comments rather than silently assumed.
- `test_api.py`: 6 new mocked cases (provision success, bad role enum,
  wrong-domain rejection surfacing as 400 not 500, get found/not-found,
  deactivate, deactivate-not-found) — 36/36 total.
- **Live-verified against real staging**, not just mocks: ran `uvicorn
  app.api:app` under a `neondb_owner` connection (the privileged
  connection these routes require per their own documented role gap),
  inserted a real `platform.person` row, then via real `curl` calls:
  `POST /staff` (200, provisioned `smoke.staff@elektricarentals.com` as
  `staff`), `GET /staff/{email}` (200, round-tripped correctly),
  `POST /staff/{email}/active` with `active: false` (200, deactivation
  took), `GET /staff/nobody@elektricarentals.com` (404), `POST /staff`
  with `role: "manager"` (400, not a valid Elektrica role), `POST /staff`
  with a `@gmail.com` address (400 — confirmed the domain-CHECK
  `ValueError` from `StaffUser.__post_init__` surfaces as a client error,
  not a 500, matching the discipline every other route in this file
  already follows). Server process confirmed killed afterward via the
  process manager's own kill confirmation (not just the command's exit
  code). No deploy, no external exposure.

**Committed & pushed** to `origin/main`.

**Not done / explicitly deferred, not silently skipped (updated):**
- No auth layer on any route (bot proposals, now also staff
  provisioning) — same standing flag, unchanged.
- `insurer_payment`/`adjuster` app-layer code — still schema-blocked on
  the real historical export (unchanged blocker, no ETA).
- Frontend — not started, deliberately last per ADR-001 v2.
- `elektrica_app`'s actual Neon-managed password was never resolved this
  cycle (the CLI's `reveal_password` API returns an empty string for
  `NOLOGIN` roles, which is expected — `NOLOGIN` roles have no password
  to reveal, they're meant to be reached via `SET ROLE` from a login
  role, not connected to directly). Nobody has actually run this app
  layer end-to-end under a literal `elektrica_app` psycopg2 connection
  string yet (every smoke/live run so far, this cycle and prior ones,
  has used `neondb_owner`) — worth a future cycle explicitly proving the
  `SET ROLE elektrica_app` path works through `app/db.py`, since that's
  the actual production access pattern the schema's own grants assume,
  not just its close cousin.

## 2026-09-04 (continuous cron cycle, resumed after a crashed run) — SET ROLE elektrica_app proven end-to-end; migration 012 sequence-grant fix

**Starting point:** found uncommitted working-tree changes from the
immediately prior cron run, which the delivered summary claims crashed
mid-work (`app/api.py`, `app/db.py`, `test_api.py` modified;
`migrations/012_fix_elektrica_app_sequence_grants.sql`,
`scripts/_smoke_elektrica_app_role.py`, `scripts/verify_012.sql`
untracked). No new commits on `origin/main` since `97ef34d`. Reviewed
every uncommitted change in full before touching anything — this closes
exactly the open item this file's own prior entry flagged (\"nobody has
run the app layer under a literal `SET ROLE elektrica_app`\"), and the
work was sound, just never finished/committed. Continuing it rather than
redoing it.

- Ran `test_models.py` (20/20) and `test_api.py` (38/38, the 2 new
  `InsufficientPrivilege -> 403` cases included) clean before touching
  the database.
- Confirmed via direct staging query that migration 012's sequence
  grants were already live (`has_sequence_privilege('elektrica_app', ...,
  'USAGE'/'SELECT')` both `true` for `toll_id_seq` and
  `compliance_item_id_seq`) — the crashed run had gotten far enough to
  apply the grant before dying. `scripts/verify_012.sql` re-run
  standalone to confirm formally.
- Ran `scripts/_smoke_elektrica_app_role.py` against real staging — hit
  a `UniqueViolation` on the very first attempt: the crashed prior run
  had already left permanent residue at a hardcoded VIN
  (`ROLESMOKEVIN00099`) and toll record id (`TOLL-ROLE-SMOKE-001`), and
  this schema's append-only tables mean that residue can never be
  deleted. **Fixed the script itself** (not a schema bug) to derive a
  per-run-unique VIN/toll-record-id from the current timestamp, so a
  future crash-and-resume doesn't repeat this. Re-ran clean: full happy
  path committed as `elektrica_app` (renter → vehicle → rental through
  every state transition → bot proposal decide → demand → toll →
  payment) plus all 4 negative checks correctly rejected
  (`platform.person` INSERT, `staff_user` INSERT/UPDATE, `payment`
  DELETE) — **first real proof that the schema's actual least-privilege
  grants (migrations 001–012) are sufficient for the full app-layer
  happy path**, not just that the SQL is fine under `neondb_owner`.
- **Live HTTP verification with the role switch actually engaged**
  (the crashed run's own live-verification step, redone): ran `uvicorn`
  with `ELEKTRICA_DB_SET_ROLE=elektrica_app` set, then `curl`'d
  `GET /health` (200), `GET /fleet/available` (200, returned real rows
  including this cycle's own smoke vehicle), and
  `POST /staff` (**403**, the new `InsufficientPrivilege`-handling
  except-clause firing for real over HTTP, not just in a mocked test) —
  confirms the new exception handling in `app/api.py` is reachable in
  practice under the real production access pattern. Server killed
  after (confirmed via process manager, not just exit code).
- **Housekeeping, not new build work:** found and killed an orphaned
  `uvicorn` process (a separate PID, still listening on `:8123`) left
  running from the crashed prior cycle — it should have been killed at
  the end of that session's verification and wasn't. Used a different
  port (`8199`) for this cycle's own live check rather than fighting
  over the stale one.
- Committed everything as one commit (`476d2d1`) and pushed to
  `origin/main`. Did not squash/rewrite the crashed run's uncommitted
  work into a different shape — kept its own framing (the SET ROLE
  support in `app/db.py`/`app/api.py`, migration 012's fix, the new
  smoke script) and added only the VIN-collision fix plus this log
  entry on top.
- **Not promoted to production:** migration 012 is a grant-only fix
  scoped to `toll_id_seq`/`compliance_item_id_seq`, which themselves
  belong to migration 008's tables — still staging-only for the same
  reason migration 008 is (no placeholder fields of its own, inherits
  status via the tables it grants against).

**Open items unchanged:** `insurer_payment`/`adjuster` still
export-blocked (no ETA); frontend not started (deliberately last per
ADR-001 v2); no auth/session layer on any route (standing flag,
unchanged). **Lesson for future cron cycles:** any smoke/seed script
using a hardcoded natural-key value (VIN, external record id, etc.)
against an append-only schema should derive it per-run — a crash mid-run
leaves permanent, undeletable residue that collides with the next
attempt, as happened here.

## 2026-09-04 (continuous cron cycle) — Document generator + communication timeline app-layer code (migrations/005/009/010 finally get a Python side)

**Starting point:** pulled and reviewed the prior 5 commits (staff-provisioning
routes, SET ROLE elektrica_app proof, migration 012). Clean working tree, no
concurrent uncommitted work. Confirmed 58/58 existing tests passing before
touching anything.

**Gap found:** `platform.document_template`/`platform.document`/
`platform.outbound_log` (migrations/005, relocated by 009) and
`platform.communication` (migrations/010) had real, live-verified SQL but
**zero app-layer code** — no dataclasses, no repository functions, no HTTP
routes. Handoff §1.3's shared document generator and §1.5/2.6's comms
timeline existed only as schema. Closed this cycle.

**Built:**
- `app/models.py`: `DocumentTemplate`, `Document`, `OutboundLog`,
  `Communication` dataclasses + their enums, mirroring migrations 005/009/010
  1:1 (same discipline as every other model in this file). `Document`'s
  `__post_init__` mirrors `document_output_hash_required_once_generated`;
  `Communication`'s mirrors `communication_match_fields_together` exactly
  (proposed rows carry no matched_by/matched_at, every other status requires
  both).
- `app/repository.py`: `get_active_document_template`/`create_document_template`,
  `create_document`/`get_document`/`list_documents_never_sent`,
  `create_outbound_log`/`list_outbound_log_for_document`,
  `create_communication`/`list_communications_for_source`/
  `list_pending_communication_matches`/`confirm_communication_match`/
  `reject_communication_match`. Outbound send stays a genuinely separate
  write from document generation (handoff §1.3's own point); communication's
  confirm/reject are the only permitted follow-up UPDATE, matching
  `elektrica.rental_proposal`'s propose-then-confirm shape.
- `app/api.py`: `GET /document-templates/{family}`, `POST /documents`,
  `GET /documents/{id}`, `GET /documents/never-sent`,
  `POST /documents/{id}/outbound`, `GET /documents/{id}/outbound`,
  `POST /communications` (proposed vs. confirmed-by-construction via a
  `proposed: bool` flag), `GET /communications/pending`,
  `GET /communications` (query-param `source_table`/`source_id` — kept off
  a path-segment shape deliberately to avoid a wildcard-route collision
  risk), `POST /communications/{id}/confirm`, `POST /communications/{id}/reject`.
  `/documents/never-sent` registered BEFORE `/documents/{document_id}` —
  same routing-order fix this file's own `/rentals/blocked` note already
  documents (FastAPI matches registration order; "never-sent" would 422 as
  an unparseable id otherwise). Caught this by actually running it, not by
  inspection — see verification below.
- Tests: 7 new `test_models.py` cases (27/27 total), 22 new `test_api.py`
  cases (58/58 total) — including the output_ref/no-hash CHECK mirror and
  the proposed/confirmed `CommunicationMatchStatus` CHECK mirror surfacing
  as 400, not 500.

**Live-verified against real staging Postgres (`neondb_owner`), twice, at
two different levels:**
1. `scripts/_smoke_platform_shared_primitives.py` — direct repository-layer
   run: created a real renter/vehicle/rental, then template -> document ->
   outbound_log (proved `documents_never_sent` correctly includes a doc
   before any send and excludes it after), then an outbound (confirmed-by-
   construction) communication and an inbound proposed-then-confirmed
   communication, including a negative check that re-deciding an
   already-decided communication row is rejected (migrations/010's trigger
   permits exactly one decision). All assertions passed.
2. Real HTTP, via `uvicorn` on `127.0.0.1:8214` against the same staging
   branch, `curl`'d through the full document + communication flow end to
   end — this is what actually caught the `/documents/never-sent`
   route-ordering bug above; a pure unit-test run with mocked repository
   calls would not have. Server killed after (confirmed via process
   manager); orphan-process check afterward showed only TIME_WAIT
   connections, no LISTENING sockets left behind.

**Committed & pushed** to `origin/main`.

**Not done / explicitly deferred, not silently skipped:**
- No template-rendering engine — `create_document()` is the storage/log
  layer only, per migrations/005's own scope note; actually producing a PDF
  from `merge_data` + a template is separate, future work.
- No auth/session layer on any route (standing flag, unchanged across every
  cycle so far).
- `insurer_payment`/`adjuster` still export-blocked (no ETA).
- Frontend not started (deliberately last per ADR-001 v2).

## 2026-09-04 (continuous cron cycle, later) — Test infra fix + migration 007 grant-scope flag raised to Jed

**Starting point:** pulled origin/main — up to date, clean tree, no concurrent
uncommitted work. Ran the full test suite before touching anything, using the
bare `pytest` invocation (not the targeted `pytest test_models.py test_api.py`
every prior cycle's log describes) to sanity-check the whole repo state.

**Bug found and fixed:** bare `pytest` failed to collect at all —
`docs/superseded/phase1-sqlite-app/`'s archived Phase 1 test suite (kept
intentionally for history per `docs/OVERNIGHT_DECISIONS.md`'s "URGENT" entry)
was being picked up alongside this repo's real tests, and its own `app/`
package collided on module name with this repo's real `app/` package
(`ImportError: cannot import name 'ComparableSet' from 'app.models'`
resolving to the wrong file). Every prior cycle's clean test runs were
real but happened to always use the targeted invocation, masking this.
Added `pytest.ini` (`norecursedirs = docs`) — bare `pytest` now correctly
collects and passes 85/85. Committed as `d995cfe`, pushed to `origin/main`.

**Reviewed migration 007 (JP litigation wiring) in detail this cycle and am
flagging its grant scope rather than building past it**, per this bot's own
absolute VLS-boundary rule. Migration 007 is Jed-approved (relayed by hermes,
logged in `docs/OVERNIGHT_DECISIONS.md`) as *architecture* — cross-schema
reuse of `vls.valid_next_states()` instead of forking VLS's JP state machine
— and is staging-only, never promoted to production. What I flagged is
narrower than the architecture decision itself: the migration's actual GRANT
statements give `elektrica_app` `SELECT, INSERT` on **all of** `vls.case`
and `vls.case_event`, with no row-level scoping visible in the migration
limiting that access to Elektrica-linked cases only (i.e. rows where some
Elektrica rental's `vls_case_id` points at them) versus VLS's own client
matters sharing the same tables. I have read clearance on VLS *schema/
migration files* to understand this wiring, but I do not have — and this
task doesn't give me — standing to independently judge whether that grant
scope is safe, since that's a real privilege-boundary call touching VLS
client data, not an Elektrica-internal decision. Logged in my own memory
(shared with Complete Collision bot) for continuity; not resolving further
without Jed's explicit sign-off. This does not block other Elektrica build
work — nothing else in the current build queue depends on resolving this
first, and migration 007 stays staging-only either way until Jed decides.

**Did not otherwise build new app-layer code this cycle** — reviewing/fixing
what was here took priority given the flag above; next cycle should resume
at the ADR-001 v2 §7 build-order queue (insurer_payment/adjuster still
export-blocked; auth/session layer still absent; frontend still not started).

**Open items unchanged:** no auth/session layer on any route; `insurer_payment`/
`adjuster` export-blocked; frontend not started; **NEW — migration 007's
`vls.case`/`vls.case_event` grant scope needs Jed's explicit review before
any production promotion** (see above; not urgent since it's staging-only,
but should not be forgotten before that promotion happens).

## 2026-09-04 (continuous cron cycle, later still) — Uncommitted work finished + Vehicle/Renter HTTP routes closed

**Starting point:** found a dirty working tree at cycle start (uncommitted
edits to `app/api.py` / `test_api.py`) from a prior unattended cron cycle
that ran out before it could commit. Diffed it carefully before touching
anything: it was the OPEN ITEM this same file's own module docstring had
flagged two cycles ago -- a real, complete, correctly-scoped fix (scoped
`X-Api-Key` auth on `POST /rentals/{id}/proposals` per handoff §1.7, fail-
closed via `require_bot_api_key()`, `hmac.compare_digest`). Ran the full
suite first (88/88 passed) to confirm correctness, then committed it
(`75073e5`) and pushed rather than discarding real finished work.

**Built this cycle: Vehicle + Renter HTTP routes** -- the same shape of gap
as the staff-provisioning route closure two cycles ago: `app/repository.py`
already had `create_vehicle`, `get_vehicle`, `get_vehicle_by_vin`,
`update_vehicle_position`, `create_renter_for_existing_person`,
`get_renter`, `get_renter_by_person_id` with zero HTTP surface. Added:

- `POST /vehicles` (VIN uniqueness check -> 409, bad enum values -> 400),
  `GET /vehicles/vin/{vin}`, `GET /vehicles/{vehicle_id}`,
  `POST /vehicles/{vehicle_id}/position` (bot-maintained non-legal field,
  handoff §2.3 -- the future rental-ops bot's future write target, nothing
  calls it automatically today).
- `POST /renters` (match-before-create discipline preserved -- takes an
  already-resolved `person_id`, does NOT do its own identity matching, per
  `docs/BACKLOG.md`), `GET /renters/{renter_id}`,
  `GET /renters/by-person/{person_id}`.
- Unlike the staff-provisioning routes, `elektrica_app` has full
  SELECT/INSERT/UPDATE on `elektrica.vehicle`/`elektrica.renter`
  (migration 001/002) -- no privilege-gap 403 case needed here.
- 20 new `test_api.py` cases (104/104 total under pytest).

**Real bug found and fixed via the direct `python test_api.py` run (not
pytest):** first draft registered `GET /vehicles/revenue-summary` AFTER
`GET /vehicles/{vehicle_id}` -- the same class of route-ordering hazard
`/rentals/blocked` already had a comment warning about, but I didn't apply
the lesson to my own new code the first time. `int`-typed `{vehicle_id}`
still swallowed the literal `revenue-summary` segment; pytest's per-route
mocked calls didn't catch it (they patch the repo function directly and
never exercise real FastAPI routing), but the direct script run's real
`TestClient` HTTP calls did (`test_vehicle_revenue_summary` failed).
Reordered the route registration; both suites now pass (104/104 pytest,
77/77 direct run).

**Live-verified against real staging Postgres, real HTTP (uvicorn on
`127.0.0.1:8247`, `neondb_owner` staging connection):** create vehicle
(id=9, VIN `SMOKE-VIN-0904-cron`) -> duplicate-VIN 409 -> lookup by VIN and
by id -> `revenue-summary` returns 200 (proves the route-ordering fix
against real routing, not just the mock) -> position update -> position
on a nonexistent vehicle id returns 404 not 500. Then renter: linked
`platform.person` id=15 (existing staging row, previously unused) as a new
renter (id=9) -> lookup by id and by person_id -> lookup on an unlinked
person_id returns 404 -> re-POSTing the same person_id returns the
existing renter row (idempotent, per `create_renter_for_existing_person`'s
own docstring) rather than erroring or duplicating. Server killed after;
confirmed via `netstat` that the process actually exited (no LISTENING
socket left).

**Also found and cleaned up, not part of my own work:** a genuinely
orphaned `uvicorn` process was still `LISTENING` on `127.0.0.1:8231` from
an earlier, unrelated cron cycle that never shut it down (its `/health`
returned this repo's real `{"status": "ok"}`, confirming it was this
app, not something else). Killed it (`taskkill /F`) -- leaving a stray
locally-bound server running between unattended cycles is exactly the
kind of silent residue this build's own standing discipline says not to
leave behind.

**git note:** `patch` flagged a "modified by sibling subagent, never read"
warning on `test_api.py` mid-edit this cycle. Investigated before
proceeding: `git diff --stat` after the write showed only my own intended
changes (import list + one 6-line diff), no foreign content -- treating
this as a stale/false-positive tracker artifact from the earlier
uncommitted-work situation at the top of this entry, not an actual
concurrent write collision. Flagging here for the record in case a real
one shows up in a future cycle and this pattern needs to be taken more
seriously.

**Committed & pushed** to `origin/main` (two commits: `75073e5` for the
API-key fix, one more for the vehicle/renter routes).

**Not done / explicitly deferred:** no auth/session layer on any route
(unchanged, standing); `insurer_payment`/`adjuster` still export-blocked,
no ETA (unchanged); frontend not started (unchanged, deliberately last per
ADR-001 v2); migration 007's `vls.case` grant-scope flag for Jed still
open (unchanged, staging-only so not urgent).

**Next up:** same as before -- `insurer_payment`/`adjuster` remain export-
blocked; frontend not started; consider whether a Fleet-board "list all
vehicles" or "list all renters" route is worth adding next (handoff §2.5
only explicitly needs Out/Available, which already existed) before moving
to something else in the build-order queue.

## 2026-09-04 (continuous cron cycle, later still) — Compliance-item + document-template HTTP routes closed; duplicate-template 500 fixed

**Starting point:** clean tree, 3 commits ahead already pushed (Vehicle/
Renter routes cycle). No concurrent-session drift found this cycle (fetched
origin/main first, matched local HEAD).

**Built this cycle:** two more "data layer done, no HTTP route" gaps closed,
same shape as staff-provisioning/vehicle/renter in prior cycles:

- **Compliance items** (bot's original v1 scope, ADR-001 v2 §3,
  migrations/008). `app/repository.py`: added `get_compliance_item()` and
  `update_compliance_item_status()` (create + list-expiring-soon already
  existed with no route). `app/api.py`: `POST /compliance-items` (vehicle_id
  existence check -> 404, bad item_type/status enum -> 400), `GET
  /compliance-items/{id}`, `POST /compliance-items/{id}/status` (drives the
  active -> expiring_soon -> expired -> renewed lifecycle, accepts an
  optional `related_document_id` since the real-world "renewed" transition
  is exactly when a new document exists to link). `elektrica_app` has full
  SELECT/INSERT/UPDATE on `compliance_item` (migration 008) -- no
  privileged-connection caveat here, unlike staff_user.
- **Document templates** (`platform.document_template`, migration 009).
  `app/api.py`: `POST /document-templates` — registers a new template
  version. Deliberately does NOT deactivate any prior active version of the
  same family (no UPDATE grant for `elektrica_app` on this table, no
  product requirement yet for that behavior) — flagged in the route's own
  docstring, not silently worked around.
- 12 new `test_api.py` cases (88/88 direct run, 115/115 pytest).

**Real bug found and fixed via live staging verification (not the mocked
test suite):** `POST /document-templates` on a duplicate `(family,
version)` — which IS unique at the DB level
(`document_template_family_version_unique`) — raised an uncaught
`psycopg2.errors.UniqueViolation` and returned a bare 500. Mocked
`test_api.py` cases never exercise a real constraint, so this only showed
up running the real route against real staging Postgres. Fixed by catching
`UniqueViolation` in the route and returning 409, same discipline as the
vehicle VIN-uniqueness route already in this file. Added a mocked
regression test (`test_create_document_template_duplicate_returns_409`,
`side_effect=psycopg2.errors.UniqueViolation()`) so this doesn't silently
regress even though the mocked suite can't catch the *original* miss on
its own — the lesson from the vehicles/revenue-summary route-ordering bug
two cycles ago (mocked tests miss framework/DB-level behavior; a real
TestClient + real Postgres run is what actually catches it) held again
here, just one layer lower (DB constraint instead of HTTP routing).

**Live-verified against real staging Postgres, real HTTP** (uvicorn on
`127.0.0.1:8263`, `neondb_owner` staging connection, confirmed 11
`elektrica.*` tables present via `neon connection-string staging --psql`
before starting): created compliance_item id=1 (dealer_license, no
vehicle) -> read back by id -> nonexistent vehicle_id 999999 -> 404 ->
bad item_type -> 400 -> status transition to `renewed` -> nonexistent id
-> 404 -> bad status enum -> 400 -> `/compliance/expiring-soon` still
200. Document templates: GET rental_demand found the pre-existing active
v1 (from an earlier cycle's smoke data) -> POST duplicate (rental_demand,
v1) -> 500 (the bug) -> fixed -> restarted server -> re-ran -> 409 (correct)
-> POST (rental_demand, v2) -> 200, new active row. Server killed after
each run; `netstat` confirmed no LISTENING socket left both times. A
scratch file holding the staging connection string
(`.staging_url_tmp.txt`, gitignored-equivalent — never committed) was
deleted immediately after use, same "never let a connection string sit on
disk longer than needed" discipline as every other cycle.

**Not done / explicitly deferred (unchanged):** no auth/session layer on
any route; `insurer_payment`/`adjuster` still export-blocked, no ETA;
frontend not started; migration 007's `vls.case` grant-scope flag for Jed
still open (staging-only, not urgent).

**Next up:** `insurer_payment`/`adjuster` remain the biggest genuinely
export-blocked item. Otherwise the build-order queue's data-layer-to-route
gaps are now largely closed (staff, vehicle, renter, compliance, document
templates all have routes) — worth checking whether any other repository
function still lacks HTTP surface before starting frontend work, which
ADR-001 v2 §6/§9 places last regardless.

## 2026-09-05 (continuous cron cycle) — vls-case linkage + comparable-set HTTP routes closed; real FK-violation 500 fixed

**Starting point:** clean tree, fetched origin/main first (matched local
HEAD at 820966c, no concurrent-session drift). `patch` flagged its usual
"modified by sibling subagent, never read" warning on both app/api.py and
test_api.py mid-edit; `git diff --stat`/`git diff` after each write showed
only my own intended changes both times, same stale/false-positive
tracker pattern noted in a prior cycle's entry -- not a real collision.

**Built this cycle:** closed the last two data-layer-function-with-no-route
gaps in the claim-generation-machine chain (rental -> demand -> JP
litigation), same shape as every prior cycle's HTTP-surface work:

- **`POST /rentals/{rental_id}/vls-case`** (`repo.link_vls_case()`,
  existing since migrations/007, previously unrouted). Sets
  `elektrica.rental.vls_case_id` -- required before a `needs_served` ->
  `in_litigation` transition will pass the DB trigger gate. Deliberately
  a separate route from `transition_rental`, per `link_vls_case()`'s own
  docstring: linking a case and actually entering litigation are two
  different real-world events. Does NOT create the `vls.case` row itself
  -- that stays VLS's own write path; this route only records the
  linkage once VLS (or a human with VLS access) hands back a case id.
  No VLS case data was read or written to build or test this beyond the
  FK constraint's own error message.
- **`POST /demands/{demand_id}/comparable-sets`** (`repo.create_comparable_set()`,
  existing since migrations/006, previously unrouted). Handoff §2.8's
  frozen market-comparable snapshot -- `elektrica.comparable_set` is
  immutable-from-creation by DB trigger, so this is create-only by design,
  no update/delete route exists or ever will. Validates demand existence
  (404) and vehicle_class enum (400) before hitting the DB.
- 8 new `test_api.py` cases (95/95 direct run, 122/122 pytest): success +
  not-found + bad-enum + bad-date-range cases for comparable-sets;
  success + not-found + a mocked FK-violation regression case for
  vls-case linkage.

**Real bug found and fixed via live staging verification (not the mocked
test suite) -- same lesson as the document-templates duplicate-version
500 two cycles ago, now recurring a third time on a different table:**
`POST /rentals/{rental_id}/vls-case` with a `vls_case_id` that doesn't
exist in `vls.case` raised an uncaught `psycopg2.errors.ForeignKeyViolation`
(`rental_vls_case_id_fkey`) and returned a bare 500. Fixed by catching
`ForeignKeyViolation` in the route and returning 400 (client-input error,
not a server fault) -- same discipline as the vehicle-VIN and
document-template uniqueness routes. Added a mocked regression test
(`test_link_vls_case_bad_vls_case_id_returns_400_not_500`,
`side_effect=psycopg2.errors.ForeignKeyViolation()`) so this can't
silently regress, even though the mocked suite still can't catch the
*original* miss on its own -- a real `TestClient` + real Postgres run
remains the only thing that actually catches this class of bug in this
codebase, three-for-three now (route-ordering, unique-constraint,
foreign-key).

**Live-verified against real staging Postgres, real HTTP** (uvicorn,
`neondb_owner` -> `SET ROLE elektrica_app`, ports 8342 then 8351 after
the fix): confirmed 5 existing rentals / 3 existing demands present via a
direct psycopg2 read before starting (no `vls.case` rows queried or
touched, staying inside the VLS hard boundary -- confirmed the FK error's
own message was sufficient to diagnose and fix the bug without needing to
read case data). Rental 6, `vls_case_id=12345` (deliberately nonexistent)
-> 500 (the bug, first server) -> fixed -> restarted server -> re-ran
identical request -> 400, rental row confirmed unchanged
(`vls_case_id` still null, rollback held) -> nonexistent rental id ->
404. Comparable-set: created id=1 on demand 1 (`scan_source=kayak`,
`vehicle_class=sedan`, `computed_average=55.00`) -> read back directly
from Postgres to confirm the JSONB `comparables` column round-tripped
correctly -> nonexistent demand id -> 404 -> bad date range (end before
start) -> 400. Both servers killed after their runs; `netstat` confirmed
no LISTENING socket left either time.

**Staging residue left intentionally** (same append-only-adjacent
reasoning as every other smoke run in this repo): `elektrica.comparable_set`
id=1 (`created_by='cron-smoke'`), rental 6 untouched (the vls-case link
never actually succeeded, by design of the test).

**Not done / explicitly deferred (unchanged):** no auth/session layer on
any route; `insurer_payment`/`adjuster` still export-blocked, no ETA;
frontend not started; migration 007's `vls.case` grant-scope flag for Jed
still open (staging-only, not urgent).

**Next up:** with vls-case linkage and comparable-sets now routed, every
repository function that had HTTP-route coverage as a gap appears closed
-- worth a fresh full pass over `app/repository.py` vs `app/api.py` next
cycle to double check nothing new slipped in, then likely time to start
looking at frontend scaffolding (ADR-001 v2 §6/§9 places it last, but the
backend build-order queue is now thin) or revisit the
`insurer_payment`/`adjuster` export-block question with Jed.

## 2026-09-05 (continuous cron cycle) — platform.insurance_carrier + platform.adjuster (migration 013), staging-only, full app-layer + routes

**Starting point:** clean tree, fetched origin/main first (matched local
HEAD at 371fbe3, no concurrent-session drift). Ran the full pytest suite
first (122/122 passed) before touching anything, per standing practice.

**Re-read the handoff/ADR to find the next real gap, not just repeat the
prior cycle's "route-coverage sweep" pattern:** confirmed via a fresh pass
over `app/repository.py` vs `app/api.py` that every non-private repository
function already has HTTP coverage (prior cycle's own "worth a fresh full
pass" note) -- so this cycle needed a genuinely new schema/app item, not
another routing gap.

**Found and closed a real, previously-unbuilt gap:** `insurer_payment`/
`adjuster` (handoff §2.8, ADR-001 v2 build order step 8) has been flagged
"export-blocked" since 2026-09-03, but re-reading the handoff closely
distinguishes two separate things that had been getting bundled together
under one BLOCKER label:
  1. The historical insurer-payment *rows* (handoff §2.9's import) --
     genuinely still blocked on Kay's Elektrica Google OAuth restoration,
     no ETA, unchanged.
  2. The `insurance_carrier`/`adjuster` *schema* itself (handoff §1.4/§2.8)
     -- NOT blocked by that export. Jed already confirmed (ADR-001 v2
     §2) that "a real insurance contact list exists (fax, phone, address,
     email)" as seed data for exactly this table, and the handoff gives
     the carrier/adjuster field list verbatim, independent of any Sheet.
     Only the historical *backfill* of `insurer_payment` needs the export;
     the carrier/adjuster *shape* does not.

Built item (2), staying honest that item (1) remains genuinely blocked:

- **`migrations/013_platform_insurance_carrier.sql`** (staging-only, new
  migration): `platform.insurance_carrier` (name UNIQUE + `aliases TEXT[]`
  -- the literal "collapse to canonical record" mechanism handoff §2.9.2
  describes for the eventual historical import) and `platform.adjuster`
  (carrier_id FK, name UNIQUE per carrier -- same adjuster name can recur
  at a DIFFERENT carrier, people move employers). Placed in `platform.*`
  from day one (not `elektrica.*` "for now") per SHARED_CONVENTIONS
  convention #2 and handoff §1.4's explicit "Shared between VLS and
  Elektrica Rentals" -- migrations 009/010 already paid for this lesson
  once each; not repeating it a third time. `elektrica_app` gets
  SELECT/INSERT/UPDATE, deliberately no DELETE (carrier/adjuster records
  get corrected, never removed) -- `vls_app` is NOT granted (no real VLS
  caller yet, same "grant when needed" discipline as every other
  cross-schema grant in this repo).
- **`scripts/verify_013.sql`**: 7 checks -- insert + aliases round-trip,
  duplicate canonical name rejected, bad adjuster carrier_id FK rejected,
  same adjuster name allowed at a different carrier, duplicate adjuster
  name at the SAME carrier rejected, `updated_at` trigger fires, and
  `elektrica_app` grant shape confirmed (SELECT/INSERT/UPDATE yes, DELETE
  no) via `has_table_privilege()`. All 7 passed against real staging
  Postgres (`neondb_owner`).
- **App layer** (`app/models.py`, `app/repository.py`, `app/api.py`):
  `InsuranceCarrier`/`Adjuster` dataclasses; repository CRUD
  (`create_insurance_carrier`, `get_insurance_carrier`,
  `find_insurance_carrier_by_name_or_alias` -- case-insensitive lookup
  against name OR any alias, `list_insurance_carriers`,
  `add_insurance_carrier_alias`, `create_adjuster`, `get_adjuster`,
  `list_adjusters_for_carrier`); HTTP routes (`POST`/`GET
  /insurance-carriers`, `GET /insurance-carriers/find` (query-param, not a
  path segment -- same wildcard-collision avoidance as `GET
  /communications`), `GET /insurance-carriers/{id}`, `POST
  /insurance-carriers/{id}/aliases`, `POST`/`GET
  /insurance-carriers/{id}/adjusters`, `GET /adjusters/{id}`). No DELETE
  route anywhere in this family, matching the DB grant.
- 14 new `test_api.py` cases (111/111 direct run, 138/138 pytest):
  create/duplicate-409, list, find-found/find-null-not-404,
  get-found/get-404, add-alias/add-alias-404, create-adjuster/
  carrier-404/duplicate-409, list-adjusters/list-404, get-adjuster-found/404.

**Real bug found and fixed in the verify SCRIPT itself, not the app code
(different class of bug than prior cycles' 500->4xx fixes, worth naming
precisely):** `scripts/verify_013.sql`'s CHECK 6 (updated_at trigger fires
on UPDATE) initially failed when run through a harness that submits an
entire multi-statement `.sql` file as one `psycopg2.execute()` call under
one implicit transaction -- Postgres's `now()` is fixed at transaction
start, so a before/after `now()`-based comparison inside that one
transaction always reads equal, producing a false failure that looks like
a missing trigger but isn't one. Confirmed the trigger itself is correct
by re-running the same check as its own separate statement/transaction
(matches how `psql` -- not available in this environment -- actually runs
a multi-statement script: one implicit transaction PER top-level
statement, not one for the whole file). Documented the trap directly in
the check's own SQL comment so a future session's harness choice doesn't
silently reintroduce it. Not a schema or app-code bug; a test-harness
transaction-boundary gotcha, logged as such rather than "fixed" by
changing the trigger, which was never wrong.

**Live-verified against real staging Postgres, real HTTP** (uvicorn,
`neondb_owner` connection, ports 8511 then 8512 after resolving a
stale-shell-environment-variable false alarm on 8511 -- the FIRST server
process failed with `UndefinedTable: relation "platform.insurance_carrier"
does not exist` even though a direct psycopg2 check in the same terminal
session confirmed the table existed; root cause was the background
server process not inheriting a freshly-exported `DATABASE_URL` from an
earlier command in the same interactive shell, not a real app or schema
bug -- fixed by passing the env var inline on the server's own launch
command instead of relying on shell export propagation into a background
process). Once running correctly: created a real carrier (Geico Insurance
Company, id=13) -> duplicate create -> 409 -> found it by alias (`GEICO`)
via `GET /insurance-carriers/find` -> confirmed a genuinely-missing name
returns `null` with 200, not 404 (deliberate: "no such carrier yet" is not
an error) -> got it by id -> confirmed a bad id returns 404 -> added a
second alias -> created an adjuster (Bob Adjuster, id=17) under it ->
confirmed a nonexistent carrier_id returns 404 -> confirmed a duplicate
adjuster name at the SAME carrier returns 409 -> listed adjusters for the
carrier -> got the adjuster by id -> confirmed a bad adjuster id returns
404. Both server processes killed after their runs; `netstat` confirmed no
LISTENING socket left on either port (8511's underlying python.exe PID
required a second explicit `taskkill` beyond the uvicorn parent PID --
noted for future cycles: verify by PID from `netstat`'s own output, not
just the PID the launch command returned, since uvicorn's actual listener
can be a different process than the one `terminal(background=true)`
reports). All scratch files holding the staging connection string
(temp helper scripts under `%TEMP%`) deleted immediately after use, same
discipline as every other cycle.

**Staging residue left intentionally** (same append-only-adjacent
reasoning as every other smoke run in this repo): `platform.insurance_carrier`
ids 4/7/10/12/13 (test_harness + Geico smoke rows), `platform.adjuster`
ids up through 17.

**Not done / explicitly deferred (unchanged):** the historical
`insurer_payment` import itself (handoff §2.9) remains genuinely
export-blocked -- this cycle's work does not change that, only removes
the *schema* from the blocked list; no auth/session layer on any route;
frontend not started; migration 007's `vls.case` grant-scope flag for Jed
still open (staging-only, not urgent). Migration 013 has NOT been
promoted to production -- new schema Jed hasn't reviewed yet, staying on
staging per standing discipline (nothing promotes without his review),
same posture as migration 010 (`platform.communication`) before its own
review.

**Next up:** `elektrica.demand.carrier_name`/`adjuster_name` (migrations/
006) are still PLACEHOLDER free-text columns per that migration's own
header comment ("no insurance_carrier/adjuster tables exist yet"). Now
that they do, wiring `elektrica.demand` to reference
`platform.insurance_carrier`/`platform.adjuster` by id instead of free
text is the natural next step -- but that is a real schema change to an
existing table with a CHECK constraint tying into it
(`demand_carrier_name_required_for_carrier_recipient`), so it deserves
its own migration + careful review rather than folding into this cycle.
Logged as the concrete next item rather than left implicit.

## 2026-09-05 (cron cycle) — elektrica.demand carrier/adjuster FK wiring, staging-only

Closed the concrete "next up" item logged at the end of the previous
entry: `elektrica.demand.carrier_name`/`adjuster_name` (migration 006
PLACEHOLDER free text) now reference `platform.insurance_carrier`/
`platform.adjuster` (migration 013) by id.

- **`migrations/014_elektrica_demand_carrier_fk.sql`** (staging-only, new
  migration): adds `carrier_id BIGINT REFERENCES platform.insurance_carrier`
  and `adjuster_id BIGINT REFERENCES platform.adjuster` to
  `elektrica.demand`; backfills both from the 3 existing staging smoke
  rows' `carrier_name` values (find-or-create a matching
  `platform.insurance_carrier` row by exact name, since these are fresh
  smoke-test names with no alias history yet); drops the old
  `demand_carrier_name_required_for_carrier_recipient` CHECK and replaces
  it with `demand_carrier_required_for_carrier_recipient` (same shape,
  `carrier_id IS NOT NULL` instead of `carrier_name IS NOT NULL`); drops
  the now-empty `carrier_name`/`adjuster_name` columns. **New invariant
  this migration adds, not present before:** a `BEFORE INSERT OR UPDATE`
  trigger (`trg_demand_check_adjuster_carrier_match`) rejects any row
  where `adjuster_id` is set but belongs to a DIFFERENT carrier than
  `carrier_id` -- a plain FK/CHECK can't express that cross-table
  column-equality rule, hence the trigger. No new grants needed:
  `elektrica_app` already had SELECT/INSERT/UPDATE on `elektrica.demand`
  (migration 006) and SELECT on both `platform.*` tables (migration 013).
- **`scripts/verify_014.sql`**: 7 checks -- create with real carrier+
  adjuster and confirm the join reads back correctly, confirm
  `carrier_name`/`adjuster_name` columns are actually gone
  (`information_schema.columns`), missing-`carrier_id`-when-
  recipient=carrier rejected, bad `carrier_id` FK rejected, mismatched
  adjuster/carrier rejected (INSERT path), renter-recipient demand still
  needs no `carrier_id` (confirms the new CHECK didn't over-tighten), and
  the mismatch trigger also fires on UPDATE, not just INSERT. All 7
  passed against real staging Postgres.
- **App layer**: `app/models.py`'s `Demand` dataclass swaps
  `carrier_name`/`adjuster_name` (str) for `carrier_id`/`adjuster_id`
  (int), `__post_init__`'s recipient-type check updated to match;
  `app/repository.py`'s `create_demand`/`_demand_from_row` updated to the
  new columns; `app/api.py`'s `DemandIn`/`DemandOut` swap to
  `carrier_id`/`adjuster_id` ints, `_demand_to_out` echoes them back, and
  `create_demand`'s route gains two new except clauses mapping
  `psycopg2.errors.ForeignKeyViolation` (bad carrier_id/adjuster_id) and
  `psycopg2.errors.RaiseException` (the new cross-carrier trigger) to
  400 -- same recurring 500->4xx discipline this repo has hit on every
  prior FK-touching route (link_vls_case, document-template duplicate,
  insurance-carrier/adjuster creation). Used `str(e)` rather than
  `e.diag.message_primary` for the error detail -- `psycopg2.Error.diag`
  is a read-only C-level attribute that a unit test can't construct on a
  bare `Error()` instance the way a real live connection populates it,
  so `str(e)` is what's actually testable without a real DB, and it
  carries the same information for a 400 response anyway.
- Updated the two DB-touching smoke scripts
  (`scripts/_smoke_repository.py`, `scripts/_smoke_elektrica_app_role.py`)
  to create a real `platform.insurance_carrier` row and pass its id
  instead of a bare `carrier_name` string, since the column no longer
  exists.
- 22 new/updated `test_api.py`/`test_models.py` cases (140/140 passed,
  up from 138/138): the two demand-model tests renamed
  `..._requires_carrier_name`/`..._no_carrier_name_needed` ->
  `..._requires_carrier_id`/`..._no_carrier_id_needed` with matching
  bodies, plus two brand-new API tests
  (`test_create_demand_unknown_carrier_id_returns_400`,
  `test_create_demand_mismatched_adjuster_carrier_returns_400`) covering
  the two new except clauses.

**Applied to real staging Postgres and live-verified over real HTTP**
(uvicorn on port 8611, `neondb_owner`-class `DATABASE_URL` passed inline
on the launch command per this repo's own documented Windows
background-process env-var gotcha). Migration applied statement-by-
statement via a one-off psycopg2 script (no `psql` in this environment,
same as every prior migration) -- hit the exact CHECK-violation-on-
backfill issue the migration file's own header now documents: the first
draft dropped `carrier_name`/`adjuster_name` outright assuming no real
data existed, but staging already had 3 smoke rows with real
`carrier_name` values from prior cycles' runs (`Acme Insurance`,
`Role Smoke Insurance` x2) that violated the new `carrier_id`-based
CHECK the moment it was added. Fixed by adding the backfill INSERT/UPDATE
step described above before the DROP COLUMN, confirmed via a direct
`information_schema.columns` query that no stale-partial-migration state
was left from the failed first attempt (columns/indexes from statements
1-3 had already committed independently before statement 5 failed, since
each statement commits on its own in this repo's split-execution
discipline -- re-ran only the not-yet-applied remaining statements
rather than the whole file a second time). Once schema was correct: ran
uvicorn, created a real demand (id=11) on rental id=1 with carrier_id=13
(Geico) + adjuster_id=17 (Bob Adjuster, correctly under Geico) -> 200 ->
confirmed a mismatched adjuster_id=19 (belongs to a different carrier)
against carrier_id=13 -> 400 with the trigger's own message -> confirmed
carrier_id=999999 (nonexistent) -> 400 -> confirmed omitting carrier_id
entirely on a carrier-recipient demand -> 400 (app-layer, pre-DB-round-
trip) -> marked demand id=11 sent via fax -> 200, `carrier_id`/
`adjuster_id` echoed correctly throughout. Server killed after
(`netstat`-confirmed PID, not the launch command's own reported PID, per
this repo's own documented lesson from the migration-013 cycle); no
LISTENING socket left on 8611. All scratch files holding the staging
connection string deleted immediately after use.

**Staging residue left intentionally** (same append-only-adjacent
reasoning as every other smoke run in this repo): `platform.insurance_carrier`
ids 15/16 (backfilled from migration 014's own INSERT, `created_by`=
`migration_014_backfill`) plus 17/18 (verify_014.sql's own test rows);
`platform.adjuster` ids 19/20; `elektrica.demand` id 11 (this cycle's
live HTTP smoke) plus ids 6/7 (verify_014.sql's own rows) and the
pre-existing ids 1/3/5 (now pointing at carrier_id=15/16 instead of
carrying free-text `carrier_name`, via the backfill).

**Not done / explicitly deferred:** the historical `insurer_payment`
import (handoff §2.9) remains genuinely export-blocked, unchanged by
this cycle. Migration 014 has NOT been promoted to production -- it's
new schema built on top of migration 006/013, both themselves still
staging-only, so this stays staging-only too, same inheritance logic as
every dependent migration in this repo. No auth/session layer on any
route; frontend not started; migration 007's `vls.case` grant-scope flag
for Jed still open (staging-only, not urgent).

**Next up (as of prior cycle):** with carrier/adjuster now properly
FK-wired, the natural next buildable items were (a) a
`GET /rentals/{id}/demands` list route; (b) the renter-provisioning
JotForm intake flow (handoff §2.2, needs
`platform.match_or_create_person()`); (c) frontend, still fully
unstarted. Item (a) closed this cycle -- see entry below.

## 2026-09-05 (cron cycle, later) -- `GET /rentals/{id}/demands` list route

Closed the concrete "next up" item (a) from the previous entry: no
schema change needed, pure app-layer gap.

- **`app/repository.py`**: new `list_demands_for_rental(cur, rental_id)`
  -- `SELECT * FROM elektrica.demand WHERE rental_id = %s ORDER BY
  created_at`, same shape/ordering convention as
  `list_tolls_for_rental`/`list_rental_events`. No status filter (draft
  and sent both belong in this view, same as every other `list_*` in
  this repo -- no query-param filtering exists anywhere yet).
- **`app/api.py`**: new `GET /rentals/{rental_id}/demands` ->
  `list[DemandOut]`, mirrors `get_rental_events`'s 404-if-rental-missing
  shape exactly.
- **`test_api.py`**: 2 new cases (`test_get_rental_demands`,
  `test_get_rental_demands_rental_not_found`), registered in the
  file's manual `__main__` test list. **Also fixed a real gap found
  while doing this**: the manual test list was missing
  `test_create_demand_unknown_carrier_id_returns_400` and
  `test_create_demand_mismatched_adjuster_carrier_returns_400` from the
  migration-014 cycle -- they existed and were pytest-collected fine,
  but `python test_api.py` (the manual runner) was silently skipping
  both. Added both to the list. 142/142 pytest, 115/115 manual runner
  (up from 140/140 and 113 actually run despite claiming otherwise).
- **Live-verified against real staging** (uvicorn port 8612,
  `neondb_owner` DSN passed inline per this repo's Windows env-var
  convention): `GET /rentals/1/demands` -> 200, 2 rows (ids 1, 11) in
  correct created_at order; `GET /rentals/8/demands` -> 200, 2 rows
  (ids 6, 10, one carrier-recipient draft + one renter-recipient
  draft, both correctly typed); `GET /rentals/999999/demands` -> 404.
  Server killed after, `netstat`-confirmed no LISTENING socket left on
  8612. Scratch DSN file deleted immediately after use.

**Not done / explicitly deferred (unchanged):** `insurer_payment`
import still export-blocked; migrations 006/013/014 (and this cycle's
app-layer change riding on top of them) remain staging-only pending
Jed's review; no auth/session layer on any route; frontend not started;
migration 007's `vls.case` grant-scope flag for Jed still open.

**Next up:** (b) the renter-provisioning JotForm intake flow (handoff
§2.2) is now the most concrete remaining backend item -- needs
`platform.match_or_create_person()` per `docs/BACKLOG.md`'s existing
entries, not bespoke matching logic. Frontend (c) remains fully
unstarted and is the other open front.

## 2026-09-05 (cron cycle, later still) -- JotForm renter-intake flow (handoff §2.2 step 1), real end to end

Closed item (b) from the previous entry: no schema change, pure app-layer
work sitting on migration 001's already-existing `elektrica.renter` /
`platform.person` / RLS structure. Also closed a real permission gap
discovered while building it.

**Discovered first, by direct query against real staging Postgres (not
assumed from the migration file's comments alone):** `platform.match_or_create_person()`
is `SECURITY DEFINER`, owned by `neondb_owner`, with `EXECUTE` granted
ONLY to `neondb_owner` and `platform_identity_service` (`REVOKE ALL`
first). `elektrica_app` has **zero** role memberships at all --
confirmed via `pg_auth_members`, not just "no grant on this one
function": it cannot `SET ROLE platform_identity_service` to reach the
function even indirectly. This matters because `app/api.py`'s
`get_cursor()` dependency optionally does `SET ROLE elektrica_app`
(`ELEKTRICA_DB_SET_ROLE`) for exactly the reason app/db.py's own
docstring documents -- exercising real least-privilege grants, not a
superuser connection. If the intake route had reused `get_cursor()`,
turning that env var on in any deployment would silently break renter
intake with a raw `psycopg2.errors.InsufficientPrivilege` (500), not a
graceful error.

**Fix:** new `app/api.py` dependency `get_privileged_cursor()` --
connects via the same `ELEKTRICA_DB_ENV_VAR`-named connection string but
ALWAYS skips `SET ROLE` (ignores `ELEKTRICA_DB_SET_ROLE` entirely), so it
authenticates as whatever LOGIN role the connection string names
(`neondb_owner`-class in every environment this repo has run in so
far -- the same role docs/BACKLOG.md already documents as the
sanctioned admin-script escape hatch for `platform.person` writes, not
a new privilege boundary). Used only by the one new route below.

- **`app/repository.py`**: `match_or_create_and_link_renter()` --
  `SET ROLE platform_identity_service`, calls
  `platform.match_or_create_person()` (positional args matching its real
  signature, confirmed by `pg_get_functiondef` against staging:
  `p_first_name, p_last_name, p_date_of_birth, p_email_normalized,
  p_phone_normalized, p_source_project, p_submitted_by`, `source_project`
  hardcoded `'elektrica'`), then `RESET ROLE` before touching
  `elektrica.renter` (`platform_identity_service` has no grants on the
  `elektrica` schema at all, by design -- would fail if not reset).
  Branches on `match_status`: `attached`/`created` call the existing
  `create_renter_for_existing_person()`; `queued` deliberately returns
  `renter=None` and the real `queue_id` -- per `docs/BACKLOG.md`'s
  explicit rule (repeated twice in that file already), a queued match
  must never be treated as linked. New `RenterIntakeResult` dataclass
  (`match_status`, `person_id`, `queue_id`, `renter`) since `queued`'s
  no-renter-yet shape doesn't fit the existing `Renter` dataclass.
- **`app/api.py`**: `get_privileged_cursor()` (see above);
  `RenterIntakeIn`/`RenterIntakeOut` schemas; `POST /renters/intake`.
  Route body collects `first_name`/`last_name`/`actor` (required) plus
  optional `date_of_birth`/`email`/`phone`/`jotform_submission_ref`/
  `drive_folder_ref` -- handoff §2.2's address/insurance/billed-to fields
  are explicitly NOT collected here (no schema column exists for any of
  them yet; flagged in the route's own docstring as a real scope gap,
  not silently dropped). Does not normalize email/phone before calling
  the repository function -- flagged in the route docstring as a real
  gap (no normalization utility exists in this codebase yet) and logged
  below, not silently done wrong.
- **`test_api.py`**: `get_privileged_cursor` added to the same mocked
  dependency-override pattern as `get_cursor`; 3 new cases
  (`test_intake_renter_attached`, `test_intake_renter_created`,
  `test_intake_renter_queued_has_no_renter`), the last one asserting
  `renter is None` specifically to guard the queued-must-not-link rule
  above. 145/145 pytest (up from 142/142), 118/118 manual runner (up
  from 115/115), both registered in the manual `__main__` list.

**Live-verified against real staging Postgres, two layers deep:**
1. Direct psycopg2 script exercising the exact `SET ROLE
   platform_identity_service` -> call -> `RESET ROLE` -> insert sequence
   the repository function performs: first call with a fresh unique
   email -> `created` (person_id=36); identical second call with the
   SAME email -> `attached`, same person_id=36 -- proving the identity
   match itself works before trusting the app layer on top of it.
2. Real uvicorn (port 8620, `neondb_owner`-class `DATABASE_URL` inline on
   the launch command, no `ELEKTRICA_DB_SET_ROLE` set -- matches this
   route's actual intended deploy shape) driving `POST /renters/intake`
   over real HTTP for all three outcomes: `created` (person_id=38, then
   39 with a fresh email) -> `attached` (second call, same email,
   correctly returned person_id=39 again with the SAME renter_id=13,
   not a duplicate) -> `queued` (seeded a real `platform.person` row
   with a distinct last_name+DOB first, then submitted a different
   first_name against that same last_name+DOB -> got back
   `match_status=queued`, `queue_id=2`, `renter=null`). Directly queried
   `elektrica.renter` afterward to confirm NO row was created for the
   queued person_id -- the withholding behavior is real, not just
   returned-but-ignored. Server killed after
   (`netstat`-confirmed PID, not the launch command's own reported PID);
   confirmed no LISTENING socket left on 8620. All scratch DSN files
   (including two stale ones left over from a PRIOR cycle, dated
   2026-09-04 -- `eleks_staging_owner.txt`, `uvicorn_smoke.log` -- found
   and deleted this cycle as cleanup debt, not new residue) deleted.

**Staging residue left intentionally** (same append-only-adjacent
reasoning as every other smoke run in this repo): `platform.person` ids
36/37/38/39; `elektrica.renter` ids 11/12/13; `platform.person_match_queue`
id 2 (status `pending` -- a real, currently-unresolved queue entry, left
deliberately since resolving it requires an actual human confirm-or-split
decision this cycle correctly does not make unilaterally).

**New backlog item (not urgent, logged not silently done wrong):** no
email/phone normalization utility exists anywhere in this codebase.
`POST /renters/intake` passes JotForm-submitted email/phone straight
through to `platform.match_or_create_person()`, whose exact-match step
does a literal string comparison against already-normalized
`platform.person` rows -- un-normalized input (mixed case email, phone
with punctuation/formatting) will silently under-match and create
duplicate `platform.person` rows instead of attaching. Added to
`docs/BACKLOG.md`.

**Not done / explicitly deferred (unchanged):** `insurer_payment` import
still export-blocked; migrations 006/013/014 remain staging-only pending
Jed's review; no auth/session layer on any human-operated route (the new
`/renters/intake` route has the SAME standing gap as every other route
in this file -- it is not bot-gated like `/rentals/{id}/proposals`,
since a JotForm webhook caller isn't the same shape as the bot-proposal
contract; flagged, not assumed); migration 007's `vls.case` grant-scope
flag for Jed still open; frontend not started.

**Next up:** with renter intake now real, remaining concrete backend
gaps are (a) the email/phone normalization utility just flagged above,
(b) resolving `platform.person_match_queue` entries (no admin action
exists yet to confirm-or-split a queued match -- this cycle's own
queue_id=2 row is a live example sitting unresolved), and (c) frontend,
still fully unstarted.

## 2026-09-05 (cron cycle, later) -- email/phone normalization utility, closes prior backlog item

Closed item (a) from the previous cycle's entry: pure app-layer addition,
no schema change, sitting on the already-existing `POST /renters/intake`
route.

**`app/normalize.py`** (new): `normalize_email()` (lowercase + strip,
`None`/blank -> `None`) and `normalize_phone()` (strip to digits-only,
`None`/blank/no-digits -> `None`). Deliberately kept Elektrica-local, not
extracted to a shared `platform.*` module -- checked Complete Collision's
equivalent call site first (`app/repository.py`'s
`create_customer_and_link()`): it inlines `email.strip().lower()` for
email only, does not normalize phone at all, and still does a bespoke
raw `INSERT INTO platform.person` rather than calling
`platform.match_or_create_person()` (a known, separately-flagged gap in
that repo). Per ADR-001's own extraction rule ("`_shared` extracted only
when a second consumer exists"), Collision's inline email-only version
doesn't make this a second real consumer of the phone-normalizing half --
Elektrica is effectively first. Documented in the module's own docstring
so this isn't rediscovered as an oversight later; promote to `platform`
the moment a second real phone-normalizing consumer shows up.

**`app/api.py`**: `POST /renters/intake` now calls `normalize_email()`/
`normalize_phone()` on `body.email`/`body.phone` before passing to
`repo.match_or_create_and_link_renter()` -- previously passed raw
JotForm-submitted strings straight through, which would silently
under-match against already-normalized `platform.person` rows (the exact
duplicate-creation risk this closes).

**`test_normalize.py`** (new): 12 cases -- lowercasing, whitespace
stripping, None/blank -> None for both, punctuation/letter stripping for
phone, and one case (`test_normalize_phone_leading_country_code_not_stripped`)
explicitly pinning the CURRENT documented behavior (no US country-code
stripping) so a future change to it is a visible diff, not a silent
regression. **157/157 pytest** (up from 145/145 -- 12 new). Manual
runners unaffected: `test_models.py` 27/27, `test_api.py` 118/118 --
`test_normalize.py` follows the same standalone-runnable pattern and was
run directly (12/12).

**Live-verified against real staging Postgres** (uvicorn port 8631,
`neondb_owner`-class `DATABASE_URL` inline, no `ELEKTRICA_DB_SET_ROLE` --
same deploy shape as the intake route's own intended use): submitted a
mixed-case, padded email -> `created` (person_id=41), then the
already-normalized form of the SAME email -> `attached`, same
person_id=41 -- proving the normalization actually prevents the
duplicate, not just theoretically. Same proof for phone: a punctuated
number -> `created` (person_id=42), then its digits-only form ->
`attached`, same person_id=42. Directly queried `platform.person`
afterward to confirm the STORED values are actually normalized at rest
(id 41: lowercase/stripped email; id 42: digits-only phone, no
punctuation) -- not just coincidentally matching. Server killed after;
`netstat` confirmed no LISTENING socket left on 8631 (only expected
client-side `TIME_WAIT` residue). Scratch verification script
(`scripts/_check_norm_smoke.py`) deleted immediately after use.

**Staging residue left intentionally** (same append-only-adjacent
reasoning as every prior smoke run in this repo): `platform.person` ids
41/42; `elektrica.renter` ids 14/15.

**Not done / explicitly deferred (unchanged):** `insurer_payment` import
still export-blocked; migrations 002-010/012-014 remain staging-only
pending Jed's review; no auth/session layer on any route; frontend not
started; migration 007's `vls.case` grant-scope flag for Jed still open;
`platform.person_match_queue` id=2 (from a prior cycle) still sits
pending human resolution -- no admin action exists yet to confirm-or-split
it.

**Next up:** with both concrete backend items from the prior cycle now
closed, the two remaining fronts are (a) a `platform.person_match_queue`
resolution admin action (confirm-or-split a queued match -- queue_id=2 is
a live, currently-unresolved example) and (b) frontend, still fully
unstarted. Picking (a) next cycle by default since it is the smaller,
more concrete gap and directly unblocks a currently-stuck real row.

## 2026-09-05 (continuous cron cycle) -- platform.person_match_queue confirm-or-split admin action closed

**Starting point:** clean tree, fetched origin/main first (matched local
HEAD at f601a89, no concurrent-session drift).

**What:** the previous cycle's own "Next up" pointed straight at this --
`queue_id=2` had sat `pending` since it was first created, because no
admin action existed to resolve a `person_match_queue` row. Full details
logged in `docs/BACKLOG.md`'s matching 2026-09-05 entry (kept there per
this repo's own split: BACKLOG.md for decided-not-yet-actionable items
that just became actionable, BUILD_LOG.md for the narrative). Summary:
`repo.list_pending_person_match_queue_items()` +
`repo.resolve_person_match_queue()` (confirmed_match / confirmed_split),
both gated behind `get_privileged_cursor()`, both hard-refuse
`source_project='vls'` rows in code (403), `confirmed_match`/`split`
additionally link an `elektrica.renter` when the row's `source_project`
is `'elektrica'` (never for `'collision'`). Two new routes:
`GET /person-match-queue/pending`, `POST /person-match-queue/{id}/decision`.

**Tests:** 6 new mocked `test_api.py` cases -- **163/163 pytest** (up
from 157/157), **124/124** manual runner.

**Live-verified against real staging Postgres, on the actual
long-pending row, not just synthetic data:** uvicorn port 8720,
`neondb_owner`-class `DATABASE_URL` inline, no `ELEKTRICA_DB_SET_ROLE`.
Resolved the REAL `queue_id=2` via `confirmed_match` -> `person_id=37`,
new `elektrica.renter` id=16 -> `GET /pending` now empty. Retried same
decision -> 400. Nonexistent id -> 404. Bad decision string -> 400.
Inserted two fresh synthetic rows to reach the two paths the real data
couldn't: a `source_project='elektrica'` row through `confirmed_split`
(-> 200, new `platform.person` id=44, new `elektrica.renter` id=17,
name/DOB verified copied correctly by direct SELECT) and a
`source_project='vls'` row through `confirmed_match` (-> **403**, then
DIRECTLY queried the row afterward to confirm it was NOT mutated --
`status` still `pending`, `resolved_by` still `NULL` -- the refusal is a
hard no-op on the DB, not just an error response with a silent side
effect). Server killed after; `netstat` confirmed no `LISTENING` socket
left, only expected client-side `TIME_WAIT`. All three scratch scripts
used for this deleted immediately after use, same standing discipline
as every prior cycle's smoke scripts.

**Staging residue left intentionally:** `platform.person` ids 43/44;
`elektrica.renter` ids 16/17; `person_match_queue` ids 2/3 now resolved,
id 4 (`vls`) deliberately left `pending` forever as a permanent
regression-guard fixture proving this bot's admin surface refuses to
touch VLS rows.

**Not done / explicitly deferred (unchanged):** no auth/session layer on
any route; migrations 002-010/012-014 staging-only pending Jed's review;
migration 007's `vls.case` grant-scope flag still open; frontend not
started.

**Next up:** the person_match_queue gap that persisted across several
cycles is finally closed. Frontend (ADR-001 v2 SS6/SS9, explicitly last in
build order) is now the only large unstarted front -- worth a cycle
surveying the full existing route surface first to scope a minimal first
screen deliberately, rather than guessing at scope mid-build.


## 2026-09-04 (later) — real Fleet/Rental exports landed; inspected, discrepancy found and flagged

Jed's OAuth restoration finally unblocked Kay's real exports:
`data/real_exports/elektrica_fleet_export.json` and
`elektrica_rental_export.json`, saved locally, already correctly
gitignored before I touched anything (verified with `git check-ignore -v`
rather than assumed — both files confirmed excluded).

Inspected structure only, never printed any actual PII values (header/
column names are safe to log; data values were described by length/type
class, e.g. "looks_like_email", never printed verbatim):

- **Real discrepancy found, not resolved unilaterally:** `Fleet info`'s
  real columns are `Year, Make, Model, Nickname, VIN, Plate, Miles, Toll
  Tag, Owner, Lender, Ownership Type` — no `class` or `tracking_system`
  column exists, directly contradicting the ADR's own "confirmed by Jed,
  2026-09-03" note that these columns are real. Kay's original static-
  analysis skeleton doc had actually flagged this correctly the first
  time ("not evidenced in source"); the real data agrees with that
  original caution, not with the later "confirmed" answer. Caveat: only
  2 of 88 Fleet tabs were parsed into row data — the ~53 per-vehicle
  tabs are unparsed, so class/tracking data could still live there.
  **Not touching `elektrica.vehicle`'s enum values in either direction**
  pending Jed's clarification — logged as an open question, not guessed
  at, in `docs/OVERNIGHT_DECISIONS.md`.
- Rental Management's real headers (`Current Rentals`/`Finished Rentals`)
  corroborate `elektrica.rental`/`demand`/`toll` as already built — no
  contradiction, `body_shop`/`rental_type` as free TEXT (rather than an
  enum) validated as the right call since real enum VALUE lists still
  aren't available (the `Settings` tab has the right COLUMN names but the
  export only returned 1 of 93 declared rows — nowhere near enough to
  safely define enum value sets from).
- Flagged a data-quality issue in the export itself for whoever reads it
  next: each Rental Management tab's own declared `headers` field is
  broken (repeats the tab title, not real columns) — the real header row
  is buried in `sample_rows[1]`, not `sample_rows[0]`.
- Replaced the old "BLOCKER — exports haven't landed" entry in
  `docs/OVERNIGHT_DECISIONS.md` with the full findings above, framed as
  RESOLVED-WITH-A-DISCREPANCY rather than either fully resolved or still
  fully blocked.
- No schema changes made this cycle — this was investigation and
  flagging only, deliberately not a "the export landed so promote
  everything" pass. Deleted the throwaway inspection script afterward;
  nothing PII-adjacent was ever committed.

**Next up:** hold on `elektrica.vehicle` enum corrections until Jed
answers the class/tracking_system question. `insurer_payment`/`adjuster`
historical import (handoff §2.9) remains genuinely blocked separately —
this export didn't include payment history at all, only Fleet + Rental
Management.

## 2026-09-05 — migration 015: dropped elektrica.vehicle.class/tracking_system (Jed's answer)

Jed's direct answer to the discrepancy flagged above: `class`/
`tracking_system` don't exist as separate columns anywhere in the real
Fleet data (not just "not on Fleet info" -- covers the per-vehicle tabs
too). Drop them from `elektrica.vehicle`; derive/infer that info
differently elsewhere if the app layer ever needs it, rather than
storing a column sourced from a Sheet field that doesn't exist.

- **migrations/015_elektrica_vehicle_drop_class_tracking.sql**: drops
  `elektrica.vehicle.class`, `elektrica.vehicle.tracking_system`, and the
  now-unused `elektrica.tracking_system` enum type. `elektrica.vehicle_class`
  the TYPE stays -- still used by `elektrica.comparable_set.vehicle_class`
  (a market-rate classification, never FK'd to `vehicle.class`). New
  migration rather than editing migration 002 in place, matching this
  repo's established "fix gets its own numbered migration" convention
  (same as migration 012). No data preserved/migrated: confirmed against
  the production branch directly first that `elektrica.vehicle` was
  never promoted, so every row anywhere is test/smoke data.
- Verified 5/5 checks on staging: columns gone, `tracking_system` type
  gone, `vehicle_class` type intact, `elektrica.vehicle` still inserts
  fine on remaining columns, `elektrica.comparable_set.vehicle_class`
  still works end-to-end.
- Updated the app layer to match: `app/models.py` (dropped
  `TrackingSystem` enum and `Vehicle.vehicle_class`/`.tracking_system`
  fields; kept `VehicleClass` for `ComparableSet`), `app/repository.py`
  (`create_vehicle`/`_vehicle_from_row`), `app/api.py`
  (`VehicleIn`/`VehicleOut` schemas, `create_vehicle` handler,
  `_vehicle_to_out`), `test_api.py` (removed the two now-meaningless
  bad-enum-value tests, fixed the two that still apply), and
  `scripts/_smoke_repository.py`. All 149 pytest tests pass.
- **Collision note:** while working this, discovered the local working
  tree had moved from commit `6ff394d` to `66f56fd` without me running
  `git pull` myself -- a concurrent process/session committed a real
  shared-secret JWT auth middleware feature (`GET /me`, SSO verification
  against `elektrica.staff_user`) directly on top of my *uncommitted*
  in-progress migration-015 edits sitting in the shared working
  directory, and pushed the combined result. Verified carefully before
  trusting any of it: diffed my originally-written migration 015 /
  verify_015.sql against what's in that commit (byte-identical), diffed
  `app/repository.py`'s vehicle-column removal (present, correct), and
  ran the full pytest suite against both the pre- and post-collision
  state to confirm nothing regressed. No data loss, no incorrect merge
  -- just an unusual instance of two sessions' edits landing in the same
  commit because they were both live in the same working directory at
  once. Flagging this pattern (not just origin-vs-local collisions, but
  same-working-directory-uncommitted-edit collisions) as worth raising
  with hermes/Jed if it recurs.
- Added `docs/BACKLOG.md` entry for the real Fleet columns
  (Year/Make/Model/Nickname/Plate/Miles/Toll Tag/Owner/Lender/Ownership
  Type) that `elektrica.vehicle` still doesn't have at all -- explicitly
  NOT bundled into migration 015 since Jed's instruction was to drop
  class/tracking_system, not add the rest; that's new scope needing its
  own sign-off (Owner/Lender person_id-vs-free-text question especially).

## 2026-09-05 — collision explained: not a third party, hermes's own frontend subagent

hermes clarified the "concurrent session" that landed `66f56fd` alongside
my in-progress migration-015 edits: it was hermes's own subagent,
dispatched into this same repo directory to build the frontend (UI push
targeted for Monday) at the same time I was finishing backend work --
not an unknown third party. hermes has steered that subagent to
git status/pull before every commit and push in smaller increments going
forward. Confirmed independently: no damage either way, both bodies of
work (migration 015 + JWT auth/CORS) are intact in git log, my migration/
verify files landed byte-identical to what I wrote. Noting for the
paper trail, not a new action item -- see this file's earlier
"Collision note" entry for the verification steps taken at the time.

`web/` directory now present, untracked, in the working tree -- that's
the frontend subagent's in-progress work. Not touching it.
