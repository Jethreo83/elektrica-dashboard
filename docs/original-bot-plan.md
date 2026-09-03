ADR-001: Elektrica Rentals Dashboard — Initial Architecture & Scope
Status: DRAFT — pending Jed's review/sign-off. Nothing in this document has been built.
Date: 2026-09-03
Owner: Elektrica dashboard agent (elektrica-dashboard profile)

1. CONTEXT

Elektrica Rentals (Elektrica Holdings LLC dba Elektrica Rentals) leases/subleases
EVs (Tesla Model 3s and similar) to customers. Based on documents already on file
(bills of sale, master lease agreement drafts, sublease agreements, HV battery
warranty language, DV assessments, a demand package to State Farm, a warranty
overlap report, a dealer pre-licensing certificate), the business appears to
combine three operational threads today, likely handled ad hoc across email/PDF/
Word docs:

  a. Fleet acquisition & ownership (bills of sale, VINs, titles, dealer licensing)
  b. Leasing/subleasing operations (lease agreements, customers, payments, terms)
  c. Incident/claims handling (accidents, diminished-value assessments, insurance
     demand packages, warranty-overlap disputes with third parties e.g. Mobilitas)

This is being modeled on the same operational pattern as Jed's other dashboard
(Jocasta/VLS Command Center) — a dashboard app + automations + integrations —
but is a fully separate product, repo, and data store. No VLS/Jocasta data,
code, or client matters are referenced anywhere in this plan or its build.

Note: given (c) above overlaps with insurance/legal claims work, and Elektrica
shares a memory space with the complete-collision bot, there's a real chance
some incident/claims tooling could be shared or cross-referenced between the
two businesses. Flagged as an open question below rather than assumed.

2. WHAT THE DASHBOARD NEEDS TO DO (v1 scope)

  Fleet management
    - Track vehicles: VIN, make/model/year, acquisition (bill of sale, cost,
      date), title status, current assignment (leased/subleased/available/
      out-of-service), odometer, HV battery warranty terms & expiration.
    - Surface upcoming warranty expirations and service/registration due dates.

  Lease / customer management
    - Track customers (lessees): contact info, lease start/end, vehicle
      assigned, lease terms/version (e.g. Master Vehicle Lease Agreement
      v1.1 vs v1.2), deposit, monthly rate.
    - Track sublease relationships separately from primary customer leases
      (Elektrica Holdings subleases are a distinct structure per docs on file).
    - Document status: signed/unsigned, which template version applied.

  Financials (lightweight, v1)
    - Payment schedule and status per lease (paid/late/outstanding).
    - Basic revenue/utilization view (vehicles earning vs. idle).
    - Full accounting stays in whatever system Jed already uses (see open Qs) —
      this dashboard is not a books-of-record replacement in v1.

  Incidents & claims
    - Log incidents per vehicle/customer: date, description, at-fault status,
      related documents (DV assessment, demand letter, warranty overlap report).
    - Track claim status/stage (filed, in negotiation, settled) and counterparty
      (e.g. insurer, other party's fleet company).
    - This is recordkeeping/status-tracking only — the dashboard does NOT draft
      or send legal correspondence; that stays a human (and possibly VLS-side,
      external to this bot) task.

  Compliance
    - Dealer licensing status/expiration (Texas Dealer Pre-License cert on file).
    - Renewal reminders.

  Reporting / home view
    - At-a-glance: fleet count & status, leases expiring soon, payments overdue,
      open incidents, upcoming compliance deadlines.

Explicitly OUT of v1 scope unless Jed asks: e-signature workflow automation,
telematics/GPS integration, full accounting/GL, customer self-service portal,
automated legal document generation.

3. PROPOSED ARCHITECTURE

Mirroring the Jocasta pattern at a smaller scale:

  - Dashboard app: single web app (server-rendered or lightweight SPA) with a
    small backend API. Suggest a boring, low-ops stack Jed's other dashboards
    already use if there's a preference (ask — see open questions); default
    assumption absent guidance: Python (FastAPI) backend + SQLite for v1,
    simple HTML/HTMX or a small React frontend.
  - Single-tenant, runs locally/self-hosted first (e.g. on the same box as this
    Hermes profile, or a small VPS) — NOT exposed externally until Jed
    explicitly approves a deployment target.
  - Automations layer: scheduled jobs (via Hermes cron in this profile, or a
    simple task scheduler in-app) for reminder generation — warranty expiring,
    lease expiring, payment overdue, compliance renewal.
  - File/document storage: local filesystem or a synced folder (e.g. the
    existing OneDrive/Downloads pattern) referenced by path/link from records;
    v1 does not need a dedicated document management system.
  - Auth: single-user (Jed) or small internal team; no public accounts in v1.

4. DATA MODEL (v1 draft)

  Vehicle
    id, vin, make, model, year, acquisition_date, acquisition_cost,
    title_status, status (available/leased/subleased/service/sold),
    odometer, hv_battery_warranty_expiration, notes

  Customer
    id, name, contact_email, contact_phone, type (lessee/sublessee),
    notes

  Lease
    id, vehicle_id, customer_id, type (primary_lease/sublease),
    agreement_template_version, start_date, end_date, monthly_rate,
    deposit_amount, status (active/ended/terminated), signed_doc_path

  Payment
    id, lease_id, due_date, amount_due, amount_paid, paid_date, status

  Incident
    id, vehicle_id, customer_id (nullable), date, description,
    at_fault (self/other/unknown), status (open/in_negotiation/settled/closed),
    counterparty_name, related_doc_paths (list)

  ComplianceItem
    id, type (dealer_license/registration/insurance/other), description,
    expiration_date, status, related_doc_path

This is a starting draft, not final — will refine once Jed confirms scope
and reviews existing documents more closely (bills of sale, lease templates,
sublease agreement) for fields I may be missing.

5. INTEGRATIONS (candidates — none built without approval)

  - E-signature (DocuSign/HelloSign/PandaDoc or similar) — if lease signing
    should be tracked/triggered from the dashboard rather than handled
    externally and just logged.
  - Payments (Stripe/Plaid or existing processor) — if Elektrica wants
    automated payment tracking/reconciliation instead of manual entry.
  - Accounting (QuickBooks or whatever Jed uses) — read-only sync for
    revenue/expense reporting, if desired.
  - Messaging (email/SMS/Telegram via Hermes gateway) — for internal reminder
    notifications (lease expiring, payment overdue, warranty ending).
  - Possible shared touchpoint with complete-collision bot for cross-business
    customers/incidents — TBD, see open questions.

6. OPEN QUESTIONS FOR JED

  1. Tech stack preference — does Jed have an existing stack/hosting pattern
     from Jocasta or elsewhere he wants mirrored, or is a fresh choice fine?
  2. Where should this run day one — local machine only, or does Jed want a
     hosting target in mind now (even if not deployed yet)?
  3. What system (if any) currently holds accounting/books for Elektrica —
     integrate/read from it, or keep finances basic in-dashboard for now?
  4. Should incident/claims tracking here ever link to work the
     complete-collision bot does, given shared customers? If so, what's
     shared vs. kept separate?
  5. Single-user (Jed only) or will other staff need dashboard access/logins
     in v1?
  6. E-signature and payment processing — build integrations now, later, or
     keep fully manual/external indefinitely?
  7. Is there an existing fleet size/growth expectation that should inform
     whether SQLite-for-v1 is sufficient or a heavier DB is worth it upfront?
  8. Any existing repo, doc, or spreadsheet Jed already uses for fleet/lease
     tracking that this should import from or replace?

7. NEXT STEPS

  - Hold for Jed's review/edits on this ADR.
  - On sign-off: confirm stack choice, set up repo structure, implement data
    model + basic CRUD dashboard for Vehicles/Customers/Leases first (highest
    daily-use value), then Payments/Incidents/Compliance views.
  - No deployment or external exposure without explicit approval, per standing
    rule.
