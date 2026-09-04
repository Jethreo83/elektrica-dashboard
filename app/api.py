"""Phase 1 HTTP API -- thin FastAPI wrapper over app/repository.py, per
ADR-001-elektrica-rentals-v2.md's build-order discipline (data layer
built and verified first; this is the first app-layer surface on top
of it). Modeled directly on Complete Collision's app/api.py (same repo
family, same conventions).

Scope discipline:
  - Every route reads/writes only Elektrica's own `elektrica` schema
    (plus the cross-schema vls.case reads the DB layer already grants
    for JP litigation, migrations/007) via the repository layer that
    already enforces every append-only/immutability/sequence rule.
  - No authentication/session/role enforcement yet -- elektrica.staff_user
    (migrations/011, production) is the real permission gate once a
    caller identity exists to check it against; there is no session/auth
    mechanism in this codebase yet, so wiring a route-guard now would be
    guessing at unbuilt architecture (same reasoning as Collision's
    api.py header).
  - Connection string comes from the environment variable named by
    ELEKTRICA_DB_ENV_VAR (default "DATABASE_URL") -- never hardcoded.
  - Bot-write endpoints (rental_proposal) are the literal handoff §1.7
    contract shape (kind/proposed_values/source_system/evidence/
    observed_at) -- but a real API-key auth layer for bot callers is
    NOT implemented yet (flagged, not silently assumed away -- see
    docs/OVERNIGHT_DECISIONS.md / this file's own module docstring
    section below).

Run locally (never exposed): `uvicorn app.api:app --reload --port 8000`.
Nothing in this repo starts that process automatically; it must be run
by a human on demand until a real deploy decision is made -- same
standing rule as every other draft-and-hold external-facing surface in
this build.

OPEN ITEM (flagged here, not decided): the bot-write proposal endpoint
below has no API-key check. Handoff §1.7 requires "a scoped API key
against explicitly proposal-shaped endpoints ... no bypass allowlist,
no localhost trust, API key or nothing." This endpoint is currently
reachable by anything that can reach the (unexposed, local-only)
process -- fine for this build phase (no deploy exists), NOT fine once
any real deploy is considered. Needs a real auth layer before that day.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import psycopg2.errors
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app import db
from app import repository as repo
from app.models import (
    Demand,
    DemandRecipientType,
    DemandType,
    EventSource,
    Payment,
    PaymentSource,
    ProposalKind,
    ProposalStatus,
    Rental,
    RentalBilledTo,
    RentalProposal,
    RentalState,
    StaffRole,
    Toll,
    Vehicle,
    VehicleClass,
    VehicleStatus,
)

app = FastAPI(
    title="Elektrica Dashboard API (Phase 1, internal/local only)",
    version="0.1.0",
)


def get_db_env_var() -> str:
    return os.environ.get("ELEKTRICA_DB_ENV_VAR", "DATABASE_URL")


def get_db_set_role() -> "str | None":
    """Optional `SET ROLE` target for the app's DB connection, e.g.
    "elektrica_app" -- see app/db.py's get_connection() docstring and
    scripts/_smoke_elektrica_app_role.py for why this exists: the real
    production access pattern is a neondb_owner-class login connection
    string that then SET ROLEs to elektrica_app (elektrica_app itself is
    NOLOGIN), not a plain neondb_owner connection with no role switch.
    Unset by default so existing deploys/tests are unaffected until this
    is explicitly turned on."""
    return os.environ.get("ELEKTRICA_DB_SET_ROLE") or None


def get_cursor():
    """FastAPI dependency yielding a transactional cursor. Overridden in
    tests so no test run ever needs a real database connection."""
    env_var = get_db_env_var()
    with db.cursor(env_var, set_role=get_db_set_role()) as cur:
        yield cur


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VehicleOut(BaseModel):
    id: int
    vin: str
    vehicle_class: Optional[str] = None
    status: str
    tracking_system: Optional[str] = None
    current_position: Optional[dict] = None


class RentalOut(BaseModel):
    id: int
    vehicle_id: int
    renter_id: int
    body_shop: Optional[str] = None
    rental_type: Optional[str] = None
    billed_to: Optional[str] = None
    current_state: str
    vls_case_id: Optional[int] = None
    assignment_document_ref: Optional[str] = None


class RentalIn(BaseModel):
    vehicle_id: int
    renter_id: int
    actor: str
    body_shop: Optional[str] = None
    rental_type: Optional[str] = None
    billed_to: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    assignment_document_ref: Optional[str] = None
    drive_folder_ref: Optional[str] = None
    jotform_submission_ref: Optional[str] = None


class TransitionRequest(BaseModel):
    target_state: str
    actor: str
    source: str = "manual"
    source_ref: Optional[str] = None
    notes: Optional[str] = None


class RentalEventOut(BaseModel):
    id: int
    rental_id: int
    event_type: str
    source: str
    confirmed: bool


class ProposalIn(BaseModel):
    """Bot-write contract shape, handoff §1.7 literal spec."""
    kind: str
    proposed_values: dict
    source_system: str
    observed_at: datetime
    evidence: Optional[dict] = None


class ProposalOut(BaseModel):
    id: int
    rental_id: int
    kind: str
    proposed_values: dict
    source_system: str
    status: str


class ProposalDecisionRequest(BaseModel):
    status: str  # 'accepted' | 'rejected'
    actor: str


class DemandIn(BaseModel):
    demand_type: str
    recipient_type: str
    amount: Decimal
    actor: str
    carrier_name: Optional[str] = None
    adjuster_name: Optional[str] = None
    prior_demand_id: Optional[int] = None


class DemandOut(BaseModel):
    id: int
    rental_id: int
    demand_type: str
    recipient_type: str
    amount: Decimal
    status: str
    sent_via: Optional[str] = None


class MarkSentRequest(BaseModel):
    sent_via: str
    actor: str


class TollIn(BaseModel):
    tolloptics_record_id: str
    amount: Decimal
    toll_date: date
    actor: str
    confirmed: bool = False


class TollOut(BaseModel):
    id: int
    rental_id: int
    tolloptics_record_id: str
    amount: Decimal
    toll_date: date
    confirmed: bool


class PaymentIn(BaseModel):
    source: str
    amount: Decimal
    actor: str
    demand_id: Optional[int] = None
    external_transaction_id: Optional[str] = None
    accounting_sync_ref: Optional[str] = None


class PaymentOut(BaseModel):
    id: int
    rental_id: int
    demand_id: Optional[int] = None
    source: str
    amount: Decimal


class StaffUserOut(BaseModel):
    id: int
    person_id: int
    role: str
    google_email: str
    active: bool
    provisioned_by_staff_user_id: Optional[int] = None


class StaffProvisionRequest(BaseModel):
    """Provisions a staff_user for an ALREADY-EXISTING platform.person.
    Matches app.repository.provision_staff_user_for_existing_person()'s
    scope exactly (same repo family, same convention as Complete
    Collision's own StaffProvisionRequest) -- deliberately does NOT
    create a new platform.person row, since that requires a privileged
    (non-elektrica_app) DB connection per app/db.py's documented role
    gap. Creating new person rows stays an admin-script operation until
    an identity-service integration exists (see docs/BACKLOG.md --
    platform.match_or_create_person() is the real mechanism once this
    route needs to grow that far)."""
    person_id: int
    role: str
    google_email: str
    actor: str
    provisioned_by_staff_user_id: Optional[int] = None


class StaffActiveRequest(BaseModel):
    active: bool
    actor: str


def _vehicle_to_out(v: Vehicle) -> VehicleOut:
    return VehicleOut(
        id=v.id, vin=v.vin,
        vehicle_class=v.vehicle_class.value if v.vehicle_class else None,
        status=v.status.value,
        tracking_system=v.tracking_system.value if v.tracking_system else None,
        current_position=v.current_position,
    )


def _rental_to_out(r: Rental) -> RentalOut:
    return RentalOut(
        id=r.id, vehicle_id=r.vehicle_id, renter_id=r.renter_id,
        body_shop=r.body_shop, rental_type=r.rental_type,
        billed_to=r.billed_to.value if r.billed_to else None,
        current_state=r.current_state.value, vls_case_id=r.vls_case_id,
        assignment_document_ref=r.assignment_document_ref,
    )


def _proposal_to_out(p: RentalProposal) -> ProposalOut:
    return ProposalOut(
        id=p.id, rental_id=p.rental_id, kind=p.kind.value,
        proposed_values=p.proposed_values, source_system=p.source_system,
        status=p.status.value,
    )


def _demand_to_out(d: Demand) -> DemandOut:
    return DemandOut(
        id=d.id, rental_id=d.rental_id, demand_type=d.demand_type.value,
        recipient_type=d.recipient_type.value, amount=d.amount,
        status=d.status.value, sent_via=d.sent_via,
    )


def _toll_to_out(t: Toll) -> TollOut:
    return TollOut(
        id=t.id, rental_id=t.rental_id, tolloptics_record_id=t.tolloptics_record_id,
        amount=t.amount, toll_date=t.toll_date, confirmed=t.confirmed,
    )


def _payment_to_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id, rental_id=p.rental_id, demand_id=p.demand_id,
        source=p.source.value, amount=p.amount,
    )


def _staff_to_out(s) -> StaffUserOut:
    return StaffUserOut(
        id=s.id, person_id=s.person_id, role=s.role.value,
        google_email=s.google_email, active=s.active,
        provisioned_by_staff_user_id=s.provisioned_by_staff_user_id,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# --- Fleet board (handoff §2.5: Rentals landing screen) --------------------

@app.get("/fleet/out", response_model=list[VehicleOut])
def fleet_out(cur=Depends(get_cursor)):
    return [_vehicle_to_out(v) for v in repo.list_vehicles_by_status(cur, VehicleStatus.OUT)]


@app.get("/fleet/available", response_model=list[VehicleOut])
def fleet_available(cur=Depends(get_cursor)):
    return [_vehicle_to_out(v) for v in repo.list_vehicles_by_status(cur, VehicleStatus.AVAILABLE)]


# --- Rentals -----------------------------------------------------------------

@app.post("/rentals", response_model=RentalOut)
def create_rental(body: RentalIn, cur=Depends(get_cursor)):
    try:
        billed_to = RentalBilledTo(body.billed_to) if body.billed_to else None
    except ValueError:
        raise HTTPException(status_code=400, detail=f"billed_to={body.billed_to!r} must be one of {[b.value for b in RentalBilledTo]}")
    rental = Rental(
        vehicle_id=body.vehicle_id, renter_id=body.renter_id, body_shop=body.body_shop,
        rental_type=body.rental_type, billed_to=billed_to, start_date=body.start_date,
        end_date=body.end_date, assignment_document_ref=body.assignment_document_ref,
        drive_folder_ref=body.drive_folder_ref, jotform_submission_ref=body.jotform_submission_ref,
    )
    return _rental_to_out(repo.create_rental(cur, rental, body.actor))


@app.get("/rentals/blocked")
def get_blocked_rentals(cur=Depends(get_cursor)):
    """Handoff §2.4's 'silence is the signal' surface. Registered BEFORE
    the /rentals/{rental_id} route below -- FastAPI matches routes in
    registration order, and an int-typed path param does not
    automatically lose to a more specific literal segment defined
    later, so 'blocked' would otherwise 422 as an unparseable rental_id."""
    return repo.list_blocked_rentals(cur)


@app.get("/rentals/{rental_id}", response_model=RentalOut)
def get_rental(rental_id: int, cur=Depends(get_cursor)):
    rental = repo.get_rental(cur, rental_id)
    if rental is None:
        raise HTTPException(status_code=404, detail=f"No rental with id={rental_id}")
    return _rental_to_out(rental)


@app.get("/rentals/{rental_id}/events", response_model=list[RentalEventOut])
def get_rental_events(rental_id: int, cur=Depends(get_cursor)):
    if repo.get_rental(cur, rental_id) is None:
        raise HTTPException(status_code=404, detail=f"No rental with id={rental_id}")
    return [
        RentalEventOut(id=e.id, rental_id=e.rental_id, event_type=e.event_type.value,
                        source=e.source.value, confirmed=e.confirmed)
        for e in repo.list_rental_events(cur, rental_id)
    ]


@app.post("/rentals/{rental_id}/transition", response_model=RentalOut)
def transition_rental(rental_id: int, body: TransitionRequest, cur=Depends(get_cursor)):
    try:
        target = RentalState(body.target_state)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"target_state={body.target_state!r} must be one of {[s.value for s in RentalState]}")
    try:
        source = EventSource(body.source)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"source={body.source!r} must be one of {[s.value for s in EventSource]}")
    try:
        rental = repo.advance_rental_state(
            cur, rental_id, target, source, body.actor,
            source_ref=body.source_ref, notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # DB-level RAISE EXCEPTION from a trigger (e.g. the litigation gate,
        # migrations/007) surfaces here as a generic psycopg2 error -- still
        # a client-input problem (invalid transition given current DB
        # state), not a server fault, so 400 not 500.
        raise HTTPException(status_code=400, detail=f"Transition rejected by database: {e}")
    return _rental_to_out(rental)


# --- Rental proposals (bot interface, handoff §1.7) -------------------------

@app.post("/rentals/{rental_id}/proposals", response_model=ProposalOut)
def create_proposal(rental_id: int, body: ProposalIn, cur=Depends(get_cursor)):
    if repo.get_rental(cur, rental_id) is None:
        raise HTTPException(status_code=404, detail=f"No rental with id={rental_id}")
    try:
        kind = ProposalKind(body.kind)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"kind={body.kind!r} must be one of {[k.value for k in ProposalKind]}")
    proposal = RentalProposal(
        rental_id=rental_id, kind=kind, proposed_values=body.proposed_values,
        source_system=body.source_system, observed_at=body.observed_at, evidence=body.evidence,
    )
    # source_system doubles as the created_by actor for bot-written rows --
    # matches handoff §1.7's framing that bots write via a scoped API key,
    # not a human actor string.
    return _proposal_to_out(repo.create_rental_proposal(cur, proposal, body.source_system))


@app.get("/proposals/pending", response_model=list[ProposalOut])
def get_pending_proposals(cur=Depends(get_cursor)):
    return [_proposal_to_out(p) for p in repo.list_pending_rental_proposals(cur)]


@app.post("/proposals/{proposal_id}/decision", response_model=ProposalOut)
def decide_proposal(proposal_id: int, body: ProposalDecisionRequest, cur=Depends(get_cursor)):
    try:
        status = ProposalStatus(body.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"status={body.status!r} must be 'accepted' or 'rejected'")
    try:
        decided = repo.decide_rental_proposal(cur, proposal_id, status, body.actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _proposal_to_out(decided)


# --- Demands -----------------------------------------------------------------

@app.post("/rentals/{rental_id}/demands", response_model=DemandOut)
def create_demand(rental_id: int, body: DemandIn, cur=Depends(get_cursor)):
    if repo.get_rental(cur, rental_id) is None:
        raise HTTPException(status_code=404, detail=f"No rental with id={rental_id}")
    try:
        demand_type = DemandType(body.demand_type)
        recipient_type = DemandRecipientType(body.recipient_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        demand = Demand(
            rental_id=rental_id, demand_type=demand_type, recipient_type=recipient_type,
            amount=body.amount, carrier_name=body.carrier_name, adjuster_name=body.adjuster_name,
            prior_demand_id=body.prior_demand_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _demand_to_out(repo.create_demand(cur, demand, body.actor))


@app.post("/demands/{demand_id}/mark-sent", response_model=DemandOut)
def mark_demand_sent(demand_id: int, body: MarkSentRequest, cur=Depends(get_cursor)):
    try:
        demand = repo.mark_demand_sent(cur, demand_id, body.sent_via, body.actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _demand_to_out(demand)


@app.get("/demands/aging")
def get_aging_demands(cur=Depends(get_cursor)):
    """Handoff §2.4: a demand at 45 days with no offer -- silence is the signal."""
    return repo.list_aging_demands(cur)


# --- Tolls -------------------------------------------------------------------

@app.post("/rentals/{rental_id}/tolls", response_model=TollOut)
def create_toll(rental_id: int, body: TollIn, cur=Depends(get_cursor)):
    if repo.get_rental(cur, rental_id) is None:
        raise HTTPException(status_code=404, detail=f"No rental with id={rental_id}")
    toll = Toll(
        rental_id=rental_id, tolloptics_record_id=body.tolloptics_record_id,
        amount=body.amount, toll_date=body.toll_date, confirmed=body.confirmed,
    )
    return _toll_to_out(repo.create_toll(cur, toll, body.actor))


@app.post("/tolls/{toll_id}/confirm", response_model=TollOut)
def confirm_toll(toll_id: int, cur=Depends(get_cursor)):
    try:
        toll = repo.confirm_toll(cur, toll_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _toll_to_out(toll)


@app.get("/rentals/{rental_id}/tolls", response_model=list[TollOut])
def get_tolls(rental_id: int, cur=Depends(get_cursor)):
    if repo.get_rental(cur, rental_id) is None:
        raise HTTPException(status_code=404, detail=f"No rental with id={rental_id}")
    return [_toll_to_out(t) for t in repo.list_tolls_for_rental(cur, rental_id)]


# --- Payments ----------------------------------------------------------------

@app.post("/rentals/{rental_id}/payments", response_model=PaymentOut)
def create_payment(rental_id: int, body: PaymentIn, cur=Depends(get_cursor)):
    if repo.get_rental(cur, rental_id) is None:
        raise HTTPException(status_code=404, detail=f"No rental with id={rental_id}")
    try:
        source = PaymentSource(body.source)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"source={body.source!r} must be one of {[s.value for s in PaymentSource]}")
    try:
        payment = Payment(
            rental_id=rental_id, demand_id=body.demand_id, source=source, amount=body.amount,
            external_transaction_id=body.external_transaction_id,
            accounting_sync_ref=body.accounting_sync_ref,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _payment_to_out(repo.create_payment(cur, payment, body.actor))


@app.get("/rentals/{rental_id}/payments", response_model=list[PaymentOut])
def get_payments(rental_id: int, cur=Depends(get_cursor)):
    if repo.get_rental(cur, rental_id) is None:
        raise HTTPException(status_code=404, detail=f"No rental with id={rental_id}")
    return [_payment_to_out(p) for p in repo.list_payments_for_rental(cur, rental_id)]


@app.get("/vehicles/revenue-summary")
def get_vehicle_revenue_summary(cur=Depends(get_cursor)):
    """Original bot plan's 'basic revenue/utilization view'."""
    return repo.vehicle_revenue_summary(cur)


# --- Compliance --------------------------------------------------------------

@app.get("/compliance/expiring-soon")
def get_compliance_expiring_soon(cur=Depends(get_cursor)):
    return repo.list_compliance_items_expiring_soon(cur)


# --- Staff (staff-provisioning workflow -- closes the BACKLOG.md gap: -----
# repository functions existed since the first app-layer cycle
# (provision_staff_user_for_existing_person, get_staff_user_by_google_email)
# but had no HTTP route; set_staff_user_active() added alongside these
# routes this cycle. Same "requires a privileged connection" caveat as
# Complete Collision's identical route family (elektrica_app has
# SELECT-only on staff_user per migration 011) -- these routes will 500
# under elektrica_app until called through a privileged connection or a
# real identity-service/admin-role boundary exists; not silently worked
# around here, same as app/db.py's own documented role gap.
#
# Deliberately does NOT expose a route that creates a brand-new
# platform.person -- per docs/BACKLOG.md, staff provisioning must go
# through platform.match_or_create_person() (via platform_identity_service)
# for identity resolution, not a bespoke INSERT in this app. This route
# only links an ALREADY-RESOLVED person_id, matching
# provision_staff_user_for_existing_person()'s own scope. -----------------

@app.post("/staff", response_model=StaffUserOut)
def provision_staff(body: StaffProvisionRequest, cur=Depends(get_cursor)):
    try:
        role = StaffRole(body.role)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"role={body.role!r} must be one of {[r.value for r in StaffRole]}",
        )
    try:
        staff = repo.provision_staff_user_for_existing_person(
            cur, body.person_id, role, body.google_email, body.actor,
            provisioned_by_staff_user_id=body.provisioned_by_staff_user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except psycopg2.errors.InsufficientPrivilege:
        # Real, expected outcome under the documented elektrica_app
        # SELECT-only grant on staff_user (migration 011) -- confirmed by
        # actually running this route under ELEKTRICA_DB_SET_ROLE=elektrica_app
        # (2026-09-04 cron cycle) rather than assumed. Surfaced as a clean
        # 403 instead of a bare framework 500, same "client error, not a
        # server bug" discipline every other route in this file already
        # follows for its own known rejection cases.
        raise HTTPException(
            status_code=403,
            detail="Staff provisioning requires a privileged (non-elektrica_app) "
                   "DB connection -- elektrica_app has SELECT-only on staff_user "
                   "by design (migration 011).",
        )
    return _staff_to_out(staff)


@app.get("/staff/{google_email}", response_model=StaffUserOut)
def get_staff(google_email: str, cur=Depends(get_cursor)):
    staff = repo.get_staff_user_by_google_email(cur, google_email)
    if staff is None:
        raise HTTPException(status_code=404, detail=f"No staff_user with google_email={google_email!r}")
    return _staff_to_out(staff)


@app.post("/staff/{google_email}/active", response_model=StaffUserOut)
def set_staff_active(google_email: str, body: StaffActiveRequest, cur=Depends(get_cursor)):
    try:
        staff = repo.set_staff_user_active(cur, google_email, body.active, body.actor)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except psycopg2.errors.InsufficientPrivilege:
        # Same real, verified gap as provision_staff() above -- not a
        # theoretical case, reproduced live via curl this cycle.
        raise HTTPException(
            status_code=403,
            detail="Deactivating/reactivating staff requires a privileged "
                   "(non-elektrica_app) DB connection -- elektrica_app has "
                   "SELECT-only on staff_user by design (migration 011).",
        )
    return _staff_to_out(staff)
