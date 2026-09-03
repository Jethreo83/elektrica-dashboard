# ADR-001: Elektrica Rentals Dashboard — Architecture & Scope (v2)

Status: **APPROVED by Jed, 2026-09-03.** Supersedes the elektrica-dashboard
bot's initial ADR-001, folding in Claude's ELEKTRICA_HANDOFF_2026-09-03.md
and Jed's direct answers (2026-09-03).

## 1. Reconciling three inputs

Three passes exist on this business and they disagree in scope, not in facts:

1. **Claude's handoff** — describes Elektrica Rentals as a claim-generation
   machine: JotForm intake -> bot-tracked rental -> demand generation ->
   JP litigation. Assumes shared platform primitives (person registry,
   JP court engine, document generator) reused from VLS.
2. **elektrica-dashboard bot's own ADR-001** — drafted independently from
   reading Jed's actual documents (bills of sale, lease agreements, DV
   assessments, State Farm demand, warranty-overlap report, dealer license).
   Scoped a *smaller*, more conservative v1: Fleet + Lease/Customer +
   lightweight Financials + Incidents (recordkeeping only) + Compliance.
   Notably: no JotForm/TollOptics/market-rate-scanner pipeline, no demand
   generation, incidents are logged not acted on.
3. **Jed's direct answers** (this session) — confirm concrete facts: DV 2.0
   is canonical, total-loss is a separate tool, a real carrier contact list
   with fax/phone/address/email exists, Fleet tabs do store vehicle
   class/tracking system, and historical insurer-payment data does record
   the adjuster.

**Resolution:** Claude's handoff describes the *target* operational flow
(this is genuinely how the business runs today per Jed's spoken account).
The bot's independent ADR undersold scope because it worked only from
static documents, not the live operational description. Jed's answers close
several of the handoff's explicit unknowns in the more capable direction
(carrier DB exists, adjuster data exists, Fleet fields exist) — meaning less
net-new build than either prior document assumed for those specific pieces.

**This ADR adopts the handoff's operational scope** (claim-generation
machine, not just a fleet/lease tracker) because that is what the business
actually does, informed by the bot's document-grounded data model and Jed's
fact answers. The bot's compliance/lease-management scope is retained as a
real v1 feature, not replaced.

## 2. Confirmed facts (Jed, 2026-09-03) — resolves handoff §7 items 2-4, 6-8 partially

| Handoff open question | Answer |
|---|---|
| Which DV generator is canonical? | **Diminished Value 2.0.** Migrate this one only; the other five are dead code, not alternates to reconcile. |
| Is total-loss a mode or a separate tool? | **Separate tool.** Do not force it into the DV pipeline's shape; give it its own entity/flow (§1.7.3 of the handoff's §3.3 table still holds for the *comparison* structure, but the tool boundary is real). |
| Carrier fax/email source? | **A real insurance contact list exists** — fax, phone, address, email. This is the seed data for `insurance_carrier` (handoff §1.4), not a net-new build. Needs export/inspection before schema, same as any other Sheet-backed store. |
| Fleet tabs store vehicle class/tracking system? | **Yes.** `vehicle.class` and `vehicle.tracking_system` (handoff §2.3) are real columns to migrate, not front-end-computed guesses. |
| Historical insurer-payment data records adjuster? | **Yes.** `insurer_payment` (handoff §2.8) can carry adjuster linkage from day one of the historical import (handoff §2.9) — "adjuster intelligence starts with years of depth" per the handoff's own aspiration, now confirmed possible. |

Still open (not asked this round, carried from handoff §7): UIM demand
trigger condition (item 5), Consulting integrity-firewall override case
(item 6 — default hard block stands until Jed says otherwise), Authorize.net
merchant account scope (item 7), payer of record for self-pay path (item 8).

## 3. Scope (v1) — supersedes the bot's independent draft

Adopting the handoff's Rentals design (§2 of ELEKTRICA_HANDOFF) as the
authoritative v1 scope:

- Fleet (vehicle entity, incl. class + tracking_system fields — confirmed real)
- Rental lifecycle per handoff §2.2-2.4 (JotForm intake through JP litigation)
- Fleet board (handoff §2.5) as the Rentals landing screen
- Communication timeline + inbound-email claim matching (handoff §2.6)
- One-button document generation/comms (handoff §2.7, depends on §1.3 shared
  document generator existing or being stubbed)
- Insurer-payment tracker + adjuster intelligence (handoff §2.8) — now
  buildable with real historical data confirmed to include adjuster
- Historical import (handoff §2.9) — first real migration target once Kay
  exports the Sheet(s)

Bot's original v1 items retained as part of this scope, not dropped:
Lease/Customer management, Compliance (dealer license, renewal reminders),
lightweight Financials view.

Consulting (handoff §3) and Sales (handoff §4, explicitly not-yet-buildable
per E-8) are separate ADRs / later work, not v1.

## 4. Shared primitives dependency

Per handoff §1, Elektrica is the second consumer that justifies extracting
`platform.person`, the JP court state machine, and the document generator
from VLS's codebase into `_shared` — **but only after the VLS versions are
proven** (ADR-001's extraction rule). This means:

- `platform.person` + RLS pattern: already built and verified in VLS
  migration 004. Elektrica's `elektrica.renter` follows the identical
  pattern (own party table, RLS-gated visibility).
- JP court state machine: VLS migration 002's `valid_next_states()` +
  trigger pattern is proven (7 checks passed, including the JP discovery
  trap). Elektrica should **import this as a dependency**, not fork it, per
  handoff §1.2's explicit instruction. Needs a decision on physical
  extraction (shared schema/package) vs. duplicated-but-identical migration
  — flagged as an open implementation question, not a design one.
- Document generator (handoff §1.3): does not yet exist in any form. This
  is new shared infrastructure both VLS and Elektrica need. Recommend
  building it now, scoped to Elektrica's first real caller (rental demand),
  since VLS hasn't needed it yet in the current build order.

## 5. Data model

Adopts handoff §2.3 entities as the v1 schema draft: `vehicle`, `renter`,
`rental`, `rental_proposal`, `toll`, `demand`, `comparable_set`, `document`,
`outbound_log`, `communication`, `payment`, `case_event`, `insurer_payment`,
`adjuster`. Validate field names against the real Sheets/Fleet-tab export
before finalizing migration SQL — Jed has confirmed the *existence* of
`class`/`tracking_system` columns, not their exact naming or enum values.

## 6. Build order

1. Export & inspect: Fleet sheet(s), insurance contact list, historical
   insurer-payment data. (Kay/export step — blocks schema finalization.)
2. `platform.person` extraction decision (shared physical schema vs.
   Elektrica's own copy referencing VLS's `platform` schema directly if
   same database, or a data-sync pattern if separate databases — **open
   question: is Elektrica on the same Postgres project as VLS, or its
   own?**).
3. `elektrica.vehicle`, `elektrica.renter`, `elektrica.rental` core tables.
4. JP court engine dependency wiring.
5. `rental_proposal` + bot API contract (handoff §1.7) — stub only, the
   rental-operations bot itself is future work per handoff §1.7/E-3.
6. `demand`, `comparable_set`, document generator v1 (rental demand only).
7. `outbound_log`, `communication` timeline.
8. `insurer_payment` + `adjuster`, then the historical import (step 1's
   export feeds this).
9. Compliance + lightweight Financials (bot's original v1 items).

## 7. Open questions still blocking full schema

1. ~~Is Elektrica's database the same Postgres project as VLS...~~ **RESOLVED
   2026-09-03: same Neon project (`aged-art-92489373`), separate `elektrica`
   schema.** `platform.person` is referenced directly cross-schema, same
   pattern as `vls.client` in migration 004 — no sync/replication needed.
2. UIM demand trigger: primary paid partial and hit limits, or also primary
   denied? (handoff §7 item 5, unanswered this round)
3. Authorize.net: one merchant account across Rentals/Sales, or separate?
   (handoff §7 item 7)
4. Self-pay path: renter or body shop is payer of record? (handoff §7 item 8)
5. Physical extraction mechanics for the shared JP engine and document
   generator (§4 above) — same-repo shared package vs. duplicated migration
   vs. actual service boundary.

## 8. Explicitly not in this ADR

Consulting (own ADR), Sales (explicitly future per E-8, do not scope yet),
the rental-operations bot itself (separate build, this ADR only stubs the
proposal API contract it will write to).
