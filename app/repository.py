"""Repository layer -- maps app.models dataclasses to/from the
`elektrica` / `platform` Postgres schema (migrations/001-011). All SQL
lives here, parametrized (never string-interpolated), so app code above
this layer never writes raw SQL.

Every write function takes an explicit `actor` string for created_by /
updated_by -- no "system" default is silently assumed, same audit-trail
discipline as Complete Collision's repository.py.

STATE MACHINE DISCIPLINE (the one thing genuinely different from
Collision's flat JobStatus sequence): elektrica.rental.current_state is
NEVER written directly. advance_rental_state() below is the only path
-- it inserts an elektrica.rental_event row and lets the DB trigger
(elektrica.rental_advance_state(), migrations/003) derive the cached
current_state. Direct UPDATEs to current_state are blocked by a
trigger (elektrica.rental_forbid_direct_state_write()) even under
neondb_owner, so there is no accidental bypass path from this layer.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import psycopg2.extras

from app.models import (
    ComplianceItem,
    ComplianceItemStatus,
    ComplianceItemType,
    Communication,
    CommunicationChannel,
    CommunicationDirection,
    CommunicationMatchStatus,
    Demand,
    DemandRecipientType,
    DemandStatus,
    DemandType,
    Document,
    DocumentTemplate,
    DocumentTemplateFamily,
    EventSource,
    OutboundChannel,
    OutboundLog,
    Payment,
    PaymentSource,
    ProposalKind,
    ProposalStatus,
    Rental,
    RentalBilledTo,
    RentalEvent,
    RentalProposal,
    RentalState,
    Renter,
    StaffRole,
    StaffUser,
    Toll,
    TrackingSystem,
    Vehicle,
    VehicleClass,
    VehicleStatus,
    validate_rental_transition,
)


def _json(d) -> Optional[psycopg2.extras.Json]:
    return psycopg2.extras.Json(d) if d is not None else None


# ---------------------------------------------------------------------------
# Renter
# ---------------------------------------------------------------------------

def get_renter_by_person_id(cur, person_id: int) -> Optional[Renter]:
    cur.execute("SELECT * FROM elektrica.renter WHERE person_id = %s", (person_id,))
    row = cur.fetchone()
    return _renter_from_row(row) if row else None


def get_renter(cur, renter_id: int) -> Optional[Renter]:
    cur.execute("SELECT * FROM elektrica.renter WHERE id = %s", (renter_id,))
    row = cur.fetchone()
    return _renter_from_row(row) if row else None


def create_renter_for_existing_person(
    cur, person_id: int, actor: str,
    jotform_submission_ref: Optional[str] = None,
    drive_folder_ref: Optional[str] = None,
) -> Renter:
    """Link an ALREADY-EXISTING platform.person row as an Elektrica
    renter. This is the path a day-to-day backend should call -- see
    docs/BACKLOG.md's staff-provisioning entry for the same
    match-before-create discipline applied to renters (identity
    resolution happens upstream of this call, not inside it)."""
    existing = get_renter_by_person_id(cur, person_id)
    if existing:
        return existing
    cur.execute(
        """
        INSERT INTO elektrica.renter (person_id, jotform_submission_ref, drive_folder_ref, created_by)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (person_id, jotform_submission_ref, drive_folder_ref, actor),
    )
    return _renter_from_row(cur.fetchone())


def _renter_from_row(row) -> Renter:
    return Renter(
        id=row["id"], person_id=row["person_id"],
        jotform_submission_ref=row["jotform_submission_ref"],
        drive_folder_ref=row["drive_folder_ref"],
        created_at=row["created_at"], created_by=row["created_by"],
    )


# ---------------------------------------------------------------------------
# Vehicle
# ---------------------------------------------------------------------------

def get_vehicle_by_vin(cur, vin: str) -> Optional[Vehicle]:
    cur.execute("SELECT * FROM elektrica.vehicle WHERE vin = %s", (vin,))
    row = cur.fetchone()
    return _vehicle_from_row(row) if row else None


def get_vehicle(cur, vehicle_id: int) -> Optional[Vehicle]:
    cur.execute("SELECT * FROM elektrica.vehicle WHERE id = %s", (vehicle_id,))
    row = cur.fetchone()
    return _vehicle_from_row(row) if row else None


def create_vehicle(cur, vehicle: Vehicle, actor: str) -> Vehicle:
    cur.execute(
        """
        INSERT INTO elektrica.vehicle (
            vin, class, status, tracking_system, notes, created_by, updated_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            vehicle.vin,
            vehicle.vehicle_class.value if vehicle.vehicle_class else None,
            vehicle.status.value,
            vehicle.tracking_system.value if vehicle.tracking_system else None,
            vehicle.notes, actor, actor,
        ),
    )
    return _vehicle_from_row(cur.fetchone())


def list_vehicles_by_status(cur, status: VehicleStatus) -> list[Vehicle]:
    """Backs the Fleet board's "Out" / "Available" halves (handoff §2.5)."""
    cur.execute("SELECT * FROM elektrica.vehicle WHERE status = %s ORDER BY id", (status.value,))
    return [_vehicle_from_row(r) for r in cur.fetchall()]


def update_vehicle_position(cur, vehicle_id: int, position: dict, actor: str) -> Vehicle:
    """Bot-maintained, non-legal per handoff §2.3 -- separate from the
    state-machine-guarded rental fields, since current_position is a
    plain column with no event log of its own."""
    cur.execute(
        """
        UPDATE elektrica.vehicle
        SET current_position = %s, position_updated_at = now(), updated_at = now(), updated_by = %s
        WHERE id = %s
        RETURNING *
        """,
        (_json(position), actor, vehicle_id),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No vehicle with id={vehicle_id}")
    return _vehicle_from_row(row)


def _vehicle_from_row(row) -> Vehicle:
    return Vehicle(
        id=row["id"], vin=row["vin"],
        vehicle_class=VehicleClass(row["class"]) if row["class"] else None,
        status=VehicleStatus(row["status"]),
        tracking_system=TrackingSystem(row["tracking_system"]) if row["tracking_system"] else None,
        current_position=row["current_position"],
        position_updated_at=row["position_updated_at"],
        notes=row["notes"],
        created_at=row["created_at"], updated_at=row["updated_at"],
        created_by=row["created_by"], updated_by=row["updated_by"],
    )


# ---------------------------------------------------------------------------
# Rental -- the spine. current_state is DERIVED, never written directly.
# ---------------------------------------------------------------------------

def create_rental(cur, rental: Rental, actor: str) -> Rental:
    """Creates the rental row (current_state defaults to 'active' in the
    DB) AND its first rental_event (source='manual', event_type='active'
    is NOT valid as a first event under the current trigger set -- the
    DB's DEFAULT 'active' means the row starts there with no event row
    at all, mirroring vls.case's own "state before the first event"
    convention). Returns the created Rental."""
    cur.execute(
        """
        INSERT INTO elektrica.rental (
            vehicle_id, renter_id, body_shop, rental_type, billed_to,
            start_date, end_date, assignment_document_ref,
            drive_folder_ref, jotform_submission_ref, created_by, updated_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            rental.vehicle_id, rental.renter_id, rental.body_shop, rental.rental_type,
            rental.billed_to.value if rental.billed_to else None,
            rental.start_date, rental.end_date, rental.assignment_document_ref,
            rental.drive_folder_ref, rental.jotform_submission_ref, actor, actor,
        ),
    )
    return _rental_from_row(cur.fetchone())


def get_rental(cur, rental_id: int) -> Optional[Rental]:
    cur.execute("SELECT * FROM elektrica.rental WHERE id = %s", (rental_id,))
    row = cur.fetchone()
    return _rental_from_row(row) if row else None


def advance_rental_state(
    cur, rental_id: int, target: RentalState, source: EventSource, actor: str,
    source_ref: Optional[str] = None, notes: Optional[str] = None,
) -> Rental:
    """THE only sanctioned way to move a rental forward. Pre-validates
    against the in-Python mirror (validate_rental_transition) for a fast,
    clear error on an obviously-illegal jump, then inserts the
    rental_event row and lets the DB trigger chain
    (rental_event_check_litigation -> rental_event_enforce_sequence ->
    rental_advance_state, migrations/003+007) do the real enforcement
    and derive current_state. Raises psycopg2.errors.RaiseException
    (wrapping the DB's RAISE EXCEPTION) if the DB disagrees -- e.g. the
    in_litigation/resolved vls.case-linkage gate, which this function
    cannot pre-check without a cross-schema read this layer doesn't
    duplicate on purpose (single source of truth stays in the DB
    trigger, not copied here)."""
    current = get_rental(cur, rental_id)
    if current is None:
        raise ValueError(f"No rental with id={rental_id}")
    validate_rental_transition(current.current_state, target)

    cur.execute(
        """
        INSERT INTO elektrica.rental_event (rental_id, event_type, source, source_ref, notes, confirmed, confirmed_by, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (rental_id, target.value, source.value, source_ref, notes, True, actor, actor),
    )
    return get_rental(cur, rental_id)


def list_rental_events(cur, rental_id: int) -> list[RentalEvent]:
    cur.execute(
        "SELECT * FROM elektrica.rental_event WHERE rental_id = %s ORDER BY event_date",
        (rental_id,),
    )
    return [_rental_event_from_row(r) for r in cur.fetchall()]


def list_blocked_rentals(cur) -> list[dict]:
    """Reads elektrica.blocked_rentals (migrations/003, updated by 007)
    -- the "silence is the signal" surface, handoff §2.4. Returned as raw
    dicts (view has no corresponding dataclass -- it's a
    query-shaped diagnostic, not an entity)."""
    cur.execute("SELECT * FROM elektrica.blocked_rentals")
    return list(cur.fetchall())


def link_vls_case(cur, rental_id: int, vls_case_id: int, actor: str) -> Rental:
    """Sets elektrica.rental.vls_case_id -- required before a rental can
    transition needs_served -> in_litigation (migrations/007's
    rental_event_check_litigation trigger). This is a plain column
    write (not state-machine-guarded), separate from advance_rental_state
    on purpose: linking a case and actually entering in_litigation are
    two different real-world events."""
    cur.execute(
        """
        UPDATE elektrica.rental
        SET vls_case_id = %s, updated_at = now(), updated_by = %s
        WHERE id = %s
        RETURNING *
        """,
        (vls_case_id, actor, rental_id),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No rental with id={rental_id}")
    return _rental_from_row(row)


def _rental_from_row(row) -> Rental:
    return Rental(
        id=row["id"], vehicle_id=row["vehicle_id"], renter_id=row["renter_id"],
        body_shop=row["body_shop"], rental_type=row["rental_type"],
        billed_to=RentalBilledTo(row["billed_to"]) if row["billed_to"] else None,
        start_date=row["start_date"], end_date=row["end_date"],
        assignment_document_ref=row["assignment_document_ref"],
        drive_folder_ref=row["drive_folder_ref"], jotform_submission_ref=row["jotform_submission_ref"],
        vls_case_id=row["vls_case_id"],
        current_state=RentalState(row["current_state"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
        created_by=row["created_by"], updated_by=row["updated_by"],
    )


def _rental_event_from_row(row) -> RentalEvent:
    return RentalEvent(
        id=row["id"], rental_id=row["rental_id"], event_type=RentalState(row["event_type"]),
        event_date=row["event_date"], source=EventSource(row["source"]),
        source_ref=row["source_ref"], notes=row["notes"],
        confirmed=row["confirmed"], confirmed_by=row["confirmed_by"],
        created_at=row["created_at"], created_by=row["created_by"],
    )


# ---------------------------------------------------------------------------
# RentalProposal -- bot-written, handoff §1.7. Accepting/rejecting NEVER
# touches elektrica.rental directly; callers must separately call
# advance_rental_state (or another explicit write) if a decision should
# actually change the rental.
# ---------------------------------------------------------------------------

def create_rental_proposal(cur, proposal: RentalProposal, actor: str) -> RentalProposal:
    cur.execute(
        """
        INSERT INTO elektrica.rental_proposal (
            rental_id, kind, proposed_values, source_system, evidence, observed_at, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            proposal.rental_id, proposal.kind.value, _json(proposal.proposed_values),
            proposal.source_system, _json(proposal.evidence), proposal.observed_at, actor,
        ),
    )
    return _rental_proposal_from_row(cur.fetchone())


def list_pending_rental_proposals(cur) -> list[RentalProposal]:
    """Queries the base table filtered to status='pending', not the
    elektrica.pending_rental_proposals VIEW directly -- that view
    (migrations/004) intentionally projects only the columns a "confirm
    bot proposal" screen needs (id, rental_id, kind, proposed_values,
    source_system, evidence, observed_at, created_at), omitting
    status/decided_by/decided_at/created_by, so it cannot round-trip
    through _rental_proposal_from_row(). Same WHERE clause and ORDER BY
    as the view, so callers see identical rows either way."""
    cur.execute(
        "SELECT * FROM elektrica.rental_proposal WHERE status = 'pending' ORDER BY observed_at ASC"
    )
    return [_rental_proposal_from_row(r) for r in cur.fetchall()]


def decide_rental_proposal(
    cur, proposal_id: int, status: ProposalStatus, actor: str,
) -> RentalProposal:
    """Records the one-time decision only. Per handoff §1.7 this is
    NEVER auto-applied to elektrica.rental -- if accepting should change
    the rental (e.g. confirm a proposed return date), the caller makes
    that a SEPARATE, explicit call (e.g. advance_rental_state or a plain
    UPDATE), so the audit trail shows a human/app decision, not an
    automatic cascade."""
    if status == ProposalStatus.PENDING:
        raise ValueError("decide_rental_proposal cannot set status back to 'pending'.")
    cur.execute(
        """
        UPDATE elektrica.rental_proposal
        SET status = %s, decided_by = %s, decided_at = now()
        WHERE id = %s
        RETURNING *
        """,
        (status.value, actor, proposal_id),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No rental_proposal with id={proposal_id}")
    return _rental_proposal_from_row(row)


def _rental_proposal_from_row(row) -> RentalProposal:
    return RentalProposal(
        id=row["id"], rental_id=row["rental_id"], kind=ProposalKind(row["kind"]),
        proposed_values=row["proposed_values"], source_system=row["source_system"],
        evidence=row["evidence"], observed_at=row["observed_at"],
        status=ProposalStatus(row["status"]), decided_by=row["decided_by"], decided_at=row["decided_at"],
        created_at=row["created_at"], created_by=row["created_by"],
    )


# ---------------------------------------------------------------------------
# Toll
# ---------------------------------------------------------------------------

def create_toll(cur, toll: Toll, actor: str) -> Toll:
    cur.execute(
        """
        INSERT INTO elektrica.toll (rental_id, tolloptics_record_id, amount, toll_date, confirmed, created_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (toll.rental_id, toll.tolloptics_record_id, toll.amount, toll.toll_date, toll.confirmed, actor),
    )
    return _toll_from_row(cur.fetchone())


def confirm_toll(cur, toll_id: int) -> Toll:
    cur.execute(
        "UPDATE elektrica.toll SET confirmed = true WHERE id = %s RETURNING *",
        (toll_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No toll with id={toll_id}")
    return _toll_from_row(row)


def list_tolls_for_rental(cur, rental_id: int) -> list[Toll]:
    cur.execute("SELECT * FROM elektrica.toll WHERE rental_id = %s ORDER BY toll_date", (rental_id,))
    return [_toll_from_row(r) for r in cur.fetchall()]


def _toll_from_row(row) -> Toll:
    return Toll(
        id=row["id"], rental_id=row["rental_id"], tolloptics_record_id=row["tolloptics_record_id"],
        amount=row["amount"], toll_date=row["toll_date"], confirmed=row["confirmed"],
        created_at=row["created_at"], created_by=row["created_by"],
    )


# ---------------------------------------------------------------------------
# Demand + ComparableSet
# ---------------------------------------------------------------------------

def create_demand(cur, demand: Demand, actor: str) -> Demand:
    cur.execute(
        """
        INSERT INTO elektrica.demand (
            rental_id, demand_type, recipient_type, carrier_name, adjuster_name,
            amount, generated_document_id, sent_via, sent_at, status,
            prior_demand_id, created_by, updated_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            demand.rental_id, demand.demand_type.value, demand.recipient_type.value,
            demand.carrier_name, demand.adjuster_name, demand.amount,
            demand.generated_document_id, demand.sent_via, demand.sent_at,
            demand.status.value, demand.prior_demand_id, actor, actor,
        ),
    )
    return _demand_from_row(cur.fetchone())


def get_demand(cur, demand_id: int) -> Optional[Demand]:
    cur.execute("SELECT * FROM elektrica.demand WHERE id = %s", (demand_id,))
    row = cur.fetchone()
    return _demand_from_row(row) if row else None


def mark_demand_sent(cur, demand_id: int, sent_via: str, actor: str) -> Demand:
    cur.execute(
        """
        UPDATE elektrica.demand
        SET status = 'sent', sent_via = %s, sent_at = now(), updated_by = %s
        WHERE id = %s AND status = 'draft'
        RETURNING *
        """,
        (sent_via, actor, demand_id),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No draft demand with id={demand_id} (either missing or already sent)")
    return _demand_from_row(row)


def list_aging_demands(cur) -> list[dict]:
    """Reads elektrica.aging_demands (migrations/006) -- "a demand at 45
    days with no offer ... silence is the signal", handoff §2.4."""
    cur.execute("SELECT * FROM elektrica.aging_demands")
    return list(cur.fetchall())


def create_comparable_set(cur, cs, actor: str):
    from app.models import ComparableSet  # local import avoids unused-at-module-scope lint noise
    cur.execute(
        """
        INSERT INTO elektrica.comparable_set (
            demand_id, scan_source, scan_timestamp, vehicle_class,
            date_range_start, date_range_end, comparables, computed_average, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            cs.demand_id, cs.scan_source, cs.scan_timestamp,
            cs.vehicle_class.value if cs.vehicle_class else None,
            cs.date_range_start, cs.date_range_end, _json(cs.comparables), cs.computed_average, actor,
        ),
    )
    row = cur.fetchone()
    return ComparableSet(
        id=row["id"], demand_id=row["demand_id"], scan_source=row["scan_source"],
        scan_timestamp=row["scan_timestamp"],
        vehicle_class=VehicleClass(row["vehicle_class"]) if row["vehicle_class"] else None,
        date_range_start=row["date_range_start"], date_range_end=row["date_range_end"],
        comparables=row["comparables"], computed_average=row["computed_average"],
        created_at=row["created_at"], created_by=row["created_by"],
    )


def _demand_from_row(row) -> Demand:
    return Demand(
        id=row["id"], rental_id=row["rental_id"], demand_type=DemandType(row["demand_type"]),
        recipient_type=DemandRecipientType(row["recipient_type"]),
        carrier_name=row["carrier_name"], adjuster_name=row["adjuster_name"],
        amount=row["amount"], generated_document_id=row["generated_document_id"],
        sent_via=row["sent_via"], sent_at=row["sent_at"], status=DemandStatus(row["status"]),
        prior_demand_id=row["prior_demand_id"],
        created_at=row["created_at"], updated_at=row["updated_at"],
        created_by=row["created_by"], updated_by=row["updated_by"],
    )


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

def create_payment(cur, payment: Payment, actor: str) -> Payment:
    cur.execute(
        """
        INSERT INTO elektrica.payment (
            rental_id, demand_id, source, external_transaction_id, amount, accounting_sync_ref, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            payment.rental_id, payment.demand_id, payment.source.value,
            payment.external_transaction_id, payment.amount, payment.accounting_sync_ref, actor,
        ),
    )
    return _payment_from_row(cur.fetchone())


def list_payments_for_rental(cur, rental_id: int) -> list[Payment]:
    cur.execute("SELECT * FROM elektrica.payment WHERE rental_id = %s ORDER BY received_at", (rental_id,))
    return [_payment_from_row(r) for r in cur.fetchall()]


def vehicle_revenue_summary(cur) -> list[dict]:
    """Reads elektrica.vehicle_revenue_summary (migrations/008) --
    original bot plan's "basic revenue/utilization view"."""
    cur.execute("SELECT * FROM elektrica.vehicle_revenue_summary")
    return list(cur.fetchall())


def _payment_from_row(row) -> Payment:
    return Payment(
        id=row["id"], rental_id=row["rental_id"], demand_id=row["demand_id"],
        source=PaymentSource(row["source"]), external_transaction_id=row["external_transaction_id"],
        amount=row["amount"], accounting_sync_ref=row["accounting_sync_ref"],
        received_at=row["received_at"], created_at=row["created_at"], created_by=row["created_by"],
    )


# ---------------------------------------------------------------------------
# ComplianceItem
# ---------------------------------------------------------------------------

def create_compliance_item(cur, item: ComplianceItem, actor: str) -> ComplianceItem:
    cur.execute(
        """
        INSERT INTO elektrica.compliance_item (
            item_type, description, vehicle_id, expiration_date, status,
            related_document_id, created_by, updated_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            item.item_type.value, item.description, item.vehicle_id, item.expiration_date,
            item.status.value, item.related_document_id, actor, actor,
        ),
    )
    return _compliance_item_from_row(cur.fetchone())


def list_compliance_items_expiring_soon(cur) -> list[dict]:
    cur.execute("SELECT * FROM elektrica.compliance_items_expiring_soon")
    return list(cur.fetchall())


def _compliance_item_from_row(row) -> ComplianceItem:
    return ComplianceItem(
        id=row["id"], item_type=ComplianceItemType(row["item_type"]), description=row["description"],
        vehicle_id=row["vehicle_id"], expiration_date=row["expiration_date"],
        status=ComplianceItemStatus(row["status"]), related_document_id=row["related_document_id"],
        created_at=row["created_at"], updated_at=row["updated_at"],
        created_by=row["created_by"], updated_by=row["updated_by"],
    )


# ---------------------------------------------------------------------------
# StaffUser -- provisioning. Same match-before-create discipline flagged
# in docs/BACKLOG.md: this module only links an ALREADY-EXISTING
# platform.person row (elektrica_app has SELECT-only on staff_user per
# migration 011 -- provisioning itself requires a privileged connection,
# same caveat as Collision's provision_staff_user_for_existing_person()).
# ---------------------------------------------------------------------------

def get_staff_user_by_google_email(cur, google_email: str) -> Optional[StaffUser]:
    cur.execute(
        "SELECT * FROM elektrica.staff_user WHERE google_email = %s",
        (google_email.strip().lower(),),
    )
    row = cur.fetchone()
    return _staff_user_from_row(row) if row else None


def provision_staff_user_for_existing_person(
    cur, person_id: int, role: StaffRole, google_email: str, actor: str,
    provisioned_by_staff_user_id: Optional[int] = None,
) -> StaffUser:
    """*** REQUIRES A PRIVILEGED CONNECTION *** -- elektrica_app has
    SELECT-only on staff_user (migration 011's tighter grant, matching
    VLS's pattern rather than Collision's broader one). Runs under
    neondb_owner-class connections only, same caveat pattern as every
    other provisioning function in this repo family."""
    su = StaffUser(
        person_id=person_id, role=role, google_email=google_email,
        provisioned_by_staff_user_id=provisioned_by_staff_user_id,
    )  # __post_init__ validates the domain before hitting the DB
    cur.execute(
        """
        INSERT INTO elektrica.staff_user (person_id, role, google_email, provisioned_by_staff_user_id, created_by, updated_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (su.person_id, su.role.value, su.google_email, su.provisioned_by_staff_user_id, actor, actor),
    )
    return _staff_user_from_row(cur.fetchone())


def set_staff_user_active(cur, google_email: str, active: bool, actor: str) -> StaffUser:
    """Flip a staff member's active flag. *** REQUIRES A PRIVILEGED
    CONNECTION *** -- same caveat as provision_staff_user_for_existing_person()
    (elektrica_app has SELECT-only on staff_user, migration 011). Mirrors
    Collision's set_staff_user_active() (same repo family, same
    conventions) -- Elektrica has no staff_user_capability() function
    (unlike Collision, whose owner/manager/receptionist role set needed
    graduated permissions; Elektrica's role set is CONFIRMED FINAL as a
    flat owner/staff split with no further granularity per Jed, migration
    011's own header), so there is no capability-lookup counterpart to
    build here -- active/inactive plus the role enum is the whole
    permission surface for this business, not a gap."""
    cur.execute(
        """
        UPDATE elektrica.staff_user
        SET active = %s, updated_at = now(), updated_by = %s
        WHERE google_email = %s
        RETURNING *
        """,
        (active, actor, google_email.strip().lower()),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No staff_user with google_email={google_email!r}")
    return _staff_user_from_row(row)


def _staff_user_from_row(row) -> StaffUser:
    return StaffUser(
        id=row["id"], person_id=row["person_id"], role=StaffRole(row["role"]),
        google_email=row["google_email"], active=row["active"],
        provisioned_by_staff_user_id=row["provisioned_by_staff_user_id"],
        created_at=row["created_at"], created_by=row["created_by"],
        updated_at=row["updated_at"], updated_by=row["updated_by"],
    )


# ---------------------------------------------------------------------------
# platform.document_template / platform.document / platform.outbound_log
# (migrations/005, relocated by migrations/009) -- shared document
# generator storage layer, handoff §1.3. First app-layer code for these
# tables; they existed schema-only since 2026-09-03/04.
# ---------------------------------------------------------------------------

def get_active_document_template(cur, family: DocumentTemplateFamily) -> Optional[DocumentTemplate]:
    """Handoff §1.3: 'Templates are versioned; a generated document
    records the template version used.' Callers generating a document
    look up the currently-active version for a family, then pass its id
    into create_document() -- this function does not itself write
    anything."""
    cur.execute(
        "SELECT * FROM platform.document_template WHERE family = %s AND is_active = true",
        (family.value,),
    )
    row = cur.fetchone()
    return _document_template_from_row(row) if row else None


def create_document_template(cur, template: DocumentTemplate, actor: str) -> DocumentTemplate:
    cur.execute(
        """
        INSERT INTO platform.document_template (family, version, template_ref, is_active, created_by)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
        """,
        (template.family.value, template.version, template.template_ref, template.is_active, actor),
    )
    return _document_template_from_row(cur.fetchone())


def _document_template_from_row(row) -> DocumentTemplate:
    return DocumentTemplate(
        id=row["id"], family=DocumentTemplateFamily(row["family"]), version=row["version"],
        template_ref=row["template_ref"], is_active=row["is_active"],
        created_at=row["created_at"], created_by=row["created_by"],
    )


def create_document(cur, document: Document, actor: str) -> Document:
    """Writes the append-only generation-log row (platform.document is
    immutable from creation, migrations/005 -- DELETE/UPDATE both forbid
    at the DB layer). merge_data is frozen at generation time per handoff
    §1.3's reproducibility requirement; this function does not itself
    render a PDF -- that is future template-rendering work, out of scope
    for the data layer."""
    cur.execute(
        """
        INSERT INTO platform.document (
            template_id, source_table, source_id, merge_data, attachments,
            output_ref, output_hash, generated_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            document.template_id, document.source_table, document.source_id,
            _json(document.merge_data), _json(document.attachments),
            document.output_ref, document.output_hash, actor,
        ),
    )
    return _document_from_row(cur.fetchone())


def get_document(cur, document_id: int) -> Optional[Document]:
    cur.execute("SELECT * FROM platform.document WHERE id = %s", (document_id,))
    row = cur.fetchone()
    return _document_from_row(row) if row else None


def list_documents_never_sent(cur) -> list[dict]:
    """Reads platform.documents_never_sent (migrations/005/009) --
    handoff §1.3's exact phrase: 'generated but never sent' is visible."""
    cur.execute("SELECT * FROM platform.documents_never_sent")
    return list(cur.fetchall())


def _document_from_row(row) -> Document:
    return Document(
        id=row["id"], template_id=row["template_id"],
        source_table=row["source_table"], source_id=row["source_id"],
        merge_data=row["merge_data"], attachments=row["attachments"],
        output_ref=row["output_ref"], output_hash=row["output_hash"],
        generated_at=row["generated_at"], generated_by=row["generated_by"],
    )


def create_outbound_log(cur, log: OutboundLog, actor: str) -> OutboundLog:
    """Records a send as its OWN append-only row -- deliberately separate
    from create_document() (handoff §1.3: 'Outbound delivery ... is a
    separate step with its own log row')."""
    cur.execute(
        """
        INSERT INTO platform.outbound_log (
            document_id, channel, recipient, delivery_confirmation_ref, sent_by
        ) VALUES (%s, %s, %s, %s, %s)
        RETURNING *
        """,
        (log.document_id, log.channel.value, log.recipient, log.delivery_confirmation_ref, actor),
    )
    return _outbound_log_from_row(cur.fetchone())


def list_outbound_log_for_document(cur, document_id: int) -> list[OutboundLog]:
    cur.execute(
        "SELECT * FROM platform.outbound_log WHERE document_id = %s ORDER BY sent_at",
        (document_id,),
    )
    return [_outbound_log_from_row(r) for r in cur.fetchall()]


def _outbound_log_from_row(row) -> OutboundLog:
    return OutboundLog(
        id=row["id"], document_id=row["document_id"], channel=OutboundChannel(row["channel"]),
        recipient=row["recipient"], delivery_confirmation_ref=row["delivery_confirmation_ref"],
        sent_at=row["sent_at"], sent_by=row["sent_by"],
    )


# ---------------------------------------------------------------------------
# platform.communication (migrations/010) -- shared comms timeline,
# handoff §1.5/§2.6. First app-layer code for this table; schema-only
# since the 2026-09-04 cron cycle that built migration 010.
# ---------------------------------------------------------------------------

def create_communication(cur, comm: Communication, actor: str) -> Communication:
    """Writes a communication row. Callers deciding an inbound match is
    correct/incorrect use confirm_communication_match()/
    reject_communication_match() below, NOT a second call to this
    function -- platform.communication only allows that one follow-up
    UPDATE per row (migrations/010's communication_restrict_update
    trigger), matching elektrica.rental_proposal's propose-then-confirm
    shape exactly."""
    cur.execute(
        """
        INSERT INTO platform.communication (
            source_table, source_id, direction, channel, occurred_at,
            from_ref, to_ref, subject, transcript_ref, source_system,
            match_status, match_evidence, matched_by, matched_at, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            comm.source_table, comm.source_id, comm.direction.value, comm.channel.value,
            comm.occurred_at, comm.from_ref, comm.to_ref, comm.subject, comm.transcript_ref,
            comm.source_system, comm.match_status.value, _json(comm.match_evidence),
            comm.matched_by, comm.matched_at, actor,
        ),
    )
    return _communication_from_row(cur.fetchone())


def list_communications_for_source(cur, source_table: str, source_id: int) -> list[Communication]:
    """Backs a rental's (or future collision.job's) communication timeline
    tab -- ordered newest-first, matching migrations/010's own index."""
    cur.execute(
        """
        SELECT * FROM platform.communication
        WHERE source_table = %s AND source_id = %s
        ORDER BY occurred_at DESC
        """,
        (source_table, source_id),
    )
    return [_communication_from_row(r) for r in cur.fetchall()]


def list_pending_communication_matches(cur) -> list[dict]:
    """Reads platform.pending_communication_matches (migrations/010) --
    the confirm-or-reject queue for inbound claim-number auto-matches,
    handoff §2.6: 'attached as a proposal pending confirmation'."""
    cur.execute("SELECT * FROM platform.pending_communication_matches")
    return list(cur.fetchall())


def _decide_communication_match(cur, communication_id: int, new_status: CommunicationMatchStatus, actor: str) -> Communication:
    cur.execute(
        """
        UPDATE platform.communication
        SET match_status = %s, matched_by = %s, matched_at = now()
        WHERE id = %s AND match_status = 'proposed'
        RETURNING *
        """,
        (new_status.value, actor, communication_id),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(
            f"No proposed communication with id={communication_id} "
            "(either missing or already decided -- migrations/010's trigger permits only one decision)."
        )
    return _communication_from_row(row)


def confirm_communication_match(cur, communication_id: int, actor: str) -> Communication:
    """Human confirms a proposed inbound-email claim-number match is
    correct. Handoff §2.6: 'wrong-claim attachment is worse than no
    attachment' -- this is the human gate that decision requires."""
    return _decide_communication_match(cur, communication_id, CommunicationMatchStatus.CONFIRMED, actor)


def reject_communication_match(cur, communication_id: int, actor: str) -> Communication:
    """Human reviews a proposed match and it was wrong."""
    return _decide_communication_match(cur, communication_id, CommunicationMatchStatus.REJECTED, actor)


def _communication_from_row(row) -> Communication:
    return Communication(
        id=row["id"], source_table=row["source_table"], source_id=row["source_id"],
        direction=CommunicationDirection(row["direction"]), channel=CommunicationChannel(row["channel"]),
        occurred_at=row["occurred_at"], from_ref=row["from_ref"], to_ref=row["to_ref"],
        subject=row["subject"], transcript_ref=row["transcript_ref"], source_system=row["source_system"],
        match_status=CommunicationMatchStatus(row["match_status"]), match_evidence=row["match_evidence"],
        matched_by=row["matched_by"], matched_at=row["matched_at"],
        created_at=row["created_at"], created_by=row["created_by"],
    )
