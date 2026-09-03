# ELEKTRICA HANDOFF — 2026-09-03

**From:** Claude (design review)
**For:** Jocasta (build), Kay (operations / data export), Jed Grant (decisions)
**Companion to:** `VLS_DASHBOARD_HANDOFF_2026-09-02.md` — same format, same conventions. Read that one first for ADR-001, ADR-002, the VLS schema status, the verification standard, and the agent-lane rules. Nothing there is repeated here except where Elektrica changes it.

**Source of truth for this document:** Jed's spoken description on 2026-09-02/03. Claude has seen **no** Elektrica code, screenshots, or Sheets. Every column, state name, and rule below is a design proposal derived from that interview, not an observation of the current system. Where the current system disagrees with this document, *the current system is the fact and this document is the proposal* — flag it, don't silently pick one.

Contains no secrets and no client names.

---

## 0. Decisions locked in this session

| # | Decision | Status |
|---|---|---|
| E-1 | Elektrica is **three products under one roof**: Rentals, Consulting, Sales. Each is its own domain with its own tables and state machine. | Approved |
| E-2 | **One platform experience, several engines.** Shared shell (login, navigation, design, unified person view) over separately deployable domain services. This is ADR-001 restated; it now covers VLS, Rentals, Consulting, and Sales-when-ready. | Approved |
| E-3 | Telematics, geofence, toll reconciliation and inbound-email matching stay **bot-side** (a dedicated Hermes-spawned rental-operations bot). The app records the bot's proposals; Jed confirms. The bot never reaches into app internals. | Approved |
| E-4 | The signed **assignment agreement is stored per rental** and is retrievable — it is the standing document if a JP defendant challenges Elektrica's right to sue. | Approved (Claude's recommendation; Jed did not object) |
| E-5 | **Consulting never appraises a vehicle Elektrica has a financial interest in.** Enforced in software, not by policy. | Approved — integrity firewall |
| E-6 | Consulting is standalone with one exit ramp: client pays for the report, **or** elects referral to VLS on a 33% contingency (DV only; VLS generally does not take total-loss). | Approved |
| E-7 | Elektrica is the **book of record for payments** for now. Design the payment table so a QuickBooks sync can be added additively later. | Approved |
| E-8 | **Sales is a documented future domain, not a build target.** Dealer license pending; outside software likely. Gets its own design session when the license lands. | Approved |
| E-9 | Years of historical insurer-payment data must be **imported, normalised, verified by aggregate, then frozen read-only.** | Approved |
| E-10 | The **document generator is a shared platform primitive.** It has been described four separate times today (rental demand, appraisal report, customer comms, DMV forms). Build it once. | Approved |

---

## 1. Shared primitives — what Elektrica takes from `_shared` / `platform`

Per ADR-001, `_shared` is extracted only when a second consumer exists. Elektrica **is** the second consumer for every item below, so these are now justified to extract — but only *after* the VLS version is working, and only the parts both actually use.

### 1.1 `platform.person` (ADR-002)
Unchanged. Elektrica owns `elektrica.renter` and `elektrica.consulting_client`, each keyed by `person_id`, each under RLS. The registry does not record which businesses a person touches.

**New cross-business event this introduces:** a Consulting client who elects VLS referral becomes a `vls.client` for the same `person_id`. This is the first designed identity-resolution case where the *same person* is deliberately created in a second app by a handoff rather than discovered by matching. Log it as a merge-free link (same `person_id`, two party rows), not a merge.

### 1.2 JP court state machine
The VLS court engine has a JP branch and a District branch. **Elektrica Rentals uses the JP branch only** (pro se, in Elektrica's own name, on assigned property-damage rights). Including the trap: *after the defendant answers, a motion for limited discovery is required before discovery can proceed.* Do not fork this logic. If the VLS engine is not yet extractable, Elektrica should *import* it as a dependency, not copy it.

### 1.3 Document generator
Contract: `(template_id, template_version, merge_data, attachments[]) → PDF + generation_log_row`. Requirements common to every caller:
- Templates are versioned; a generated document records the template version used.
- Attachments are embedded in order (final bill, image report, comps, W-9, assignment, receipts…).
- Every generation writes a log row: who, when, which template version, which source record, output hash.
- Outbound delivery (fax via RingCentral, email draft, SMS via RingCentral) is a **separate** step with its own log row, so "generated but never sent" is visible.

Callers today: rental demand (3 variants), rental agreement, return agreement, DV request letter, DV appraisal report, total-loss appraisal report, DMV title forms (future), lease-to-own contract (future).

### 1.4 Insurance carrier database
Canonical carrier record: name, aliases, fax, email, phone, claims-mailing conventions. **Shared** between VLS and Elektrica Rentals. Adjuster records hang off carriers (see §2.8).

### 1.5 Communication timeline
RingCentral call transcripts, outbound email/SMS, inbound email — all attached to a domain record (rental, VLS case, consulting order) with provenance. Same engine as the VLS "email as source of truth" idea. Inbound insurer email matched by claim number is a **proposal** the human confirms (see §2.6).

### 1.6 Payments
`payment` table with `source` (authorize_net | check | insurer_eft | manual), external transaction id, amount, timestamp, and a nullable `accounting_sync_ref` reserved for QuickBooks. Authorize.net integration is a shared adapter; Rentals uses one-off charges, Sales (future) uses recurring.

### 1.7 Bot interface
Bots write to the app **only** through a scoped API key against explicitly proposal-shaped endpoints (`POST /api/elektrica/rentals/{id}/proposals`). Proposals carry `source_system`, `observed_at`, `evidence` (e.g. geofence alert message id, TollOptics record id). A proposal is never auto-applied to a legal-record field. This is the same discipline that keeps Jocasta out of production and the same fix the VLS security audit demanded: **no bypass allowlist, no localhost trust, API key or nothing.**

---

## 2. Elektrica Rentals

### 2.1 What it is
Not a booking system. A **claim-generation machine.** Elektrica rents a vehicle to a claimant (usually while their car is at a body shop), the rental agreement assigns the renter's property-damage rental claim to Elektrica, and Elektrica then demands payment from the at-fault carrier — and sues in JP court in its own name if unpaid.

### 2.2 The flow (as Jed described it)
1. Renter completes a **JotForm** at the body shop (link/QR): identity, address, insurance, who is billed. Auto-creates a Drive folder.
2. Vehicle goes out. The rental-operations bot tracks it (Bouncie login, standard-fleet live position, geofence email alerts on some vehicles).
3. Vehicle returns to the geofence. A second form fires / the bot detects it and proposes completion. Bot pulls tolls from **TollOptics** (API) and independently logs in to confirm dates and that the toll record is closed.
4. Jed opens the rental, confirms dates, tolls, insurance, self-pay/payment-link status.
5. Market-rate scanner (Kayak/online API) pulls the average rate **for that vehicle for those exact dates** — Austin rates swing widely with events; market rate, not a fixed rate, is what the carrier owes a claimant.
6. Rental receipt generated → Drive → **demand PDF** bundling receipt + market comparables + W-9 (+ assignment on request), faxed via RingCentral or dropped as an email draft, addressed from the carrier database. Minutes end to end.
7. Negotiation, payment, or JP litigation owned by Elektrica.

### 2.3 Entities (proposed — validate against the real Sheets before writing migrations)

- **`vehicle`** — VIN, class (EV / gas / SUV / truck / …), status (available | out | maintenance | retired), tracking system(s) installed (bouncie | standard_fleet | geofence_email | none), current known position (bot-maintained, non-legal).
- **`renter`** — party row keyed to `platform.person`.
- **`rental`** — the spine. vehicle, renter, body_shop, rental_type, billed_to (carrier | self | body_shop), start/end (confirmed), **`assignment_document_id`** (required before a demand can be generated), Drive folder ref, JotForm submission ref.
- **`rental_proposal`** — bot-written. rental_id, kind (departure | return | dates | tolls), proposed values, source_system, evidence, observed_at, status (pending | accepted | rejected), decided_by, decided_at.
- **`toll`** — per rental, TollOptics record id, amount, date, confirmed flag.
- **`demand`** — rental_id, **`demand_type` (primary_insurer | uim | balance_to_renter)**, recipient (carrier + adjuster, or renter), amount, generated_document_id, sent_via, sent_at, status. A rental has many demands; each has its own lifecycle. The shortfall from a resolved earlier demand pre-fills the next.
- **`comparable_set`** — frozen per demand. scan source, scan timestamp, vehicle class, date range, each comparable (vendor, vehicle, daily rate), computed average. **Immutable once the demand is generated.**
- **`document`** — generated and uploaded documents with hashes (receipt, demand, assignment, agreement, return agreement, DV request).
- **`outbound_log`** — every send: document, channel (fax | email | sms), recipient, timestamp, delivery confirmation ref.
- **`communication`** — call transcript / email / SMS attached to rental with direction and provenance (see §2.6).
- **`payment`** — see §1.6.
- **`case_event`** — append-only, same shape as VLS; state derived from events.
- **`insurer_payment`** — see §2.8.
- **`adjuster`** — see §2.8.

### 2.4 State machine (Jed's list, mapped)
```
active → finished → needs_demand → (needs_more_information ⇄) → demand_sent
→ negotiating → no_offer → needs_lawsuit → needs_served → [JP engine:
answered → motion_limited_discovery_filed → discovery → mediation …] → finished
```
- `finished` (rental) and `finished` (matter) are different states; rename the terminal one `resolved` to avoid confusion.
- `needs_more_information` is where source disagreement lands (Bouncie says Tuesday, geofence says Wednesday, TollOptics not closed). Never resolve it silently.
- Aging surfaces itself: a demand at 45 days with no offer, a `needs_lawsuit` rental approaching a limitations problem. Silence is the signal — same as VLS treatment-gap logic.
- Every state change is a `case_event` with `source_ref`.

### 2.5 Fleet board (must survive the rebuild unchanged in function)
Two halves, one screen:
- **Out:** each vehicle with body shop / rental type / renter name beside it, plus (new) bot-reported live status: out, due back, currently near lot.
- **Available:** grouped by class.
This is Jed's daily operational truth. Keep it as the Rentals landing screen.

### 2.6 Communication timeline & auto-matching
- RingCentral: when a call involves a renter's number, transcript attaches to the rental.
- Outbound email/SMS from the app attaches automatically (it already knows the rental).
- Inbound carrier email is matched by **claim number in subject/body** → attached as a *proposal* pending confirmation. Wrong-claim attachment is worse than no attachment; this timeline may become evidence.

### 2.7 One-button comms
"Generate document → choose channel" action on the rental: rental agreement, return agreement, DV request, payment link. Text or email via RingCentral. All go through §1.3 and §2.3 `outbound_log`.

### 2.8 Insurer-payment tracker & adjuster intelligence — **strategic asset**
Jed has years of data on what carriers actually paid at market rate. When an adjuster offers $35–40/day, the exhibit is: *this same carrier paid market rate on N prior claims.*

- **`insurer_payment`**: carrier_id, adjuster_id (nullable), claim ref, vehicle class, rental dates, market rate at the time, amount demanded, amount paid, days, resolved_at, source (system | legacy_import), source_ref, `frozen` flag.
- Populates **automatically** from every resolved demand. Grows without effort.
- First-class query/exhibit: filter by carrier, date range, vehicle class → exportable table for a demand or a JP filing.
- **`adjuster`**: carrier_id, name, contact, notes; outcomes roll up (settles at market / lowballs / forces suit). Shapes how a file is worked the day it lands.

### 2.9 Historical import — the plan
1. **Kay exports** the current payment/market-rate Sheet(s) to CSV. Claude/Jocasta look at the *real* columns before finalising `insurer_payment`. Schema fits reality plus future needs — not the reverse.
2. **Normalise, don't copy.** Carrier names collapse to canonical `insurance_carrier` records; vehicle classes map to the standard set; dates parsed to one format. Kay proposes the mapping; Jed reviews the ambiguous cases; then it runs.
3. **Link, don't just clean.** Rows that cannot be linked to a carrier or class are not failures — they are a to-do list ("30 rows reference carriers I couldn't match"). Resolving them enriches the carrier database.
4. **Provenance on every row:** `source = legacy_import`, `imported_at`, pointer to original Sheet row.
5. **Verify by aggregate**, not by assumption: row count in = out; per-carrier totals and averages match old vs new. Mismatch = stop.
6. **Freeze.** Verified historical rows become read-only. New settlements append. The past is immutable — that is what makes it credible as an exhibit.
7. **Sequencing:** after `insurer_payment` exists and is verified, before it is needed under a deadline. Not as urgent as OAuth or the auth patch; not last either.

**Open:** does the historical data already record the adjuster? If yes, carry it through — adjuster intelligence starts with years of depth.

---

## 3. Elektrica Consulting

### 3.1 What it is
A **professional appraisal practice**, sold as a product: diminished-value appraisal **$400**, total-loss appraisal **$700**. Certified reports carrying Jed's credentials, licence, methodology, resume. Consulting **never sends a demand.**

### 3.2 Integrity firewall (E-5) — enforce in schema
Consulting must be structurally unable to open an appraisal on a vehicle tied to an Elektrica rental claim (or any matter where Elektrica stands to benefit). Implement as a check at order creation against `elektrica.rental.vehicle` / renter identity, with an explicit blocked-reason surfaced, not a silent failure. This rule protects the credibility of every report Consulting has ever issued.

### 3.3 One engine, two configurations
Both appraisal types are the same pipeline: **import & decode → gather valuation inputs → confirmed grade → assemble certified PDF.** Build it as a pipeline with pluggable valuation sources.

| Step | Diminished value | Total loss |
|---|---|---|
| Inputs | Final bill PDF + image report PDF (drag-drop); cover photo; Jed's pre/post-loss opinion | Final bill PDF (optional decode) |
| Decode | VIN decoder from final bill auto-fills vehicle/repair data | Same |
| Grade | AI scans bill for structural damage, proposes **1–5 grade (Mannheim-style)**; **Jed confirms/corrects** | As applicable |
| Valuation | **Black Book API**: accident date, repair-complete date, location, pre-grade, post-grade → wholesale / trade / private-party / retail / average. Optional **Mannheim** auction data by grade. | **Manually sourced comps within 200-mile radius**, uploaded |
| History | **VIN Audit** report (in-house CARFAX equivalent) | Same |
| Headline value | Diminished value. Report uses the **average**; litigation falls back on **wholesale** (the only provable transaction data — the rest are listing values) | **Actual cash value** |
| Output | ~50-page certified appraisal: methodology, credentials, both source docs embedded | Certified appraisal with vehicle photos and comps embedded |

### 3.4 Disciplines that matter more here (Jed's name and licence are on the output)
- **Store both grades**: `ai_grade` and `confirmed_grade`, with who confirmed and when. The trail must show a licensed appraiser made the call.
- **Freeze the valuation snapshot per report**: raw Black Book response, Mannheim data, uploaded comps, VIN Audit — captured immutably at generation. A certified appraisal must be reproducible years later.
- **Version credentials and methodology.** A report records the methodology/credential version in force on its issue date.
- Report generation goes through §1.3 with a distinct template family.

### 3.5 Order flow and the VLS exit ramp (E-6)
```
order_received → inputs_uploaded → graded (ai) → grade_confirmed → valued
→ report_generated → [fork]
     ├─ paid ($400 DV / $700 TL) → delivered → closed
     └─ referred_to_vls (DV only, typically) → VLS opens a matter; 33% contingency on recovery
```
- The fork is an **explicit, logged decision** on the order (`disposition = paid | referred_to_vls`). Money works completely differently on each branch; conversion rate between them is a business metric worth having.
- On referral: same `person_id` becomes a `vls.client`; the appraisal crosses as an **exhibit document** (hash-referenced, not copied into VLS's domain tables); VLS creates its own engagement and fee terms. Consulting does not reach into VLS. This is the ADR-001 process boundary doing its job.
- Total loss: VLS generally does not take these; the client buys the report.

### 3.6 Entities (proposed)
`consulting_client` (→ person), `appraisal_order` (type, disposition, price, status), `appraisal_input_document`, `vehicle_decode`, `grade` (ai / confirmed), `valuation_snapshot` (frozen JSON + normalised columns), `comparable` (TL), `appraisal_report` (document ref, methodology_version, credential_version), `payment`, `vls_referral` (order_id, vls matter ref, created_at).

---

## 4. Elektrica Sales — FUTURE DOMAIN, do not build yet (E-8)

**Why not now:** dealer licence pending; outside software likely for parts of it; still forming. Everything else in this document Jed has *operated*; Sales he has *planned*. Speccing lease-to-own before the licence and the software choices are known is designing on sand.

**What it is:** buy salvage at auction → repair in Jed's own body shop → resell, or **lease with option to buy** for no/bad-credit customers (maximise money down, retain title, remote-access enabled vehicle; non-payment → cut access → easy repo; buyout ~10% of value at term end).

**Three separable pieces, for the architecture to leave room for:**
1. **Inventory & reconditioning tracking** — vehicle state machine: acquired → in_repair → needs_title | needs_rebuilt_title → titled → for_sale | leased | sold. Close cousin of the fleet board.
2. **DMV form generator** — pick form type (new title / rebuilt title / …), fill blanks, attach rebuild receipts and work breakdown, one button → print-ready PDF. **This is §1.3, not a new tool.**
3. **Lease-to-own engine** — inventory tied to a deal; payment calculator (down, rate, term, buyout) → filled contract PDF (§1.3) → e-sign; **Authorize.net recurring** with customer payment options; payment status wired to remote-access/repo lever.

**Flags for that future session:** lending-adjacent compliance (Texas lease/finance disclosures, repossession rules, remote-disable notice requirements) — get counsel input before building #3. Also decide what outside software owns what before any schema is written.

Reserve `elektrica_sales` as a schema name. Nothing else.

---

## 5. Cross-business handoffs — the complete list

| From → To | What crosses | What does NOT cross |
|---|---|---|
| Consulting → VLS | `person_id`; appraisal report as exhibit (hash ref); referral record | Order lifecycle, pricing, grading data |
| Rentals ↔ VLS | Nothing by design. Rental claims are Elektrica's own (assigned). | A VLS client who also rents is the same `person_id` under RLS; no domain data flows |
| Rentals → Consulting | **Blocked** (E-5 firewall) | — |
| Any → platform | Identity, carrier database, document generation log, comms timeline | Domain lifecycle (hinge condition from ADR-001) |

Hinge-condition test still applies: if a Rentals or Consulting change forces a `platform` migration, the boundary is wrong.

---

## 6. Build order (proposal)

1. Finish VLS schema items already approved (rename, RLS 004, permanent harness, fixtures — **blocked on the fee-shifting question**).
2. Extract `_shared` document generator and JP engine only once VLS versions are proven.
3. Rentals schema + fixtures + verify suite, in this order: vehicle/rental/assignment → proposals + bot API → demand + frozen comps → outbound log → comms → payments → insurer_payment + adjuster.
4. Historical insurer-payment import (§2.9).
5. Consulting schema + firewall check + valuation snapshot + report pipeline.
6. Shell: unified login/nav, person view across VLS/Rentals/Consulting.
7. Sales: separate session, later.

Verification standard is unchanged from the VLS handoff: behaviour proven against a live database, self-authored tests flagged as unable to catch domain misunderstandings, Jed checks the Texas-practice parts.

---

## 7. Open questions (Jed to answer)

1. **Fee-shifting on third-party VLS cases** — still blocks VLS fixtures. (Carried over.)
2. Does the historical insurer-payment data record the **adjuster**?
3. Which Sheet(s)/tabs hold the payment history, the carrier database, and the fleet list? (Kay: include in DATABASE_MAP.)
4. Is the **assignment** currently a distinct signed document, or a clause inside the rental agreement? Affects whether `assignment_document_id` points at the agreement or a separate file.
5. UIM demands: is the trigger "primary paid partial and hit limits" only, or also "primary denied"?
6. Consulting: is there ever a case where Jed *wants* to appraise a vehicle with an Elektrica connection and disclose the interest instead of being blocked? (Default: hard block.)
7. Authorize.net: single merchant account across Rentals and Sales, or separate?
8. For the payment-link / self-pay path, who is the payer of record — renter or body shop?

---

*End of handoff. Update `journal.txt` in the transcripts directory with this file's name and md5 once uploaded to Drive.*

---

## 8. Corrections from Kay's static analysis (CLAUDE_TO_KAY_006, 2026-09-03)

Source: `INTEGRATION_INVENTORY.md` and `DATABASE_MAP_elektrica_SKELETON.md`, derived from 111 Python files in the repo, **no Sheets access**. Row counts, headers, and source-of-truth classification remain UNKNOWN until Elektrica OAuth is restored on the cloud host.

| Handoff assumption | What the code shows | Effect on design |
|---|---|---|
| Rental Management is the Elektrica data source | Two primary sheets: **Fleet** (`1wK_Zt…`, 36 refs, ~53 per-vehicle tabs + `Fleet Info`) and **Rental Management** (`1Rg5aJ…`, 33 refs; tabs `Current Rentals`, `Finished Rentals`, `Settings`). A third, `1ezyp1…` (8 refs), is unidentified. | Fleet migration is a separate legacy source with a per-vehicle-tab shape. §2.9-style normalisation applies to it too. |
| `vehicle.class` and `tracking_system` are stored | Not evidenced in source. May be front-end-computed or absent. | **Jed to confirm.** Do not assume these columns exist in the export. |
| A carrier contact database exists | **Not located.** Only `pal_insurance_companies` (Austin Legal endpoint). | **Jed to answer:** where does the fax number come from today? Either point §1.4 at the PAL data as a legacy source, or §1.4 is net-new build. |
| Demands have a log | Demand state is `demand_details.json` + `demand_scanner_state.json` on the mini, plus rental rows. | Demand history migrates from local JSON, not a sheet. |
| Bouncie / standard-fleet / geofence / Mannheim integrations exist | **Absent.** (A Standard Fleet mileage updater is claimed in MEMORY.md but not in the repo.) | Consistent with E-3: these are the future bot's job. Nothing to migrate; clean start. |
| One DV generator | **Six variants** coexist (`dv_report*.py`) plus `dv_engine.py`, `dv_charts.py`. Canonical one unknown. | **Jed to name the live one.** Migrate only that. |
| Distinct total-loss generator | **Not found.** Appears to be a mode inside the DV chain. | **Jed to confirm.** Supports the "one engine, two configurations" design in §3.3, but the current implementation must be located. |
| Kayak scanner as a feed | `rental_rate_scraper.py` scrapes kayak/hertz; write target undetermined. | Bot-side per E-3; its output contract must be pinned when it is restored. |
| Tolls via API | `tolloptics_api.py` confirmed; called from `server.py` on rental close; creds file present. | Matches §2.2. |
| VIN decode | NHTSA vPIC inside `dv_engine.py`, free, no key. | Matches §3.3. |
| Black Book, VIN Audit | `blackbook_api.py`, `_vinaudit_pdf_v2.py` confirmed. | Matches §3.3. |
| Authorize.net | Already inside `server.py`. | §1.6 adapter has a legacy reference implementation. |
| JotForm intake | Webhook `/api/cc/jotform-webhook` live until 2026-09-02; two scanner scripts with **hardcoded API keys**. | Matches §2.2. Keys must move to env/file. |

**Security items surfaced (act before any Elektrica build):**
- OpenAI API key hardcoded in source (likely `dv_engine.py`); repo pushes to GitHub nightly. Check repo visibility; rotate regardless.
- Seven files with literal secrets: three `add_cc_keywords*` (SE Ranking), `collections_jotform_scanner.py`, `pi_intake_import.py`, `dv_engine.py`, `server.py`. 89/111 files load credentials correctly.
- Nothing runs on the cloud host. All scripts and the Flask app remain on the mini; whether LaunchAgents still fire there is unverified (`launchctl list` on the mini).
- RingCentral credential files absent on the cloud host.
- Auth patch from the security audit: written, **still unapplied**.

**Open questions added to §7:**
9. Where does the carrier fax/email come from when a demand is sent today?
10. Which of the six DV generators is canonical?
11. Is total loss a mode inside the DV tool, or a separate tool?
12. Do the Fleet tabs record vehicle class and tracking system, or is that in the front end?
