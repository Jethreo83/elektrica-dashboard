# Overnight Decisions Log — Elektrica Dashboard

Started 2026-09-03 overnight, per hermes's standing overnight rules (Jed
unreachable until morning). Purpose: anything that would normally need
Jed's direct sign-off gets queued here instead of decided unilaterally.
Genuine unknowns that block a build item get logged here too, per rule 3,
and I move to the next item rather than idling. hermes is keeping a
matching file in vls-dashboard and will read all of these back to Jed when
he checks in.

Format per entry: STATUS (PENDING / BLOCKER), what, why, what happens if we
wait vs. proceed, my recommendation if I have one.

---

## BLOCKER — JP litigation state machine wiring (ADR-001 v2 §7 item 5)

**What:** `elektrica.rental`'s state machine (migration 003) stops at
`needs_served` with a TODO instead of continuing into the JP litigation
states (`answered -> motion_limited_discovery_filed -> discovery_open ->
settled/dismissed/judgment`), which VLS already has working in
`vls.valid_next_states('jp', ...)` (VLS migration 002).

**Why not resolved tonight:** ADR-001 v2 §7 item 5 lists this as an
explicitly open *implementation* question with three real alternatives
Jed hasn't chosen between: (a) same-repo shared package both apps import,
(b) a duplicated-but-identical migration in elektrica's own schema, (c) an
actual service boundary (API call between apps). These have different
long-term coupling/ops tradeoffs between two separate businesses' schemas —
exactly the kind of "touching another business's schema" decision the
overnight rules ask me to queue rather than decide alone, even though I
have read clearance on the VLS files themselves.

**What happens if we wait:** `elektrica.rental` rows can reach
`needs_served` and stop there (flagged, not silently stuck — see
`elektrica.blocked_rentals` view) until Jed picks an option. No JP
litigation for a rental can be tracked in the dashboard until this closes.
No revenue-blocking impact tonight since there's no real rental data yet
(schema-only build phase).

**What happens if I proceed anyway:** I'd have to pick one of (a)/(b)/(c)
myself. Cheapest one (direct cross-schema call to
`vls.valid_next_states('jp', ...)` via a nullable FK from `elektrica.rental`
to `vls.case`) is technically low-risk (same pattern already approved for
`platform.person`), but it's still Jed's call per the ADR's own framing,
not mine to default into.

**My recommendation for when Jed's back:** option (a) or the direct
cross-schema call — both keep the JP engine as a true single source of
truth (VLS migration 002's exact logic, not a fork), and Elektrica's
`platform.person`-style cross-schema reference is already the established
pattern in this codebase. Duplicating the migration (b) risks drift between
two copies of the same 12-state machine.

---

## BLOCKER — Real Fleet / carrier / insurer-payment Sheet exports

**What:** Kay's `CLAUDE_TO_KAY_006` export tasking (Fleet sheet, insurance
carrier contact list, insurer-payment history) has not landed —
`~/Downloads/elektrica_exports/` still only has the two skeleton docs from
static code analysis, no real CSVs. Blocked on Elektrica Google OAuth
restoration on Kay's host; no ETA as of this session.

**Why this blocks things:** `elektrica.vehicle`'s `class` /
`vehicle_status` / `tracking_system` enum value sets are placeholder
(handoff prose, not real column values) — carries an explicit DO-NOT-PROMOTE
banner. Everything downstream that FKs to `elektrica.vehicle`
(`elektrica.rental`, in turn anything FKing to `rental`) inherits the same
staging-only status, since Postgres won't let a migration apply to
production if it FKs a table that doesn't exist there yet. `insurance_carrier`
and `insurer_payment`/`adjuster` tables can't be schema-designed responsibly
at all yet — no real columns to validate field names against.

**What happens if we wait:** Schema work continues on staging (rental
lifecycle, proposals, demand/comparable_set shapes) without being blocked;
none of it can promote to production until the export lands and the
`elektrica.vehicle` enums are corrected.

**What happens if I proceed anyway:** Already doing the sanctioned version
of this — building on staging with explicit confirmed-vs-placeholder
comments per field, never promoting the placeholder pieces. Nothing further
to decide here; this is a genuine external dependency (someone else's OAuth
restoration), not a decision I can make my way out of.

---
