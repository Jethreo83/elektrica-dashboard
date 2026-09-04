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
