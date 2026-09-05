"""Elektrica Dashboard -- core domain models.

Phase: data-layer-first app code, per ADR-001-elektrica-rentals-v2.md's
own build-order discipline (schema before backend, backend before
frontend). These are plain dataclasses mirroring the `elektrica` /
`platform` Postgres schema (migrations/001-011). Field names match the
SQL columns 1:1 so repository.py's row <-> object mapping stays trivial.

Modeled directly on Complete Collision's app/models.py (same repo
family, same conventions) -- str Enum values matching Postgres enum
labels exactly, dataclasses with id/created_at/created_by trailing
fields, __post_init__ validation mirroring DB-level CHECK constraints
so bad data is rejected before it ever reaches a query.

SCOPE NOTE: elektrica.vehicle's class/status/tracking_system enums
(migration 002) carry PLACEHOLDER values pending the real Fleet export
-- see docs/OVERNIGHT_DECISIONS.md. This module mirrors those enums
as-is (same placeholder caveat), does not invent new values, and will
need a one-line VehicleClass/TrackingSystem update when the export
lands and migration 002 is corrected.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums -- kept in exact sync with the Postgres enum types they mirror.
# ---------------------------------------------------------------------------

class VehicleClass(str, Enum):
    """Matches elektrica.vehicle_class (migrations/002). PLACEHOLDER
    value set pending real Fleet export -- see docs/OVERNIGHT_DECISIONS.md."""
    EV = "ev"
    GAS = "gas"
    SUV = "suv"
    TRUCK = "truck"
    SEDAN = "sedan"
    VAN = "van"
    OTHER = "other"


class VehicleStatus(str, Enum):
    """Matches elektrica.vehicle_status (migrations/002)."""
    AVAILABLE = "available"
    OUT = "out"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class TrackingSystem(str, Enum):
    """Matches elektrica.tracking_system (migrations/002). PLACEHOLDER
    value set, taken verbatim from handoff §2.3's parenthetical."""
    BOUNCIE = "bouncie"
    STANDARD_FLEET = "standard_fleet"
    GEOFENCE_EMAIL = "geofence_email"
    NONE = "none"


class RentalState(str, Enum):
    """Matches elektrica.rental_state (migrations/003, extended by 007
    with 'in_litigation'). Order matters for JOB-STATUS-style sequence
    validation mirrors -- but unlike Collision, Elektrica's real sequence
    enforcement lives in the DB trigger
    (elektrica.rental_valid_next_states()), not here. This Python order
    is documentation, matching the handoff §2.4 diagram; app-layer code
    should call the DB (via advance_rental_state in repository.py), not
    re-derive validity here, so the DB stays the single source of truth."""
    ACTIVE = "active"
    FINISHED = "finished"
    NEEDS_DEMAND = "needs_demand"
    NEEDS_MORE_INFORMATION = "needs_more_information"
    DEMAND_SENT = "demand_sent"
    NEGOTIATING = "negotiating"
    NO_OFFER = "no_offer"
    NEEDS_LAWSUIT = "needs_lawsuit"
    NEEDS_SERVED = "needs_served"
    IN_LITIGATION = "in_litigation"
    RESOLVED = "resolved"


class RentalBilledTo(str, Enum):
    """Matches elektrica.rental_billed_to (migrations/003)."""
    CARRIER = "carrier"
    SELF = "self"
    BODY_SHOP = "body_shop"


class EventSource(str, Enum):
    """Matches elektrica.event_source (migrations/003)."""
    MANUAL = "manual"
    JOTFORM = "jotform"
    BOT_PROPOSAL = "bot_proposal"
    RINGCENTRAL = "ringcentral"
    SYSTEM = "system"


class ProposalKind(str, Enum):
    """Matches elektrica.proposal_kind (migrations/004)."""
    DEPARTURE = "departure"
    RETURN = "return"
    DATES = "dates"
    TOLLS = "tolls"


class ProposalStatus(str, Enum):
    """Matches elektrica.proposal_status (migrations/004)."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class DemandType(str, Enum):
    """Matches elektrica.demand_type (migrations/006) -- handoff-literal."""
    PRIMARY_INSURER = "primary_insurer"
    UIM = "uim"
    BALANCE_TO_RENTER = "balance_to_renter"


class DemandRecipientType(str, Enum):
    """Matches elektrica.demand_recipient_type (migrations/006)."""
    CARRIER = "carrier"
    RENTER = "renter"


class DemandStatus(str, Enum):
    """Matches elektrica.demand_status (migrations/006). PLACEHOLDER
    value set -- handoff only says "each has its own lifecycle", doesn't
    enumerate states. Inferred from the rental lifecycle's own
    vocabulary for consistency -- see migrations/006 header."""
    DRAFT = "draft"
    SENT = "sent"
    NEGOTIATING = "negotiating"
    NO_OFFER = "no_offer"
    ACCEPTED = "accepted"
    RESOLVED = "resolved"


class PaymentSource(str, Enum):
    """Matches elektrica.payment_source (migrations/008) -- handoff-literal
    (§1.6)."""
    AUTHORIZE_NET = "authorize_net"
    CHECK = "check"
    INSURER_EFT = "insurer_eft"
    MANUAL = "manual"


class ComplianceItemType(str, Enum):
    """Matches elektrica.compliance_item_type (migrations/008)."""
    DEALER_LICENSE = "dealer_license"
    REGISTRATION = "registration"
    INSURANCE = "insurance"
    OTHER = "other"


class ComplianceItemStatus(str, Enum):
    """Matches elektrica.compliance_item_status (migrations/008)."""
    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    RENEWED = "renewed"


class StaffRole(str, Enum):
    """Matches elektrica.staff_user's role enum (migrations/011).
    CONFIRMED FINAL by Jed 2026-09-04 -- owner/staff, no further
    granularity planned."""
    OWNER = "owner"
    STAFF = "staff"


GOOGLE_WORKSPACE_DOMAIN = "elektricarentals.com"
"""Matches migrations/011_elektrica_staff_user.sql's domain-restriction
CHECK constraint. Sourced from a real filename evidence (a certificate
PDF in ~/Downloads named with jed@elektricarentals.com) -- weaker
provenance than VLS's domain source, flagged as such in migration 011's
own header, not presented with unearned confidence."""


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------

@dataclass
class Renter:
    """Mirrors elektrica.renter (migrations/001). person_id points at the
    shared platform.person table (cross-business identity, shared with
    VLS/Collision) -- this dataclass does NOT model platform.person
    itself."""
    person_id: int
    jotform_submission_ref: Optional[str] = None
    drive_folder_ref: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


@dataclass
class Vehicle:
    """Mirrors elektrica.vehicle (migrations/002). class/status/
    tracking_system enum VALUES are placeholder -- see VehicleClass
    docstring above."""
    vin: str
    vehicle_class: Optional[VehicleClass] = None
    status: VehicleStatus = VehicleStatus.AVAILABLE
    tracking_system: Optional[TrackingSystem] = None
    current_position: Optional[dict] = None
    position_updated_at: Optional[datetime] = None
    notes: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


@dataclass
class Rental:
    """Mirrors elektrica.rental (migrations/003, extended by 007 with
    vls_case_id). current_state is a CACHED READ of the latest
    rental_event -- never written directly by application code; see
    repository.advance_rental_state()."""
    vehicle_id: int
    renter_id: int
    body_shop: Optional[str] = None       # PLACEHOLDER SHAPE, free text
    rental_type: Optional[str] = None     # PLACEHOLDER SHAPE, free text
    billed_to: Optional[RentalBilledTo] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    assignment_document_ref: Optional[str] = None
    drive_folder_ref: Optional[str] = None
    jotform_submission_ref: Optional[str] = None
    vls_case_id: Optional[int] = None
    current_state: RentalState = RentalState.ACTIVE
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


@dataclass
class RentalEvent:
    """Mirrors elektrica.rental_event (migrations/003) -- append-only
    status transition log, state DERIVED from these rows by a DB
    trigger (elektrica.rental_advance_state())."""
    rental_id: int
    event_type: RentalState
    source: EventSource
    source_ref: Optional[str] = None
    notes: Optional[str] = None
    confirmed: bool = True
    confirmed_by: Optional[str] = None
    event_date: Optional[datetime] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None

    def __post_init__(self):
        # Mirrors rental_event_source_ref_required CHECK.
        if self.source not in (EventSource.MANUAL, EventSource.SYSTEM) and not self.source_ref:
            raise ValueError(
                f"source={self.source.value!r} requires source_ref "
                "(elektrica.rental_event's rental_event_source_ref_required CHECK)."
            )
        # Mirrors rental_event_confirmed_by_required CHECK: CHECK (confirmed
        # = false OR confirmed_by IS NOT NULL) -- i.e. confirmed=true rows
        # MUST carry confirmed_by (who confirmed it); confirmed=false rows
        # are exempt (a bot-sourced event can sit unconfirmed with no
        # confirmed_by until a human confirms it).
        if self.confirmed and not self.confirmed_by:
            raise ValueError(
                "confirmed=True requires confirmed_by to be set "
                "(elektrica.rental_event's rental_event_confirmed_by_required CHECK)."
            )


@dataclass
class RentalProposal:
    """Mirrors elektrica.rental_proposal (migrations/004) -- bot-written,
    per handoff §1.7: never auto-applied to a legal-record field.
    Accepting/rejecting here does NOT touch elektrica.rental; a
    separate app-layer action must insert the corresponding RentalEvent."""
    rental_id: int
    kind: ProposalKind
    proposed_values: dict
    source_system: str
    observed_at: datetime
    evidence: Optional[dict] = None
    status: ProposalStatus = ProposalStatus.PENDING
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


@dataclass
class Toll:
    """Mirrors elektrica.toll (migrations/008) -- handoff §2.3 literal
    spec. Immutable except the confirmed flag after creation."""
    rental_id: int
    tolloptics_record_id: str
    amount: Decimal
    toll_date: date
    confirmed: bool = False
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


@dataclass
class Demand:
    """Mirrors elektrica.demand (migrations/006). status value set and
    carrier_name/adjuster_name are PLACEHOLDER -- see DemandStatus
    docstring and migrations/006 header."""
    rental_id: int
    demand_type: DemandType
    recipient_type: DemandRecipientType
    amount: Decimal
    carrier_name: Optional[str] = None
    adjuster_name: Optional[str] = None
    generated_document_id: Optional[int] = None
    sent_via: Optional[str] = None   # platform.outbound_channel value, kept as str here (cross-schema enum)
    sent_at: Optional[datetime] = None
    status: DemandStatus = DemandStatus.DRAFT
    prior_demand_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    def __post_init__(self):
        # Mirrors demand_carrier_name_required_for_carrier_recipient CHECK.
        if self.recipient_type == DemandRecipientType.CARRIER and not self.carrier_name:
            raise ValueError(
                "recipient_type='carrier' requires carrier_name "
                "(elektrica.demand's demand_carrier_name_required_for_carrier_recipient CHECK)."
            )
        # Mirrors demand_draft_has_no_send_record CHECK.
        if self.status == DemandStatus.DRAFT and (self.sent_via or self.sent_at):
            raise ValueError(
                "status='draft' demands cannot carry sent_via/sent_at "
                "(elektrica.demand's demand_draft_has_no_send_record CHECK)."
            )
        # Mirrors demand_prior_not_self CHECK -- only checkable once id is known,
        # so this branch only fires on manual misuse (id set explicitly and equal).
        if self.prior_demand_id is not None and self.id is not None and self.prior_demand_id == self.id:
            raise ValueError("a demand cannot be its own prior_demand_id.")


@dataclass
class ComparableSet:
    """Mirrors elektrica.comparable_set (migrations/006) -- frozen per
    demand, immutable from creation."""
    demand_id: int
    scan_source: str
    scan_timestamp: datetime
    date_range_start: date
    date_range_end: date
    comparables: list
    computed_average: Decimal
    vehicle_class: Optional[VehicleClass] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None

    def __post_init__(self):
        if self.date_range_end < self.date_range_start:
            raise ValueError(
                "date_range_end must be >= date_range_start "
                "(elektrica.comparable_set's comparable_set_date_range_valid CHECK)."
            )


@dataclass
class Payment:
    """Mirrors elektrica.payment (migrations/008) -- append-only
    financial record, handoff §1.6 literal spec."""
    rental_id: int
    source: PaymentSource
    amount: Decimal
    demand_id: Optional[int] = None
    external_transaction_id: Optional[str] = None
    accounting_sync_ref: Optional[str] = None
    received_at: Optional[datetime] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None

    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError("elektrica.payment.amount must be > 0 (DB CHECK constraint mirrors this).")
        if self.source == PaymentSource.AUTHORIZE_NET and not self.external_transaction_id:
            raise ValueError(
                "source='authorize_net' requires external_transaction_id "
                "(elektrica.payment's payment_external_txn_id_required_for_authorize_net CHECK)."
            )


@dataclass
class ComplianceItem:
    """Mirrors elektrica.compliance_item (migrations/008) -- bot's
    original v1 scope, retained per ADR-001 v2 §3."""
    item_type: ComplianceItemType
    description: str
    expiration_date: date
    vehicle_id: Optional[int] = None
    status: ComplianceItemStatus = ComplianceItemStatus.ACTIVE
    related_document_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


@dataclass
class StaffUser:
    """Mirrors elektrica.staff_user (migrations/011, production). role
    enum CONFIRMED FINAL by Jed (owner/staff)."""
    person_id: int
    role: StaffRole
    google_email: str
    active: bool = True
    provisioned_by_staff_user_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None

    def __post_init__(self):
        email = (self.google_email or "").strip().lower()
        if not email.endswith(f"@{GOOGLE_WORKSPACE_DOMAIN}"):
            raise ValueError(
                f"google_email={self.google_email!r} must end in "
                f"'@{GOOGLE_WORKSPACE_DOMAIN}' (migrations/011's CHECK constraint mirrors this)."
            )
        self.google_email = email


# ---------------------------------------------------------------------------
# platform.document_template / platform.document / platform.outbound_log
# (migrations/005, relocated to platform.* by migrations/009). No app-layer
# code existed for these until now -- a real gap this cycle closes (the
# shared document generator, handoff §1.3, had schema but no Python side).
# ---------------------------------------------------------------------------

class DocumentTemplateFamily(str, Enum):
    """Matches platform.document_template_family (migrations/005, moved to
    platform by migrations/009). Rentals-only value set for now -- VLS/
    Consulting families get added in whichever migration gives them a real
    caller, per migration 009's own "build when needed" discipline."""
    RENTAL_DEMAND = "rental_demand"
    RENTAL_AGREEMENT = "rental_agreement"
    RETURN_AGREEMENT = "return_agreement"
    DV_REQUEST_LETTER = "dv_request_letter"


class OutboundChannel(str, Enum):
    """Matches platform.outbound_channel (migrations/005/009)."""
    FAX = "fax"
    EMAIL = "email"
    SMS = "sms"


@dataclass
class DocumentTemplate:
    """Mirrors platform.document_template. (family, version) is unique --
    is_active marks the current live version per family."""
    family: DocumentTemplateFamily
    version: int
    template_ref: str
    is_active: bool = True
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


@dataclass
class Document:
    """Mirrors platform.document -- an append-only generation log row.
    source_table/source_id are polymorphic (e.g. 'elektrica.rental');
    enforced at the application layer that writes this row, same as
    elektrica.rental_event.source_ref."""
    template_id: int
    source_table: str
    source_id: int
    merge_data: dict
    attachments: list = None  # type: ignore[assignment]
    output_ref: Optional[str] = None
    output_hash: Optional[str] = None
    id: Optional[int] = None
    generated_at: Optional[datetime] = None
    generated_by: Optional[str] = None

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []
        # Mirrors document_output_hash_required_once_generated CHECK.
        if self.output_ref is not None and self.output_hash is None:
            raise ValueError(
                "output_ref set without output_hash "
                "(platform.document's document_output_hash_required_once_generated CHECK)."
            )


@dataclass
class OutboundLog:
    """Mirrors platform.outbound_log -- "generated but never sent" is
    visible precisely because sending is this SEPARATE append-only row,
    not a status flag on Document."""
    document_id: int
    channel: OutboundChannel
    recipient: str
    delivery_confirmation_ref: Optional[str] = None
    id: Optional[int] = None
    sent_at: Optional[datetime] = None
    sent_by: Optional[str] = None


# ---------------------------------------------------------------------------
# platform.communication (migrations/010) -- shared comms timeline, handoff
# §1.5/§2.6. No app-layer code existed for this until now either.
# ---------------------------------------------------------------------------

class CommunicationDirection(str, Enum):
    """Matches platform.communication_direction (migrations/010)."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CommunicationChannel(str, Enum):
    """Matches platform.communication_channel (migrations/010)."""
    CALL = "call"
    EMAIL = "email"
    SMS = "sms"


class CommunicationMatchStatus(str, Enum):
    """Matches platform.communication_match_status (migrations/010).
    'confirmed': human-verified, or an outbound message the app itself
    authored. 'proposed': inbound auto-match by claim number, pending
    human confirmation. 'rejected': a proposed match a human rejected."""
    CONFIRMED = "confirmed"
    PROPOSED = "proposed"
    REJECTED = "rejected"


@dataclass
class Communication:
    """Mirrors platform.communication. Immutable except the one-time
    proposed -> confirmed|rejected decision (migrations/010's
    communication_restrict_update trigger) -- same propose-then-confirm
    shape as elektrica.rental_proposal."""
    source_table: str
    source_id: int
    direction: CommunicationDirection
    channel: CommunicationChannel
    occurred_at: datetime
    source_system: str
    from_ref: Optional[str] = None
    to_ref: Optional[str] = None
    subject: Optional[str] = None
    transcript_ref: Optional[str] = None
    match_status: CommunicationMatchStatus = CommunicationMatchStatus.CONFIRMED
    match_evidence: Optional[dict] = None
    matched_by: Optional[str] = None
    matched_at: Optional[datetime] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None

    def __post_init__(self):
        # Mirrors communication_match_fields_together CHECK exactly:
        # proposed rows carry no matched_by/matched_at yet; every other
        # status requires both (set at write time by the caller/repository,
        # not left to drift out of sync with match_status).
        if self.match_status == CommunicationMatchStatus.PROPOSED:
            if self.matched_by is not None or self.matched_at is not None:
                raise ValueError(
                    "match_status='proposed' rows must not carry matched_by/matched_at "
                    "(platform.communication's communication_match_fields_together CHECK)."
                )
        else:
            if self.matched_by is None or self.matched_at is None:
                raise ValueError(
                    f"match_status={self.match_status.value!r} requires both matched_by and "
                    "matched_at (platform.communication's communication_match_fields_together CHECK)."
                )


# ---------------------------------------------------------------------------
# Rental state sequence -- documentation mirror of
# elektrica.rental_valid_next_states() (migrations/003, updated by 007).
# The DB is the real enforcement (see repository.advance_rental_state());
# this dict exists so app-layer code can pre-validate/display valid next
# states WITHOUT a round trip, same convenience Collision's
# JOB_STATUS_SEQUENCE gives, but as a graph (Elektrica's machine branches
# and loops, unlike Collision's strictly-forward line) rather than a list.
# ---------------------------------------------------------------------------

RENTAL_VALID_NEXT_STATES: dict[RentalState, list[RentalState]] = {
    RentalState.ACTIVE: [RentalState.FINISHED],
    RentalState.FINISHED: [RentalState.NEEDS_DEMAND],
    RentalState.NEEDS_DEMAND: [RentalState.NEEDS_MORE_INFORMATION, RentalState.DEMAND_SENT],
    RentalState.NEEDS_MORE_INFORMATION: [RentalState.NEEDS_DEMAND, RentalState.DEMAND_SENT],
    RentalState.DEMAND_SENT: [RentalState.NEGOTIATING, RentalState.RESOLVED],
    RentalState.NEGOTIATING: [RentalState.NO_OFFER, RentalState.RESOLVED],
    RentalState.NO_OFFER: [RentalState.NEEDS_LAWSUIT, RentalState.RESOLVED],
    RentalState.NEEDS_LAWSUIT: [RentalState.NEEDS_SERVED],
    RentalState.NEEDS_SERVED: [RentalState.IN_LITIGATION],
    RentalState.IN_LITIGATION: [RentalState.RESOLVED],
    RentalState.RESOLVED: [],
}


def validate_rental_transition(current: RentalState, target: RentalState) -> None:
    """Pre-flight check mirroring the DB trigger's logic, for fast
    client-side feedback ONLY. The DB (elektrica.rental_event_enforce_sequence,
    migrations/003 + elektrica.rental_event_check_litigation,
    migrations/007) is the actual source of truth -- this function can
    reject something the DB would also reject, sparing a round trip, but
    must never be more permissive than the DB. It does NOT check the
    in_litigation/resolved vls.case-linkage gate (that requires a DB read
    of vls.case.current_state) -- callers still need the real INSERT to
    catch that."""
    valid = RENTAL_VALID_NEXT_STATES.get(current, [])
    if target not in valid:
        raise ValueError(
            f"Invalid rental state transition: {current.value} -> {target.value}. "
            f"Valid next states: {[s.value for s in valid]}"
        )


# ---------------------------------------------------------------------------
# InsuranceCarrier + Adjuster -- mirrors platform.insurance_carrier /
# platform.adjuster (migrations/013). Handoff §1.4 ("Canonical carrier
# record... Shared between VLS and Elektrica Rentals") / §2.8 ("adjuster:
# carrier_id, name, contact, notes"). No PLACEHOLDER caveat on the SHAPE
# of these two tables (unlike elektrica.vehicle's enums) -- the handoff
# gives their field list verbatim; only the historical *rows* (handoff
# §2.9's import) remain export-blocked, not this schema. See migrations/
# 013's own header comment for the full distinction.
# ---------------------------------------------------------------------------

@dataclass
class InsuranceCarrier:
    """Mirrors platform.insurance_carrier (migrations/013). `name` is the
    canonical carrier name -- unique at the DB level, the "collapse to
    canonical record" mechanism from handoff §2.9.2. Variant names belong
    in `aliases`, not a second row."""
    name: str
    aliases: list[str] = None  # type: ignore[assignment]
    fax: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    claims_mailing_address: Optional[str] = None
    notes: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []
        name = (self.name or "").strip()
        if not name:
            raise ValueError("InsuranceCarrier.name cannot be blank")
        self.name = name


@dataclass
class Adjuster:
    """Mirrors platform.adjuster (migrations/013). Unique per
    (carrier_id, name) at the DB level -- the same adjuster name CAN
    recur at a different carrier (people move employers); that's not a
    duplicate."""
    carrier_id: int
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    def __post_init__(self):
        name = (self.name or "").strip()
        if not name:
            raise ValueError("Adjuster.name cannot be blank")
        self.name = name
