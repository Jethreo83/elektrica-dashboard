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

## BLOCKER — JP litigation state machine wiring (ADR-001 v2 §7 item 5) — RESOLVED, see below

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

## PENDING — Document generator: build inside `elektrica` schema, not `platform.*`

**What:** Handoff §1.3 frames the shared document generator as a platform
primitive both VLS and Elektrica need. Migration 005 built its storage/log
tables (`document_template`, `document`, `outbound_log`) inside the
`elektrica` schema instead of `platform.*`.

**Why queued instead of just done:** ADR-001's extraction rule is "extract
only when a second consumer exists." VLS hasn't built a document generator
yet (confirmed in the handoff: "neither VLS nor you have built one yet"),
so there's no second real consumer to justify a `platform.*` placement
tonight. But this is genuinely a cross-cutting architecture call — where
shared infrastructure physically lives affects both businesses' schemas —
so I'm not treating "I think the rule says elektrica-schema-for-now" as
equivalent to Jed or hermes actually deciding that.

**What happens if we wait:** Elektrica's rental-demand document flow keeps
building on the elektrica-schema version, fully functional for Elektrica's
own use. If Jed/hermes later want it moved to `platform.*` once VLS builds
its own document needs, it's a straightforward move — the schema was
written to the handoff's exact platform-primitive contract
(template_id/version, merge_data, attachments, output_hash) specifically
so relocation is a rename + grant change, not a redesign.

**What happens if I proceed differently:** Building directly in
`platform.*` now would preemptively couple VLS to a schema shape neither
VLS nor Jed has reviewed, for a feature VLS hasn't asked for yet — higher
risk than waiting, not lower.

---

## RESOLVED 2026-09-04 — JP litigation state machine wiring (was ADR-001 v2 §7 item 5)

**Decision (Jed, via hermes):** option (a) — shared/cross-schema reuse of
`vls.valid_next_states()`, matching my recommendation below. Implemented
in `migrations/007_elektrica_jp_litigation.sql`.

**What was built:** `elektrica.rental` gained a nullable `vls_case_id` FK
to `vls.case`. A new `in_litigation` state sits between `needs_served` and
`resolved`. Elektrica's litigation is driven entirely through `vls.case` +
`vls.case_event` using VLS migration 002's existing, already-verified
`valid_next_states()`/trigger logic (including the JP discovery trap) —
zero new JP-specific transition rules defined in the elektrica schema.
`resolved` is gated on the linked `vls.case.current_state` having reached
one of VLS's own terminal states (settled/dismissed/judgment), checked by
a new trigger that only reads `vls.case`, never re-derives its logic.

**Verified with `scripts/verify_007.sql`** (6 checks): `in_litigation`
blocked without a linked `vls.case`; succeeds once one exists; `resolved`
blocked while the linked case is non-terminal; the linked `vls.case`
walked through VLS's real JP branch (filed -> served -> answered ->
[discovery trap fires correctly, rejecting a direct jump to
discovery_open] -> motion_limited_discovery_filed -> discovery_open ->
settled) using nothing but `vls.case_event` inserts — proving this is real
reuse of VLS's proven logic, not a reimplementation; `resolved` then
succeeds; and the old temporary `needs_served -> resolved` escape hatch
from migration 003 is confirmed closed.

**Grants added:** `elektrica_app` now has `USAGE` on schema `vls` and
`SELECT, INSERT` on `vls.case` / `vls.case_event` (plus their sequences)
— scoped narrowly to what driving Elektrica's own litigation through
VLS's engine requires. Nothing here grants elektrica_app visibility into
`vls.client` or any VLS-client-specific data; RLS on `platform.person` is
untouched.

**Still staging-only:** inherits `elektrica.rental`'s staging-only status
mechanically (placeholder vehicle/rental fields, pending real exports) —
the JP-wiring piece itself has no placeholder fields and would be
promotion-ready on its own once its dependencies are.

---

## URGENT — Two unreconciled build tracks now BOTH on origin/main (process error, my fault)

**What happened:** A different session of this same bot profile received a
separate "Phase 1" instruction from Jed and built a FastAPI + SQLite CRUD
app (`app/`) against the *original* simpler ADR draft
(`docs/original-bot-plan.md` — Vehicle/Customer/Lease/Payment/Incident/
ComplianceItem, integer PKs, no Neon/Postgres). That session correctly
recognized this conflicts with the `elektrica.*` Postgres v2 schema I've
been building, flagged it prominently in README.md and
`workspace/LOG.md`, and **deliberately did not push commit `4a46d40` to
origin** — holding it for Jed's explicit review per the standing
external-facing rule, exactly as it should have.

**I broke that hold by accident.** When I committed and pushed migration
007 tonight, I never checked `git log`/`git status` for pre-existing local
commits ahead of what I expected before pushing. `4a46d40` was sitting
unpushed on local `main`, ahead of my own last-known-pushed commit
(`d6e2324`). My `git push origin main` pushed both `4a46d40` and my own
`35aacb5` together — git pushes everything on the branch, not just what I
personally just committed. Confirmed via `git log origin/main`: `4a46d40`
is now live on `github.com/Jethreo83/elektrica-dashboard`.

**Why this matters, not just as a process slip:** the other session's own
commit message and README section are correct that this is a real
architecture fork needing Jed's decision, not something either of us
should resolve solo — and now it's live on origin without that review
having happened first, which is exactly backwards from what both sessions
intended.

**Impact assessment (what did NOT happen, to be precise about severity):**
no VLS/Jocasta data touched, no Neon/Postgres connection ever opened by
the SQLite app, no external deployment, no data exposed beyond the
GitHub repo itself. This is a premature-push-of-reviewable-code issue,
not a data/security incident.

**What I'm doing:** not attempting to force-push/revert origin myself —
rewriting shared git history unilaterally is its own risk and doesn't
undo the fact the push happened. Escalating instead: this needs Jed's
decision on the other session's own open questions (which ADR is
authoritative for the dashboard app — the SQLite Phase 1 scaffold or the
Postgres v2 claim-generation schema; whether `4a46d40` being live is fine
to leave as-is or needs history cleanup) before I touch anything else in
this repo, including the still-queued document-generator placement
question.

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
