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

RESOLVED (2026-09-04, later cron cycle): the bot-write proposal endpoint
now enforces a scoped API key -- see require_bot_api_key() below. Matches
handoff §1.7 literally: "no bypass allowlist, no localhost trust, API key
or nothing." Fails CLOSED, not open: if ELEKTRICA_BOT_API_KEY is unset,
the endpoint returns 503 (disabled) rather than silently accepting any
request. Only the one explicitly bot-shaped endpoint gets this dependency
-- every other route in this file still has no auth, which remains a
separate, larger, standing gap (a real session/staff-auth layer for
human-operated routes) that this change does not claim to resolve.
"""
from __future__ import annotations

import hmac
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import psycopg2.errors
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from app import db
from app import repository as repo
from app.models import (
    Demand,
    DemandRecipientType,
    DemandType,
    Communication,
    CommunicationChannel,
    CommunicationDirection,
    CommunicationMatchStatus,
    Document,
    DocumentTemplateFamily,
    EventSource,
    OutboundChannel,
    OutboundLog,
    Payment,
    PaymentSource,
    ProposalKind,
    ProposalStatus,
    Renter,
    Rental,
    RentalBilledTo,
    RentalProposal,
    RentalState,
    StaffRole,
    Toll,
    Vehicle,
    VehicleClass,
    VehicleStatus,
    TrackingSystem,
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


def get_bot_api_key_env_var() -> str:
    return os.environ.get("ELEKTRICA_BOT_API_KEY_ENV_VAR", "ELEKTRICA_BOT_API_KEY")


def require_bot_api_key(x_api_key: "str | None" = Header(default=None)):
    """Dependency for the ONE bot-write endpoint that handoff §1.7 requires
    to be gated: POST /rentals/{id}/proposals. Deliberately fails CLOSED:

      - No key configured server-side (ELEKTRICA_BOT_API_KEY unset) -> 503.
        This is a "auth not turned on yet" state, not "auth open to all" --
        the endpoint refuses to serve rather than silently accepting every
        caller, so an operator can never mistake "forgot to set the env
        var" for "intentionally open".
      - Caller sent no X-Api-Key header, or the wrong one -> 401.
      - No bypass allowlist, no localhost trust, no dev-mode skip -- every
        request goes through the same check regardless of source, per the
        handoff's literal wording ("API key or nothing").

    Comparison uses hmac.compare_digest (constant-time) rather than `==`
    to avoid a timing side-channel on the key comparison itself.

    This intentionally does NOT become a general auth/session layer for
    the rest of app/api.py's routes (staff/human-operated routes still
    have none) -- that is a bigger, separate decision (real session
    identity tied to elektrica.staff_user) that this task doesn't decide.
    """
    configured = os.environ.get(get_bot_api_key_env_var())
    if not configured:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Bot proposal endpoint disabled: environment variable "
                f"{get_bot_api_key_env_var()!r} is not set. Refusing to "
                "accept unauthenticated bot writes rather than silently "
                "allowing them."
            ),
        )
    if not x_api_key or not hmac.compare_digest(x_api_key, configured):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Api-Key header.")


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


class VehicleIn(BaseModel):
    """Handoff §2.3 vehicle intake shape. class/status/tracking_system
    values are the PLACEHOLDER enum sets from migrations/002 (see
    app/models.py's VehicleClass docstring) -- pending real Fleet export."""
    vin: str
    actor: str
    vehicle_class: Optional[str] = None
    status: str = "available"
    tracking_system: Optional[str] = None
    notes: Optional[str] = None


class VehiclePositionIn(BaseModel):
    """Bot-maintained, non-legal per handoff §2.3 -- a plain column
    write with no event log of its own, distinct from rental state
    transitions."""
    position: dict
    actor: str


class RenterOut(BaseModel):
    id: int
    person_id: int
    jotform_submission_ref: Optional[str] = None
    drive_folder_ref: Optional[str] = None


class RenterIn(BaseModel):
    """Links an ALREADY-EXISTING platform.person as an Elektrica renter --
    see docs/BACKLOG.md's match-before-create discipline. Identity
    resolution (platform.match_or_create_person(), via
    platform_identity_service) happens upstream of this call, not here."""
    person_id: int
    actor: str
    jotform_submission_ref: Optional[str] = None
    drive_folder_ref: Optional[str] = None


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


class DocumentIn(BaseModel):
    """Handoff §1.3 literal contract shape: (template_id, template_version,
    merge_data, attachments[]) -> document. template_version is resolved by
    the caller looking up get_active_document_template() first -- this
    endpoint takes an already-resolved template_id, same discipline as
    StaffProvisionRequest taking an already-resolved person_id."""
    template_id: int
    source_table: str
    source_id: int
    merge_data: dict
    actor: str
    attachments: list = []
    output_ref: Optional[str] = None
    output_hash: Optional[str] = None


class DocumentOut(BaseModel):
    id: int
    template_id: int
    source_table: str
    source_id: int
    output_ref: Optional[str] = None
    output_hash: Optional[str] = None


class OutboundLogIn(BaseModel):
    channel: str
    recipient: str
    actor: str
    delivery_confirmation_ref: Optional[str] = None


class OutboundLogOut(BaseModel):
    id: int
    document_id: int
    channel: str
    recipient: str
    delivery_confirmation_ref: Optional[str] = None


class CommunicationIn(BaseModel):
    """Handoff §1.5/§2.6: outbound rows are confirmed-by-construction
    (the app authored them, it already knows the rental); inbound rows
    default to match_status='proposed' pending human confirmation --
    this schema requires the caller to be explicit about which shape it's
    writing rather than defaulting silently to confirmed for everything."""
    source_table: str
    source_id: int
    direction: str
    channel: str
    occurred_at: datetime
    source_system: str
    actor: str
    from_ref: Optional[str] = None
    to_ref: Optional[str] = None
    subject: Optional[str] = None
    transcript_ref: Optional[str] = None
    proposed: bool = False
    match_evidence: Optional[dict] = None


class CommunicationOut(BaseModel):
    id: int
    source_table: str
    source_id: int
    direction: str
    channel: str
    subject: Optional[str] = None
    match_status: str


class CommunicationDecisionRequest(BaseModel):
    actor: str


def _document_to_out(d: Document) -> DocumentOut:
    return DocumentOut(
        id=d.id, template_id=d.template_id, source_table=d.source_table,
        source_id=d.source_id, output_ref=d.output_ref, output_hash=d.output_hash,
    )


def _outbound_log_to_out(o: OutboundLog) -> OutboundLogOut:
    return OutboundLogOut(
        id=o.id, document_id=o.document_id, channel=o.channel.value,
        recipient=o.recipient, delivery_confirmation_ref=o.delivery_confirmation_ref,
    )


def _communication_to_out(c: Communication) -> CommunicationOut:
    return CommunicationOut(
        id=c.id, source_table=c.source_table, source_id=c.source_id,
        direction=c.direction.value, channel=c.channel.value, subject=c.subject,
        match_status=c.match_status.value,
    )


def _vehicle_to_out(v: Vehicle) -> VehicleOut:
    return VehicleOut(
        id=v.id, vin=v.vin,
        vehicle_class=v.vehicle_class.value if v.vehicle_class else None,
        status=v.status.value,
        tracking_system=v.tracking_system.value if v.tracking_system else None,
        current_position=v.current_position,
    )


def _renter_to_out(r: Renter) -> RenterOut:
    return RenterOut(
        id=r.id, person_id=r.person_id,
        jotform_submission_ref=r.jotform_submission_ref,
        drive_folder_ref=r.drive_folder_ref,
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


# --- Vehicles (handoff §2.3 vehicle intake; elektrica_app has full
# SELECT/INSERT/UPDATE on elektrica.vehicle per migration 002, unlike the
# SELECT-only staff_user gap above -- so these routes are not blocked by
# any DB privilege split.) --------------------------------------------------

@app.post("/vehicles", response_model=VehicleOut)
def create_vehicle(body: VehicleIn, cur=Depends(get_cursor)):
    try:
        status = VehicleStatus(body.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"status={body.status!r} must be one of {[s.value for s in VehicleStatus]}",
        )
    vehicle_class = None
    if body.vehicle_class is not None:
        try:
            vehicle_class = VehicleClass(body.vehicle_class)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"vehicle_class={body.vehicle_class!r} must be one of {[c.value for c in VehicleClass]}",
            )
    tracking_system = None
    if body.tracking_system is not None:
        try:
            tracking_system = TrackingSystem(body.tracking_system)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"tracking_system={body.tracking_system!r} must be one of {[t.value for t in TrackingSystem]}",
            )
    existing = repo.get_vehicle_by_vin(cur, body.vin)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"vin={body.vin!r} already exists as vehicle id={existing.id}")
    vehicle = Vehicle(
        vin=body.vin, vehicle_class=vehicle_class, status=status,
        tracking_system=tracking_system, notes=body.notes,
    )
    return _vehicle_to_out(repo.create_vehicle(cur, vehicle, body.actor))


@app.get("/vehicles/vin/{vin}", response_model=VehicleOut)
def get_vehicle_by_vin(vin: str, cur=Depends(get_cursor)):
    """Registered before /vehicles/{vehicle_id} would collide -- 'vin' is
    a fixed literal segment, not a numeric path param, so there is no
    actual FastAPI route-ordering hazard here (unlike /rentals/blocked
    above), but the lookup semantics differ (VIN string vs. surrogate id)
    so this stays a separate route rather than overloading one."""
    vehicle = repo.get_vehicle_by_vin(cur, vin)
    if vehicle is None:
        raise HTTPException(status_code=404, detail=f"No vehicle with vin={vin!r}")
    return _vehicle_to_out(vehicle)


@app.get("/vehicles/revenue-summary")
def get_vehicle_revenue_summary(cur=Depends(get_cursor)):
    """Original bot plan's 'basic revenue/utilization view'. Registered
    BEFORE /vehicles/{vehicle_id} below -- same route-ordering discipline
    as /rentals/blocked above: 'revenue-summary' is a fixed literal
    segment that would otherwise be swallowed by the int-typed
    {vehicle_id} path param (a real bug caught via test_api.py's direct
    __main__ run, which exercises actual FastAPI routing, unlike the
    pytest suite's per-route mocked calls)."""
    return repo.vehicle_revenue_summary(cur)


@app.get("/vehicles/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: int, cur=Depends(get_cursor)):
    vehicle = repo.get_vehicle(cur, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail=f"No vehicle with id={vehicle_id}")
    return _vehicle_to_out(vehicle)


@app.post("/vehicles/{vehicle_id}/position", response_model=VehicleOut)
def update_vehicle_position(vehicle_id: int, body: VehiclePositionIn, cur=Depends(get_cursor)):
    """Bot-maintained, non-legal per handoff §2.3 -- see
    repository.update_vehicle_position()'s own docstring. This is the
    route the future rental-operations bot (Bouncie/standard-fleet/
    geofence, handoff §1.7/E-3) will call once it exists; nothing in
    this repo calls it automatically today."""
    try:
        return _vehicle_to_out(repo.update_vehicle_position(cur, vehicle_id, body.position, body.actor))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Renters (links an already-existing platform.person; handoff §2.2 --
# identity resolution happens upstream via platform.match_or_create_person(),
# per docs/BACKLOG.md, NOT in this route.) -----------------------------------

@app.post("/renters", response_model=RenterOut)
def create_renter(body: RenterIn, cur=Depends(get_cursor)):
    renter = repo.create_renter_for_existing_person(
        cur, body.person_id, body.actor,
        jotform_submission_ref=body.jotform_submission_ref,
        drive_folder_ref=body.drive_folder_ref,
    )
    return _renter_to_out(renter)


@app.get("/renters/{renter_id}", response_model=RenterOut)
def get_renter(renter_id: int, cur=Depends(get_cursor)):
    renter = repo.get_renter(cur, renter_id)
    if renter is None:
        raise HTTPException(status_code=404, detail=f"No renter with id={renter_id}")
    return _renter_to_out(renter)


@app.get("/renters/by-person/{person_id}", response_model=RenterOut)
def get_renter_by_person(person_id: int, cur=Depends(get_cursor)):
    renter = repo.get_renter_by_person_id(cur, person_id)
    if renter is None:
        raise HTTPException(status_code=404, detail=f"No renter linked to person_id={person_id}")
    return _renter_to_out(renter)


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

@app.post("/rentals/{rental_id}/proposals", response_model=ProposalOut, dependencies=[Depends(require_bot_api_key)])
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


# --- Documents (shared platform document generator, handoff §1.3) ----------
# Storage/log layer only -- this does NOT render a PDF. A caller looks up
# the active template first (GET /document-templates/{family}), then
# posts the merge_data/attachments it already assembled. Rendering itself
# is future template-engine work, out of scope for this data layer.

@app.get("/document-templates/{family}")
def get_active_document_template(family: str, cur=Depends(get_cursor)):
    try:
        fam = DocumentTemplateFamily(family)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"family={family!r} must be one of {[f.value for f in DocumentTemplateFamily]}")
    template = repo.get_active_document_template(cur, fam)
    if template is None:
        raise HTTPException(status_code=404, detail=f"No active document_template for family={family!r}")
    return {"id": template.id, "family": template.family.value, "version": template.version, "template_ref": template.template_ref}


@app.post("/documents", response_model=DocumentOut)
def create_document(body: DocumentIn, cur=Depends(get_cursor)):
    try:
        document = Document(
            template_id=body.template_id, source_table=body.source_table, source_id=body.source_id,
            merge_data=body.merge_data, attachments=body.attachments,
            output_ref=body.output_ref, output_hash=body.output_hash,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _document_to_out(repo.create_document(cur, document, body.actor))


@app.get("/documents/never-sent")
def get_documents_never_sent(cur=Depends(get_cursor)):
    """Handoff §1.3's exact phrase: 'generated but never sent' is visible.
    Registered BEFORE /documents/{document_id} below -- same routing-order
    fix as /rentals/blocked (this file's earlier note): FastAPI matches in
    registration order, so 'never-sent' would otherwise get swallowed as
    an unparseable document_id and 422."""
    return repo.list_documents_never_sent(cur)


@app.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, cur=Depends(get_cursor)):
    document = repo.get_document(cur, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"No document with id={document_id}")
    return _document_to_out(document)


@app.post("/documents/{document_id}/outbound", response_model=OutboundLogOut)
def create_outbound_log(document_id: int, body: OutboundLogIn, cur=Depends(get_cursor)):
    if repo.get_document(cur, document_id) is None:
        raise HTTPException(status_code=404, detail=f"No document with id={document_id}")
    try:
        channel = OutboundChannel(body.channel)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"channel={body.channel!r} must be one of {[c.value for c in OutboundChannel]}")
    log = OutboundLog(
        document_id=document_id, channel=channel, recipient=body.recipient,
        delivery_confirmation_ref=body.delivery_confirmation_ref,
    )
    return _outbound_log_to_out(repo.create_outbound_log(cur, log, body.actor))


@app.get("/documents/{document_id}/outbound", response_model=list[OutboundLogOut])
def get_outbound_log(document_id: int, cur=Depends(get_cursor)):
    if repo.get_document(cur, document_id) is None:
        raise HTTPException(status_code=404, detail=f"No document with id={document_id}")
    return [_outbound_log_to_out(o) for o in repo.list_outbound_log_for_document(cur, document_id)]


# --- Communication timeline (shared platform primitive, handoff §1.5/§2.6) --
# Inbound rows matched by claim number are PROPOSALS -- handoff's own words:
# "wrong-claim attachment is worse than no attachment". This endpoint never
# auto-confirms; confirm/reject are separate human-gated actions below.

@app.post("/communications", response_model=CommunicationOut)
def create_communication(body: CommunicationIn, cur=Depends(get_cursor)):
    try:
        direction = CommunicationDirection(body.direction)
        channel = CommunicationChannel(body.channel)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    now = datetime.now()
    try:
        comm = Communication(
            source_table=body.source_table, source_id=body.source_id,
            direction=direction, channel=channel, occurred_at=body.occurred_at,
            source_system=body.source_system, from_ref=body.from_ref, to_ref=body.to_ref,
            subject=body.subject, transcript_ref=body.transcript_ref,
            match_status=CommunicationMatchStatus.PROPOSED if body.proposed else CommunicationMatchStatus.CONFIRMED,
            match_evidence=body.match_evidence,
            matched_by=None if body.proposed else body.actor,
            matched_at=None if body.proposed else now,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _communication_to_out(repo.create_communication(cur, comm, body.actor))


@app.get("/communications/pending")
def get_pending_communication_matches(cur=Depends(get_cursor)):
    """Handoff §2.6's confirm-or-reject queue for inbound claim-number auto-matches."""
    return repo.list_pending_communication_matches(cur)


@app.get("/communications", response_model=list[CommunicationOut])
def get_communications_for_source(source_table: str, source_id: int, cur=Depends(get_cursor)):
    """Query-param form deliberately, NOT a path segment like
    /{source_table}/{source_id}/communications -- that shape would be a
    wildcard route matching almost any two-segment path prefix in this
    file, risking silent collisions with every other route registered
    after it. source_table/source_id are the polymorphic attachment key
    (e.g. source_table='elektrica.rental', source_id=<rental id>)."""
    return [_communication_to_out(c) for c in repo.list_communications_for_source(cur, source_table, source_id)]


@app.post("/communications/{communication_id}/confirm", response_model=CommunicationOut)
def confirm_communication(communication_id: int, body: CommunicationDecisionRequest, cur=Depends(get_cursor)):
    try:
        comm = repo.confirm_communication_match(cur, communication_id, body.actor)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _communication_to_out(comm)


@app.post("/communications/{communication_id}/reject", response_model=CommunicationOut)
def reject_communication(communication_id: int, body: CommunicationDecisionRequest, cur=Depends(get_cursor)):
    try:
        comm = repo.reject_communication_match(cur, communication_id, body.actor)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _communication_to_out(comm)

