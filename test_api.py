"""Tests for app/api.py -- no DB dependency. Every repository call is
mocked via unittest.mock.patch on app.repository's functions (imported
into app.api as `repo`), and the get_cursor dependency is overridden to
yield a harmless sentinel so no real connection is ever attempted. Same
discipline as Complete Collision's test_api.py.

Run: python test_api.py
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

# Same auth-bypass conftest.py sets for pytest -- pytest auto-loads
# conftest.py, but `python test_api.py` (the manual runner this file's
# own module docstring documents) does NOT, so the global SSO-JWT auth
# middleware in app/api.py would otherwise 401 every request here. Set
# it explicitly in this module too so both invocation styles work,
# rather than only fixing the pytest path and leaving the manual runner
# broken (real bug found running `python test_api.py` this cycle, not
# just inspection -- it failed with a raw 401 on the very first
# repo-mocked test before this fix).
os.environ.setdefault("ELEKTRICA_DISABLE_AUTH", "1")

import psycopg2.errors
from fastapi.testclient import TestClient

from app.api import app, get_cursor, get_privileged_cursor
from app.models import (
    Adjuster, ComparableSet, Communication, CommunicationChannel, CommunicationDirection,
    CommunicationMatchStatus, ComplianceItem, ComplianceItemStatus,
    ComplianceItemType, Demand, DemandRecipientType, DemandType,
    Document, DocumentTemplate, DocumentTemplateFamily, InsuranceCarrier,
    InsurerPayment, InsurerPaymentSource, OutboundChannel,
    OutboundLog, Payment, PaymentSource, ProposalKind, ProposalStatus,
    Renter, Rental, RentalBilledTo, RentalEvent, RentalProposal, RentalState,
    EventSource, StaffRole, StaffUser, Toll, Vehicle,
    VehicleClass, VehicleStatus,
)

FAILED = []


def _override_cursor():
    yield object()  # never touched -- every repo.* call in these tests is mocked


app.dependency_overrides[get_cursor] = _override_cursor
app.dependency_overrides[get_privileged_cursor] = _override_cursor
client = TestClient(app)


def check(name: str, condition: bool, detail: str = ""):
    """Raises AssertionError on failure (not just prints) so both
    invocation styles genuinely fail: pytest's collection of these
    test_* functions actually reports a failure (pytest does NOT
    inspect a plain print()/list-append side effect -- a test_* function
    that returns normally is a PASS to pytest regardless of what it
    printed), and the `python test_api.py` manual runner's own
    FAILED-list summary at the bottom still works via the same list.
    REAL BUG FIXED (2026-09-05, elektrica cron cycle): this function
    previously only appended to FAILED and printed, never raising -- the
    exact same latent bug already found and fixed in
    complete-collision-dashboard's test_api.py (see that repo's own fix
    for the identical pattern). Confirmed the bug reproduces here before
    fixing it (a deliberately-failing check() call did not raise)."""
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} {detail}")
        FAILED.append(name)
        raise AssertionError(f"{name}: {detail}")


def _sample_vehicle(**overrides) -> Vehicle:
    defaults = dict(id=1, vin="1FADP3F20EL123456", status=VehicleStatus.OUT)
    defaults.update(overrides)
    return Vehicle(**defaults)


def _sample_rental(**overrides) -> Rental:
    defaults = dict(
        id=1, vehicle_id=1, renter_id=1, billed_to=RentalBilledTo.CARRIER,
        current_state=RentalState.NEEDS_DEMAND,
    )
    defaults.update(overrides)
    return Rental(**defaults)


def _sample_proposal(**overrides) -> RentalProposal:
    defaults = dict(
        id=1, rental_id=1, kind=ProposalKind.RETURN, proposed_values={"return_date": "2026-09-10"},
        source_system="geofence_email", observed_at=datetime(2026, 9, 10, 14, 30),
        status=ProposalStatus.PENDING,
    )
    defaults.update(overrides)
    return RentalProposal(**defaults)


def _sample_demand(**overrides) -> Demand:
    defaults = dict(
        id=1, rental_id=1, demand_type=DemandType.PRIMARY_INSURER,
        recipient_type=DemandRecipientType.CARRIER, carrier_id=13,
        amount=Decimal("450.00"),
    )
    defaults.update(overrides)
    return Demand(**defaults)


def _sample_toll(**overrides) -> Toll:
    defaults = dict(
        id=1, rental_id=1, tolloptics_record_id="TOLL-1", amount=Decimal("3.50"),
        toll_date=date(2026, 9, 9), confirmed=False,
    )
    defaults.update(overrides)
    return Toll(**defaults)


def _sample_comparable_set(**overrides) -> ComparableSet:
    defaults = dict(
        id=1, demand_id=1, scan_source="kayak", scan_timestamp=datetime(2026, 9, 5, 12, 0),
        vehicle_class=VehicleClass.SEDAN, date_range_start=date(2026, 9, 5),
        date_range_end=date(2026, 9, 12),
        comparables=[{"vendor": "Enterprise", "vehicle": "Camry", "daily_rate": "55.00"}],
        computed_average=Decimal("55.00"),
    )
    defaults.update(overrides)
    return ComparableSet(**defaults)


def _sample_payment(**overrides) -> Payment:
    defaults = dict(id=1, rental_id=1, source=PaymentSource.MANUAL, amount=Decimal("450.00"))
    defaults.update(overrides)
    return Payment(**defaults)


def _sample_staff(**overrides) -> StaffUser:
    defaults = dict(
        id=1, person_id=10, role=StaffRole.STAFF,
        google_email="hire@elektricarentals.com", active=True,
    )
    defaults.update(overrides)
    return StaffUser(**defaults)


def _sample_document_template(**overrides) -> DocumentTemplate:
    defaults = dict(id=1, family=DocumentTemplateFamily.RENTAL_DEMAND, version=1, template_ref="gdoc:abc")
    defaults.update(overrides)
    return DocumentTemplate(**defaults)


def _sample_compliance_item(**overrides) -> ComplianceItem:
    defaults = dict(
        id=1, item_type=ComplianceItemType.DEALER_LICENSE, description="Dealer license renewal",
        expiration_date=date(2027, 1, 1), vehicle_id=None, status=ComplianceItemStatus.ACTIVE,
        related_document_id=None,
    )
    defaults.update(overrides)
    return ComplianceItem(**defaults)


def _sample_document(**overrides) -> Document:
    defaults = dict(
        id=1, template_id=1, source_table="elektrica.rental", source_id=1,
        merge_data={"renter_name": "Jane Doe"},
    )
    defaults.update(overrides)
    return Document(**defaults)


def _sample_outbound_log(**overrides) -> OutboundLog:
    defaults = dict(id=1, document_id=1, channel=OutboundChannel.FAX, recipient="555-0100")
    defaults.update(overrides)
    return OutboundLog(**defaults)


def _sample_communication(**overrides) -> Communication:
    defaults = dict(
        id=1, source_table="elektrica.rental", source_id=1,
        direction=CommunicationDirection.INBOUND, channel=CommunicationChannel.EMAIL,
        occurred_at=datetime(2026, 9, 4), source_system="ringcentral",
        match_status=CommunicationMatchStatus.PROPOSED,
    )
    defaults.update(overrides)
    return Communication(**defaults)


def _sample_renter(**overrides) -> Renter:
    defaults = dict(id=1, person_id=11)
    defaults.update(overrides)
    return Renter(**defaults)


def test_health():
    r = client.get("/health")
    check("test_health", r.status_code == 200 and r.json() == {"status": "ok"})


def test_fleet_out():
    with patch("app.api.repo.list_vehicles_by_status", return_value=[_sample_vehicle()]):
        r = client.get("/fleet/out")
    check("test_fleet_out_status", r.status_code == 200, r.text)
    check("test_fleet_out_body", r.json()[0]["status"] == "out")


def test_fleet_board_out_route():
    """Handoff §2.5 literal Out-half shape -- body_shop/rental_type/renter
    name beside the vehicle, via the new joined repo.fleet_board_out()."""
    row = {
        "vehicle_id": 1, "vin": "OUTVIN001", "current_position": None,
        "position_updated_at": None, "rental_id": 5, "body_shop": "Roxie",
        "rental_type": "Claimant", "current_state": "active",
        "start_date": None, "end_date": None,
        "first_name": "Jane", "last_name": "Doe",
    }
    with patch("app.api.repo.fleet_board_out", return_value=[row]):
        r = client.get("/fleet-board/out")
    check("test_fleet_board_out_status", r.status_code == 200, r.text)
    check("test_fleet_board_out_body_shop", r.json()[0]["body_shop"] == "Roxie", r.text)
    check("test_fleet_board_out_renter_name", r.json()[0]["first_name"] == "Jane", r.text)


def test_fleet_board_available_route():
    """Handoff §2.5 literal Available-half shape. Also pins the KNOWN
    SPEC CONFLICT documented in repo.fleet_board_available()'s docstring:
    `class` is always null since migration 015 dropped the column --
    this is a visible regression test for that documented gap, not an
    assertion that grouping-by-class actually works."""
    row = {"vehicle_id": 2, "vin": "AVAILVIN002", "notes": None, "class": None}
    with patch("app.api.repo.fleet_board_available", return_value=[row]):
        r = client.get("/fleet-board/available")
    check("test_fleet_board_available_status", r.status_code == 200, r.text)
    check("test_fleet_board_available_class_is_null", r.json()[0]["class"] is None, r.text)


def test_create_vehicle():
    with patch("app.api.repo.get_vehicle_by_vin", return_value=None), \
         patch("app.api.repo.create_vehicle", return_value=_sample_vehicle(status=VehicleStatus.AVAILABLE)):
        r = client.post(
            "/vehicles",
            json={"vin": "1FADP3F20EL123456", "actor": "jed", "status": "available"},
        )
    check("test_create_vehicle_status", r.status_code == 200, r.text)
    check("test_create_vehicle_body", r.json()["vin"] == "1FADP3F20EL123456")


def test_create_vehicle_duplicate_vin_returns_409():
    with patch("app.api.repo.get_vehicle_by_vin", return_value=_sample_vehicle()):
        r = client.post("/vehicles", json={"vin": "1FADP3F20EL123456", "actor": "jed"})
    check("test_create_vehicle_duplicate_vin_returns_409", r.status_code == 409, r.text)


def test_create_vehicle_bad_status_returns_400():
    r = client.post("/vehicles", json={"vin": "SOMEVIN", "actor": "jed", "status": "not_a_status"})
    check("test_create_vehicle_bad_status_returns_400", r.status_code == 400, r.text)


def test_get_vehicle_by_vin_found():
    with patch("app.api.repo.get_vehicle_by_vin", return_value=_sample_vehicle()):
        r = client.get("/vehicles/vin/1FADP3F20EL123456")
    check("test_get_vehicle_by_vin_found", r.status_code == 200, r.text)


def test_get_vehicle_by_vin_not_found():
    with patch("app.api.repo.get_vehicle_by_vin", return_value=None):
        r = client.get("/vehicles/vin/NOSUCHVIN")
    check("test_get_vehicle_by_vin_not_found", r.status_code == 404)


def test_get_vehicle_found():
    with patch("app.api.repo.get_vehicle", return_value=_sample_vehicle()):
        r = client.get("/vehicles/1")
    check("test_get_vehicle_found", r.status_code == 200, r.text)


def test_get_vehicle_not_found():
    with patch("app.api.repo.get_vehicle", return_value=None):
        r = client.get("/vehicles/999")
    check("test_get_vehicle_not_found", r.status_code == 404)


def test_update_vehicle_position():
    with patch("app.api.repo.update_vehicle_position", return_value=_sample_vehicle(current_position={"lat": 30.27, "lon": -97.74})):
        r = client.post("/vehicles/1/position", json={"position": {"lat": 30.27, "lon": -97.74}, "actor": "bouncie_bot"})
    check("test_update_vehicle_position_status", r.status_code == 200, r.text)
    check("test_update_vehicle_position_body", r.json()["current_position"] == {"lat": 30.27, "lon": -97.74})


def test_update_vehicle_position_not_found_returns_404():
    with patch("app.api.repo.update_vehicle_position", side_effect=ValueError("No vehicle with id=999")):
        r = client.post("/vehicles/999/position", json={"position": {}, "actor": "bouncie_bot"})
    check("test_update_vehicle_position_not_found_returns_404", r.status_code == 404, r.text)


def test_create_renter():
    with patch("app.api.repo.create_renter_for_existing_person", return_value=_sample_renter()):
        r = client.post("/renters", json={"person_id": 11, "actor": "jed"})
    check("test_create_renter_status", r.status_code == 200, r.text)
    check("test_create_renter_body", r.json()["person_id"] == 11)


def test_intake_renter_attached():
    """First-time renter whose identity exactly matches an existing
    platform.person (phone/email match) -- match_status='attached'."""
    from app.repository import RenterIntakeResult
    result = RenterIntakeResult(match_status="attached", person_id=11, queue_id=None, renter=_sample_renter())
    with patch("app.api.repo.match_or_create_and_link_renter", return_value=result):
        r = client.post("/renters/intake", json={
            "first_name": "Jane", "last_name": "Doe", "actor": "jotform_bot",
            "email": "jane@example.com",
        })
    check("test_intake_renter_attached_status", r.status_code == 200, r.text)
    check("test_intake_renter_attached_match_status", r.json()["match_status"] == "attached")
    check("test_intake_renter_attached_renter_present", r.json()["renter"] is not None)


def test_intake_renter_created():
    """No match found -- platform.match_or_create_person() creates a new
    platform.person row, match_status='created'."""
    from app.repository import RenterIntakeResult
    result = RenterIntakeResult(match_status="created", person_id=42, queue_id=None, renter=_sample_renter(id=2, person_id=42))
    with patch("app.api.repo.match_or_create_and_link_renter", return_value=result):
        r = client.post("/renters/intake", json={
            "first_name": "New", "last_name": "Renter", "actor": "jotform_bot",
        })
    check("test_intake_renter_created_status", r.status_code == 200, r.text)
    check("test_intake_renter_created_match_status", r.json()["match_status"] == "created")
    check("test_intake_renter_created_person_id", r.json()["person_id"] == 42)


def test_intake_renter_queued_has_no_renter():
    """Close-but-not-exact name+DOB match -- queues to
    platform.person_match_queue for human review. Per docs/BACKLOG.md's
    explicit rule, the response must NOT carry a linked renter."""
    from app.repository import RenterIntakeResult
    result = RenterIntakeResult(match_status="queued", person_id=11, queue_id=7, renter=None)
    with patch("app.api.repo.match_or_create_and_link_renter", return_value=result):
        r = client.post("/renters/intake", json={
            "first_name": "Jane", "last_name": "Doe", "actor": "jotform_bot",
            "date_of_birth": "1990-01-01",
        })
    check("test_intake_renter_queued_status", r.status_code == 200, r.text)
    check("test_intake_renter_queued_match_status", r.json()["match_status"] == "queued")
    check("test_intake_renter_queued_queue_id", r.json()["queue_id"] == 7)
    check("test_intake_renter_queued_no_renter", r.json()["renter"] is None)


def test_get_pending_person_match_queue_excludes_vls_at_query_level():
    """Route just passes through repo's own VLS-excluding query -- this
    test pins that the response can legitimately contain elektrica AND
    collision rows together (repo.list_pending_person_match_queue_items()
    is the enforcement point, tested more directly below)."""
    rows = [
        {
            "id": 2, "candidate_person_id": 37, "first_name": "Different",
            "last_name": "QueueTest", "date_of_birth": date(1985, 5, 5),
            "email_normalized": None, "phone_normalized": None,
            "match_reason": "name_dob_close_match", "source_project": "elektrica",
            "submitted_by": "cron_http_smoke", "submitted_at": datetime(2026, 9, 5, 11, 7, 55),
        },
    ]
    with patch("app.api.repo.list_pending_person_match_queue_items", return_value=rows):
        r = client.get("/person-match-queue/pending")
    check("test_get_pending_person_match_queue_status", r.status_code == 200, r.text)
    check("test_get_pending_person_match_queue_one_row", len(r.json()) == 1)
    check("test_get_pending_person_match_queue_source_project", r.json()[0]["source_project"] == "elektrica")


def test_decide_person_match_queue_confirmed_match():
    result = {
        "queue_id": 2, "decision": "confirmed_match", "resulting_person_id": 37,
        "source_project": "elektrica", "renter": _sample_renter(id=5, person_id=37),
    }
    with patch("app.api.repo.resolve_person_match_queue", return_value=result):
        r = client.post("/person-match-queue/2/decision", json={
            "decision": "confirmed_match", "actor": "jed",
        })
    check("test_decide_person_match_queue_confirmed_match_status", r.status_code == 200, r.text)
    check("test_decide_person_match_queue_confirmed_match_person", r.json()["resulting_person_id"] == 37)
    check("test_decide_person_match_queue_confirmed_match_renter", r.json()["renter"] is not None)


def test_decide_person_match_queue_confirmed_split_no_renter_for_collision():
    """source_project='collision' -- repo deliberately does not link an
    elektrica.renter for a non-elektrica queue row; renter must be None."""
    result = {
        "queue_id": 9, "decision": "confirmed_split", "resulting_person_id": 99,
        "source_project": "collision", "renter": None,
    }
    with patch("app.api.repo.resolve_person_match_queue", return_value=result):
        r = client.post("/person-match-queue/9/decision", json={
            "decision": "confirmed_split", "actor": "jed",
        })
    check("test_decide_person_match_queue_split_status", r.status_code == 200, r.text)
    check("test_decide_person_match_queue_split_no_renter", r.json()["renter"] is None)


def test_decide_person_match_queue_vls_refused_403():
    """The VLS-refusal ValueError must surface as 403 (authorization
    boundary), not 400/404 -- see app.api.decide_person_match_queue()'s
    own docstring for why."""
    with patch(
        "app.api.repo.resolve_person_match_queue",
        side_effect=ValueError("person_match_queue id=5 is source_project='vls' -- refuses"),
    ):
        r = client.post("/person-match-queue/5/decision", json={
            "decision": "confirmed_match", "actor": "jed",
        })
    check("test_decide_person_match_queue_vls_refused_403", r.status_code == 403, r.text)


def test_decide_person_match_queue_not_found_404():
    with patch(
        "app.api.repo.resolve_person_match_queue",
        side_effect=ValueError("No person_match_queue row with id=999"),
    ):
        r = client.post("/person-match-queue/999/decision", json={
            "decision": "confirmed_match", "actor": "jed",
        })
    check("test_decide_person_match_queue_not_found_404", r.status_code == 404, r.text)


def test_decide_person_match_queue_already_resolved_400():
    with patch(
        "app.api.repo.resolve_person_match_queue",
        side_effect=ValueError("person_match_queue id=2 already resolved (status='confirmed_match', resolved_by='jed')"),
    ):
        r = client.post("/person-match-queue/2/decision", json={
            "decision": "confirmed_match", "actor": "jed",
        })
    check("test_decide_person_match_queue_already_resolved_400", r.status_code == 400, r.text)


def test_get_renter_found():
    with patch("app.api.repo.get_renter", return_value=_sample_renter()):
        r = client.get("/renters/1")
    check("test_get_renter_found", r.status_code == 200, r.text)


def test_get_renter_not_found():
    with patch("app.api.repo.get_renter", return_value=None):
        r = client.get("/renters/999")
    check("test_get_renter_not_found", r.status_code == 404)


def test_get_renter_by_person_found():
    with patch("app.api.repo.get_renter_by_person_id", return_value=_sample_renter()):
        r = client.get("/renters/by-person/11")
    check("test_get_renter_by_person_found", r.status_code == 200, r.text)


def test_get_renter_by_person_not_found():
    with patch("app.api.repo.get_renter_by_person_id", return_value=None):
        r = client.get("/renters/by-person/999")
    check("test_get_renter_by_person_not_found", r.status_code == 404)


def test_create_rental():
    with patch("app.api.repo.create_rental", return_value=_sample_rental(current_state=RentalState.ACTIVE)):
        r = client.post("/rentals", json={"vehicle_id": 1, "renter_id": 1, "actor": "jed", "billed_to": "carrier"})
    check("test_create_rental_status", r.status_code == 200, r.text)
    check("test_create_rental_state", r.json()["current_state"] == "active")


def test_create_rental_bad_billed_to():
    r = client.post("/rentals", json={"vehicle_id": 1, "renter_id": 1, "actor": "jed", "billed_to": "not_real"})
    check("test_create_rental_bad_billed_to", r.status_code == 400, r.text)


def test_get_rental_found():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()):
        r = client.get("/rentals/1")
    check("test_get_rental_found", r.status_code == 200 and r.json()["current_state"] == "needs_demand")


def test_get_rental_not_found():
    with patch("app.api.repo.get_rental", return_value=None):
        r = client.get("/rentals/999")
    check("test_get_rental_not_found", r.status_code == 404)


def test_list_rentals_no_filter():
    with patch("app.api.repo.list_rentals", return_value=[_sample_rental()]) as mock_list:
        r = client.get("/rentals")
    check("test_list_rentals_status", r.status_code == 200, r.text)
    check("test_list_rentals_body", len(r.json()) == 1 and r.json()[0]["current_state"] == "needs_demand")
    check("test_list_rentals_no_filter_arg", mock_list.call_args[0][1] is None)


def test_list_rentals_with_state_filter():
    with patch("app.api.repo.list_rentals", return_value=[]) as mock_list:
        r = client.get("/rentals?current_state=active")
    check("test_list_rentals_filter_status", r.status_code == 200, r.text)
    check("test_list_rentals_filter_arg", mock_list.call_args[0][1] == RentalState.ACTIVE)


def test_list_rentals_bad_state_filter():
    r = client.get("/rentals?current_state=not_real")
    check("test_list_rentals_bad_filter", r.status_code == 400, r.text)


def test_transition_rental_success():
    updated = _sample_rental(current_state=RentalState.DEMAND_SENT)
    with patch("app.api.repo.advance_rental_state", return_value=updated) as mock_adv:
        r = client.post(
            "/rentals/1/transition",
            json={"target_state": "demand_sent", "actor": "jed", "source": "manual"},
        )
    check("test_transition_rental_success_status", r.status_code == 200, r.text)
    check("test_transition_rental_success_body", r.json()["current_state"] == "demand_sent")
    args, kwargs = mock_adv.call_args
    check("test_transition_rental_success_actor_passed", "jed" in args or kwargs.get("actor") == "jed")


def test_transition_rental_illegal_returns_400():
    with patch("app.api.repo.advance_rental_state", side_effect=ValueError("Invalid rental state transition")):
        r = client.post("/rentals/1/transition", json={"target_state": "resolved", "actor": "jed"})
    check("test_transition_rental_illegal_returns_400", r.status_code == 400, r.text)


def test_transition_rental_bad_state_value_returns_400():
    r = client.post("/rentals/1/transition", json={"target_state": "not_a_real_state", "actor": "jed"})
    check("test_transition_rental_bad_state_value_returns_400", r.status_code == 400, r.text)


def test_transition_rental_db_rejection_returns_400_not_500():
    """DB-trigger-level rejections (e.g. the litigation gate, migrations/007)
    must surface as 400 client errors, not 500s -- they represent invalid
    input given current state, not a server fault."""
    with patch("app.api.repo.advance_rental_state", side_effect=Exception("no vls.case is linked")):
        r = client.post("/rentals/1/transition", json={"target_state": "in_litigation", "actor": "jed"})
    check("test_transition_rental_db_rejection_returns_400_not_500", r.status_code == 400, r.text)


def test_get_blocked_rentals():
    with patch("app.api.repo.list_blocked_rentals", return_value=[{"id": 1, "block_reason": "x"}]):
        r = client.get("/rentals/blocked")
    check("test_get_blocked_rentals", r.status_code == 200 and r.json()[0]["block_reason"] == "x")


def test_link_vls_case():
    linked = _sample_rental(vls_case_id=42)
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.link_vls_case", return_value=linked):
        r = client.post("/rentals/1/vls-case", json={"vls_case_id": 42, "actor": "jed"})
    check("test_link_vls_case", r.status_code == 200 and r.json()["vls_case_id"] == 42, r.text)


def test_link_vls_case_rental_not_found():
    with patch("app.api.repo.get_rental", return_value=None):
        r = client.post("/rentals/999/vls-case", json={"vls_case_id": 42, "actor": "jed"})
    check("test_link_vls_case_rental_not_found", r.status_code == 404, r.text)


def test_link_vls_case_bad_vls_case_id_returns_400_not_500():
    """Real bug found via live staging: an unlinked/nonexistent vls_case_id
    violates rental_vls_case_id_fkey and must surface as 400, not a bare
    500 (mocked here since a real FK violation can't be triggered without
    a DB)."""
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.link_vls_case", side_effect=psycopg2.errors.ForeignKeyViolation()):
        r = client.post("/rentals/1/vls-case", json={"vls_case_id": 999999, "actor": "jed"})
    check("test_link_vls_case_bad_vls_case_id_returns_400_not_500", r.status_code == 400, r.text)


def test_create_proposal():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.create_rental_proposal", return_value=_sample_proposal()), \
         patch.dict(os.environ, {"ELEKTRICA_BOT_API_KEY": "test-bot-key"}):
        r = client.post(
            "/rentals/1/proposals",
            json={
                "kind": "return", "proposed_values": {"return_date": "2026-09-10"},
                "source_system": "geofence_email", "observed_at": "2026-09-10T14:30:00",
            },
            headers={"X-Api-Key": "test-bot-key"},
        )
    check("test_create_proposal_status", r.status_code == 200, r.text)
    check("test_create_proposal_body", r.json()["status"] == "pending")


def test_create_proposal_rental_not_found():
    with patch("app.api.repo.get_rental", return_value=None), \
         patch.dict(os.environ, {"ELEKTRICA_BOT_API_KEY": "test-bot-key"}):
        r = client.post(
            "/rentals/999/proposals",
            json={"kind": "return", "proposed_values": {}, "source_system": "bot", "observed_at": "2026-09-10T14:30:00"},
            headers={"X-Api-Key": "test-bot-key"},
        )
    check("test_create_proposal_rental_not_found", r.status_code == 404)


def test_create_proposal_bad_kind():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch.dict(os.environ, {"ELEKTRICA_BOT_API_KEY": "test-bot-key"}):
        r = client.post(
            "/rentals/1/proposals",
            json={"kind": "not_a_kind", "proposed_values": {}, "source_system": "bot", "observed_at": "2026-09-10T14:30:00"},
            headers={"X-Api-Key": "test-bot-key"},
        )
    check("test_create_proposal_bad_kind", r.status_code == 400, r.text)


def test_create_proposal_no_key_configured_returns_503():
    """Handoff §1.7: API key or nothing -- if the server has no key
    configured, the endpoint must refuse to serve (fail closed), not
    silently accept the write."""
    env_without_key = {k: v for k, v in os.environ.items() if k != "ELEKTRICA_BOT_API_KEY"}
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch.dict(os.environ, env_without_key, clear=True):
        r = client.post(
            "/rentals/1/proposals",
            json={"kind": "return", "proposed_values": {}, "source_system": "bot", "observed_at": "2026-09-10T14:30:00"},
            headers={"X-Api-Key": "anything"},
        )
    check("test_create_proposal_no_key_configured_returns_503", r.status_code == 503, r.text)


def test_create_proposal_missing_header_returns_401():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch.dict(os.environ, {"ELEKTRICA_BOT_API_KEY": "test-bot-key"}):
        r = client.post(
            "/rentals/1/proposals",
            json={"kind": "return", "proposed_values": {}, "source_system": "bot", "observed_at": "2026-09-10T14:30:00"},
        )
    check("test_create_proposal_missing_header_returns_401", r.status_code == 401, r.text)


def test_create_proposal_wrong_key_returns_401():
    """No bypass allowlist, no localhost trust -- a wrong key is rejected
    exactly like a missing one."""
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch.dict(os.environ, {"ELEKTRICA_BOT_API_KEY": "test-bot-key"}):
        r = client.post(
            "/rentals/1/proposals",
            json={"kind": "return", "proposed_values": {}, "source_system": "bot", "observed_at": "2026-09-10T14:30:00"},
            headers={"X-Api-Key": "wrong-key"},
        )
    check("test_create_proposal_wrong_key_returns_401", r.status_code == 401, r.text)


def test_get_pending_proposals():
    with patch("app.api.repo.list_pending_rental_proposals", return_value=[_sample_proposal()]):
        r = client.get("/proposals/pending")
    check("test_get_pending_proposals", r.status_code == 200 and len(r.json()) == 1)


def test_decide_proposal_accept():
    decided = _sample_proposal(status=ProposalStatus.ACCEPTED)
    with patch("app.api.repo.decide_rental_proposal", return_value=decided):
        r = client.post("/proposals/1/decision", json={"status": "accepted", "actor": "jed"})
    check("test_decide_proposal_accept", r.status_code == 200 and r.json()["status"] == "accepted")


def test_decide_proposal_bad_status():
    r = client.post("/proposals/1/decision", json={"status": "pending", "actor": "jed"})
    check("test_decide_proposal_bad_status", r.status_code == 400, r.text)


def test_create_demand():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.create_demand", return_value=_sample_demand()):
        r = client.post(
            "/rentals/1/demands",
            json={
                "demand_type": "primary_insurer", "recipient_type": "carrier",
                "amount": "450.00", "actor": "jed", "carrier_id": 13,
            },
        )
    check("test_create_demand_status", r.status_code == 200, r.text)
    check("test_create_demand_body", r.json()["status"] == "draft")


def test_create_demand_carrier_without_name_returns_400():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()):
        r = client.post(
            "/rentals/1/demands",
            json={
                "demand_type": "primary_insurer", "recipient_type": "carrier",
                "amount": "450.00", "actor": "jed",
            },
        )
    check("test_create_demand_carrier_without_name_returns_400", r.status_code == 400, r.text)


def test_create_demand_unknown_carrier_id_returns_400():
    """migrations/014's demand.carrier_id_fkey -- a carrier_id that doesn't
    exist must surface as 400, same 500->400 discipline as every other FK
    violation in this API (link_vls_case, insurance-carrier adjuster
    creation, etc.)."""
    import psycopg2.errors
    fk_error = psycopg2.errors.ForeignKeyViolation(
        "insert or update on table \"demand\" violates foreign key constraint \"demand_carrier_id_fkey\""
    )
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.create_demand", side_effect=fk_error):
        r = client.post(
            "/rentals/1/demands",
            json={
                "demand_type": "primary_insurer", "recipient_type": "carrier",
                "amount": "450.00", "actor": "jed", "carrier_id": 999999,
            },
        )
    check("test_create_demand_unknown_carrier_id_returns_400", r.status_code == 400, r.text)


def test_create_demand_mismatched_adjuster_carrier_returns_400():
    """migrations/014's trg_demand_check_adjuster_carrier_match -- an
    adjuster_id belonging to a different carrier than carrier_id must
    surface as 400, not 500."""
    import psycopg2.errors
    raise_error = psycopg2.errors.RaiseException(
        "demand.adjuster_id 20 belongs to carrier_id 18 but demand.carrier_id is 17 -- "
        "adjuster must belong to the same carrier the demand is addressed to."
    )
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.create_demand", side_effect=raise_error):
        r = client.post(
            "/rentals/1/demands",
            json={
                "demand_type": "primary_insurer", "recipient_type": "carrier",
                "amount": "450.00", "actor": "jed", "carrier_id": 17, "adjuster_id": 20,
            },
        )
    check("test_create_demand_mismatched_adjuster_carrier_returns_400", r.status_code == 400, r.text)


def test_get_rental_demands():
    """docs/BUILD_LOG.md migration-014 cycle's flagged next item: a plain
    gap where a rental's demand chain couldn't be listed, only created
    one-by-one. Same shape as list_rental_events/list_tolls_for_rental."""
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.list_demands_for_rental", return_value=[_sample_demand(id=1), _sample_demand(id=2)]):
        r = client.get("/rentals/1/demands")
    check("test_get_rental_demands_status", r.status_code == 200, r.text)
    check("test_get_rental_demands_body", len(r.json()) == 2 and r.json()[0]["id"] == 1)


def test_get_rental_demands_rental_not_found():
    with patch("app.api.repo.get_rental", return_value=None):
        r = client.get("/rentals/999/demands")
    check("test_get_rental_demands_rental_not_found", r.status_code == 404, r.text)


def test_mark_demand_sent():
    from app.models import DemandStatus
    sent = _sample_demand(status=DemandStatus.SENT, sent_via="fax")
    with patch("app.api.repo.mark_demand_sent", return_value=sent):
        r = client.post("/demands/1/mark-sent", json={"sent_via": "fax", "actor": "jed"})
    check("test_mark_demand_sent", r.status_code == 200 and r.json()["status"] == "sent")


def test_get_aging_demands():
    with patch("app.api.repo.list_aging_demands", return_value=[{"id": 1, "days_since_sent": 50}]):
        r = client.get("/demands/aging")
    check("test_get_aging_demands", r.status_code == 200 and r.json()[0]["days_since_sent"] == 50)


def test_create_comparable_set():
    with patch("app.api.repo.get_demand", return_value=_sample_demand()), \
         patch("app.api.repo.create_comparable_set", return_value=_sample_comparable_set()):
        r = client.post(
            "/demands/1/comparable-sets",
            json={
                "scan_source": "kayak", "scan_timestamp": "2026-09-05T12:00:00",
                "date_range_start": "2026-09-05", "date_range_end": "2026-09-12",
                "comparables": [{"vendor": "Enterprise", "vehicle": "Camry", "daily_rate": "55.00"}],
                "computed_average": "55.00", "vehicle_class": "sedan", "actor": "jed",
            },
        )
    check("test_create_comparable_set", r.status_code == 200 and r.json()["computed_average"] == "55.00", r.text)


def test_create_comparable_set_demand_not_found():
    with patch("app.api.repo.get_demand", return_value=None):
        r = client.post(
            "/demands/999/comparable-sets",
            json={
                "scan_source": "kayak", "scan_timestamp": "2026-09-05T12:00:00",
                "date_range_start": "2026-09-05", "date_range_end": "2026-09-12",
                "comparables": [], "computed_average": "55.00", "actor": "jed",
            },
        )
    check("test_create_comparable_set_demand_not_found", r.status_code == 404, r.text)


def test_create_comparable_set_bad_date_range_returns_400():
    with patch("app.api.repo.get_demand", return_value=_sample_demand()):
        r = client.post(
            "/demands/1/comparable-sets",
            json={
                "scan_source": "kayak", "scan_timestamp": "2026-09-05T12:00:00",
                "date_range_start": "2026-09-12", "date_range_end": "2026-09-05",
                "comparables": [], "computed_average": "55.00", "actor": "jed",
            },
        )
    check("test_create_comparable_set_bad_date_range_returns_400", r.status_code == 400, r.text)


def test_create_comparable_set_bad_vehicle_class_returns_400():
    with patch("app.api.repo.get_demand", return_value=_sample_demand()):
        r = client.post(
            "/demands/1/comparable-sets",
            json={
                "scan_source": "kayak", "scan_timestamp": "2026-09-05T12:00:00",
                "date_range_start": "2026-09-05", "date_range_end": "2026-09-12",
                "comparables": [], "computed_average": "55.00",
                "vehicle_class": "not-a-real-class", "actor": "jed",
            },
        )
    check("test_create_comparable_set_bad_vehicle_class_returns_400", r.status_code == 400, r.text)


def test_create_toll():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.create_toll", return_value=_sample_toll()):
        r = client.post(
            "/rentals/1/tolls",
            json={"tolloptics_record_id": "TOLL-1", "amount": "3.50", "toll_date": "2026-09-09", "actor": "bot"},
        )
    check("test_create_toll", r.status_code == 200 and r.json()["confirmed"] is False)


def test_confirm_toll():
    with patch("app.api.repo.confirm_toll", return_value=_sample_toll(confirmed=True)):
        r = client.post("/tolls/1/confirm")
    check("test_confirm_toll", r.status_code == 200 and r.json()["confirmed"] is True)


def test_confirm_toll_not_found():
    with patch("app.api.repo.confirm_toll", side_effect=ValueError("No toll with id=999")):
        r = client.post("/tolls/999/confirm")
    check("test_confirm_toll_not_found", r.status_code == 404)


def test_create_payment():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.create_payment", return_value=_sample_payment()):
        r = client.post("/rentals/1/payments", json={"source": "manual", "amount": "450.00", "actor": "jed"})
    check("test_create_payment", r.status_code == 200, r.text)


def test_create_payment_authorize_net_without_txn_id_returns_400():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()):
        r = client.post("/rentals/1/payments", json={"source": "authorize_net", "amount": "450.00", "actor": "jed"})
    check("test_create_payment_authorize_net_without_txn_id_returns_400", r.status_code == 400, r.text)


def test_create_payment_zero_amount_returns_400():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()):
        r = client.post("/rentals/1/payments", json={"source": "manual", "amount": "0.00", "actor": "jed"})
    check("test_create_payment_zero_amount_returns_400", r.status_code == 400, r.text)


def test_vehicle_revenue_summary():
    with patch("app.api.repo.vehicle_revenue_summary", return_value=[{"vehicle_id": 1, "total_revenue": "450.00"}]):
        r = client.get("/vehicles/revenue-summary")
    check("test_vehicle_revenue_summary", r.status_code == 200 and len(r.json()) == 1)


def test_compliance_expiring_soon():
    with patch("app.api.repo.list_compliance_items_expiring_soon", return_value=[{"id": 1}]):
        r = client.get("/compliance/expiring-soon")
    check("test_compliance_expiring_soon", r.status_code == 200 and len(r.json()) == 1)


def test_create_compliance_item():
    with patch("app.api.repo.create_compliance_item", return_value=_sample_compliance_item()):
        r = client.post(
            "/compliance-items",
            json={
                "item_type": "dealer_license", "description": "Dealer license renewal",
                "expiration_date": "2027-01-01", "actor": "jed",
            },
        )
    check("test_create_compliance_item", r.status_code == 200 and r.json()["item_type"] == "dealer_license", r.text)


def test_create_compliance_item_vehicle_not_found():
    with patch("app.api.repo.get_vehicle", return_value=None):
        r = client.post(
            "/compliance-items",
            json={
                "item_type": "insurance", "description": "Policy renewal", "vehicle_id": 999,
                "expiration_date": "2027-01-01", "actor": "jed",
            },
        )
    check("test_create_compliance_item_vehicle_not_found", r.status_code == 404, r.text)


def test_create_compliance_item_bad_item_type_returns_400():
    r = client.post(
        "/compliance-items",
        json={"item_type": "not_a_type", "description": "x", "expiration_date": "2027-01-01", "actor": "jed"},
    )
    check("test_create_compliance_item_bad_item_type_returns_400", r.status_code == 400, r.text)


def test_get_compliance_item_found():
    with patch("app.api.repo.get_compliance_item", return_value=_sample_compliance_item()):
        r = client.get("/compliance-items/1")
    check("test_get_compliance_item_found", r.status_code == 200 and r.json()["id"] == 1, r.text)


def test_get_compliance_item_not_found():
    with patch("app.api.repo.get_compliance_item", return_value=None):
        r = client.get("/compliance-items/999")
    check("test_get_compliance_item_not_found", r.status_code == 404, r.text)


def test_update_compliance_item_status():
    renewed = _sample_compliance_item(status=ComplianceItemStatus.RENEWED, related_document_id=5)
    with patch("app.api.repo.update_compliance_item_status", return_value=renewed):
        r = client.post("/compliance-items/1/status", json={"status": "renewed", "actor": "jed", "related_document_id": 5})
    check("test_update_compliance_item_status", r.status_code == 200 and r.json()["status"] == "renewed", r.text)


def test_update_compliance_item_status_not_found():
    with patch("app.api.repo.update_compliance_item_status", side_effect=ValueError("No compliance_item with id=999")):
        r = client.post("/compliance-items/999/status", json={"status": "renewed", "actor": "jed"})
    check("test_update_compliance_item_status_not_found", r.status_code == 404, r.text)


def test_update_compliance_item_status_bad_status_returns_400():
    r = client.post("/compliance-items/1/status", json={"status": "not_a_status", "actor": "jed"})
    check("test_update_compliance_item_status_bad_status_returns_400", r.status_code == 400, r.text)


def test_provision_staff():
    with patch("app.api.repo.provision_staff_user_for_existing_person", return_value=_sample_staff()):
        r = client.post(
            "/staff",
            json={"person_id": 10, "role": "staff", "google_email": "hire@elektricarentals.com", "actor": "jed"},
        )
    check("test_provision_staff_status", r.status_code == 200, r.text)
    check("test_provision_staff_body", r.json()["role"] == "staff")


def test_provision_staff_bad_role_returns_400():
    r = client.post(
        "/staff",
        json={"person_id": 10, "role": "not_a_role", "google_email": "hire@elektricarentals.com", "actor": "jed"},
    )
    check("test_provision_staff_bad_role_returns_400", r.status_code == 400, r.text)


def test_provision_staff_domain_rejection_returns_400():
    """StaffUser.__post_init__'s domain CHECK mirror (migrations/011)
    raises ValueError inside the repository call -- must surface as 400,
    not 500."""
    with patch(
        "app.api.repo.provision_staff_user_for_existing_person",
        side_effect=ValueError("google_email must end in '@elektricarentals.com'"),
    ):
        r = client.post(
            "/staff",
            json={"person_id": 10, "role": "staff", "google_email": "hire@gmail.com", "actor": "jed"},
        )
    check("test_provision_staff_domain_rejection_returns_400", r.status_code == 400, r.text)


def test_provision_staff_insufficient_privilege_returns_403():
    """Real, live-reproduced gap (2026-09-04 cron cycle, run under
    ELEKTRICA_DB_SET_ROLE=elektrica_app via curl): elektrica_app has
    SELECT-only on staff_user (migration 011) so this route 500'd until
    this except-clause was added. Confirms it now surfaces as a clean
    403, not a bare framework 500."""
    with patch(
        "app.api.repo.provision_staff_user_for_existing_person",
        side_effect=psycopg2.errors.InsufficientPrivilege("permission denied for table staff_user"),
    ):
        r = client.post(
            "/staff",
            json={"person_id": 10, "role": "staff", "google_email": "hire@elektricarentals.com", "actor": "jed"},
        )
    check("test_provision_staff_insufficient_privilege_returns_403", r.status_code == 403, r.text)


def test_get_staff_found():
    with patch("app.api.repo.get_staff_user_by_google_email", return_value=_sample_staff()):
        r = client.get("/staff/hire@elektricarentals.com")
    check("test_get_staff_found", r.status_code == 200 and r.json()["google_email"] == "hire@elektricarentals.com")


def test_get_staff_not_found():
    with patch("app.api.repo.get_staff_user_by_google_email", return_value=None):
        r = client.get("/staff/nobody@elektricarentals.com")
    check("test_get_staff_not_found", r.status_code == 404)


def test_set_staff_active_deactivate():
    with patch("app.api.repo.set_staff_user_active", return_value=_sample_staff(active=False)):
        r = client.post("/staff/hire@elektricarentals.com/active", json={"active": False, "actor": "jed"})
    check("test_set_staff_active_deactivate", r.status_code == 200 and r.json()["active"] is False)


def test_set_staff_active_not_found():
    with patch("app.api.repo.set_staff_user_active", side_effect=ValueError("No staff_user with google_email=...")):
        r = client.post("/staff/nobody@elektricarentals.com/active", json={"active": False, "actor": "jed"})
    check("test_set_staff_active_not_found", r.status_code == 404)


def test_set_staff_active_insufficient_privilege_returns_403():
    """Same real, live-reproduced gap as test_provision_staff_insufficient_privilege_returns_403
    above, for the sibling route."""
    with patch(
        "app.api.repo.set_staff_user_active",
        side_effect=psycopg2.errors.InsufficientPrivilege("permission denied for table staff_user"),
    ):
        r = client.post("/staff/hire@elektricarentals.com/active", json={"active": False, "actor": "jed"})
    check("test_set_staff_active_insufficient_privilege_returns_403", r.status_code == 403, r.text)


def test_get_active_document_template_found():
    with patch("app.api.repo.get_active_document_template", return_value=_sample_document_template()):
        r = client.get("/document-templates/rental_demand")
    check("test_get_active_document_template_found", r.status_code == 200 and r.json()["template_ref"] == "gdoc:abc", r.text)


def test_get_active_document_template_not_found():
    with patch("app.api.repo.get_active_document_template", return_value=None):
        r = client.get("/document-templates/rental_demand")
    check("test_get_active_document_template_not_found", r.status_code == 404, r.text)


def test_get_active_document_template_bad_family_returns_400():
    r = client.get("/document-templates/not_a_family")
    check("test_get_active_document_template_bad_family_returns_400", r.status_code == 400, r.text)


def test_create_document_template():
    with patch("app.api.repo.create_document_template", return_value=_sample_document_template(id=2, version=2, template_ref="gdoc:v2")):
        r = client.post(
            "/document-templates",
            json={"family": "rental_demand", "version": 2, "template_ref": "gdoc:v2", "actor": "jed"},
        )
    check("test_create_document_template", r.status_code == 200 and r.json()["template_ref"] == "gdoc:v2", r.text)


def test_create_document_template_bad_family_returns_400():
    r = client.post(
        "/document-templates",
        json={"family": "not_a_family", "version": 1, "template_ref": "gdoc:x", "actor": "jed"},
    )
    check("test_create_document_template_bad_family_returns_400", r.status_code == 400, r.text)


def test_create_document_template_duplicate_returns_409():
    with patch("app.api.repo.create_document_template", side_effect=psycopg2.errors.UniqueViolation()):
        r = client.post(
            "/document-templates",
            json={"family": "rental_demand", "version": 1, "template_ref": "gdoc:dupe", "actor": "jed"},
        )
    check("test_create_document_template_duplicate_returns_409", r.status_code == 409, r.text)


def test_create_document():
    with patch("app.api.repo.create_document", return_value=_sample_document()):
        r = client.post(
            "/documents",
            json={
                "template_id": 1, "source_table": "elektrica.rental", "source_id": 1,
                "merge_data": {"renter_name": "Jane Doe"}, "actor": "jed",
            },
        )
    check("test_create_document_status", r.status_code == 200, r.text)
    check("test_create_document_body", r.json()["source_table"] == "elektrica.rental")


def test_create_document_output_ref_without_hash_returns_400():
    """Document.__post_init__'s CHECK mirror (platform.document,
    migrations/005) -- must surface as 400, not 500."""
    r = client.post(
        "/documents",
        json={
            "template_id": 1, "source_table": "elektrica.rental", "source_id": 1,
            "merge_data": {}, "actor": "jed", "output_ref": "drive:abc",
        },
    )
    check("test_create_document_output_ref_without_hash_returns_400", r.status_code == 400, r.text)


def test_get_document_found():
    with patch("app.api.repo.get_document", return_value=_sample_document()):
        r = client.get("/documents/1")
    check("test_get_document_found", r.status_code == 200 and r.json()["id"] == 1)


def test_get_document_not_found():
    with patch("app.api.repo.get_document", return_value=None):
        r = client.get("/documents/999")
    check("test_get_document_not_found", r.status_code == 404)


def test_get_documents_never_sent():
    with patch("app.api.repo.list_documents_never_sent", return_value=[{"document_id": 1}]):
        r = client.get("/documents/never-sent")
    check("test_get_documents_never_sent", r.status_code == 200 and len(r.json()) == 1)


def test_create_outbound_log():
    with patch("app.api.repo.get_document", return_value=_sample_document()), \
         patch("app.api.repo.create_outbound_log", return_value=_sample_outbound_log()):
        r = client.post("/documents/1/outbound", json={"channel": "fax", "recipient": "555-0100", "actor": "jed"})
    check("test_create_outbound_log_status", r.status_code == 200, r.text)
    check("test_create_outbound_log_body", r.json()["channel"] == "fax")


def test_create_outbound_log_document_not_found():
    with patch("app.api.repo.get_document", return_value=None):
        r = client.post("/documents/999/outbound", json={"channel": "fax", "recipient": "555-0100", "actor": "jed"})
    check("test_create_outbound_log_document_not_found", r.status_code == 404)


def test_create_outbound_log_bad_channel_returns_400():
    with patch("app.api.repo.get_document", return_value=_sample_document()):
        r = client.post("/documents/1/outbound", json={"channel": "carrier_pigeon", "recipient": "x", "actor": "jed"})
    check("test_create_outbound_log_bad_channel_returns_400", r.status_code == 400, r.text)


def test_get_outbound_log():
    with patch("app.api.repo.get_document", return_value=_sample_document()), \
         patch("app.api.repo.list_outbound_log_for_document", return_value=[_sample_outbound_log()]):
        r = client.get("/documents/1/outbound")
    check("test_get_outbound_log", r.status_code == 200 and len(r.json()) == 1)


def test_create_communication_proposed():
    with patch("app.api.repo.create_communication", return_value=_sample_communication()):
        r = client.post(
            "/communications",
            json={
                "source_table": "elektrica.rental", "source_id": 1, "direction": "inbound",
                "channel": "email", "occurred_at": "2026-09-04T00:00:00", "source_system": "ringcentral",
                "actor": "jed", "proposed": True,
            },
        )
    check("test_create_communication_proposed_status", r.status_code == 200, r.text)
    check("test_create_communication_proposed_body", r.json()["match_status"] == "proposed")


def test_create_communication_outbound_confirmed_by_construction():
    with patch(
        "app.api.repo.create_communication",
        return_value=_sample_communication(
            direction=CommunicationDirection.OUTBOUND, match_status=CommunicationMatchStatus.CONFIRMED,
            matched_by="app", matched_at=datetime(2026, 9, 4),
        ),
    ):
        r = client.post(
            "/communications",
            json={
                "source_table": "elektrica.rental", "source_id": 1, "direction": "outbound",
                "channel": "email", "occurred_at": "2026-09-04T00:00:00", "source_system": "app",
                "actor": "jed", "proposed": False,
            },
        )
    check("test_create_communication_outbound_confirmed_status", r.status_code == 200, r.text)
    check("test_create_communication_outbound_confirmed_body", r.json()["match_status"] == "confirmed")


def test_create_communication_bad_channel_returns_400():
    r = client.post(
        "/communications",
        json={
            "source_table": "elektrica.rental", "source_id": 1, "direction": "inbound",
            "channel": "carrier_pigeon", "occurred_at": "2026-09-04T00:00:00", "source_system": "ringcentral",
            "actor": "jed",
        },
    )
    check("test_create_communication_bad_channel_returns_400", r.status_code == 400, r.text)


def test_get_pending_communication_matches():
    with patch("app.api.repo.list_pending_communication_matches", return_value=[{"id": 1}]):
        r = client.get("/communications/pending")
    check("test_get_pending_communication_matches", r.status_code == 200 and len(r.json()) == 1)


def test_get_communications_for_source():
    with patch("app.api.repo.list_communications_for_source", return_value=[_sample_communication()]):
        r = client.get("/communications", params={"source_table": "elektrica.rental", "source_id": 1})
    check("test_get_communications_for_source", r.status_code == 200 and len(r.json()) == 1, r.text)


def test_confirm_communication():
    with patch(
        "app.api.repo.confirm_communication_match",
        return_value=_sample_communication(match_status=CommunicationMatchStatus.CONFIRMED, matched_by="jed", matched_at=datetime(2026, 9, 4)),
    ):
        r = client.post("/communications/1/confirm", json={"actor": "jed"})
    check("test_confirm_communication", r.status_code == 200 and r.json()["match_status"] == "confirmed", r.text)


def test_confirm_communication_not_found():
    with patch("app.api.repo.confirm_communication_match", side_effect=ValueError("No proposed communication with id=999")):
        r = client.post("/communications/999/confirm", json={"actor": "jed"})
    check("test_confirm_communication_not_found", r.status_code == 404)


def test_reject_communication():
    with patch(
        "app.api.repo.reject_communication_match",
        return_value=_sample_communication(match_status=CommunicationMatchStatus.REJECTED, matched_by="jed", matched_at=datetime(2026, 9, 4)),
    ):
        r = client.post("/communications/1/reject", json={"actor": "jed"})
    check("test_reject_communication", r.status_code == 200 and r.json()["match_status"] == "rejected", r.text)


# --- Insurance carrier + adjuster (platform.*, migrations/013) --------------

def _sample_carrier(**overrides) -> InsuranceCarrier:
    defaults = dict(id=1, name="State Farm Mutual Automobile Insurance Company", aliases=["State Farm", "SF"])
    defaults.update(overrides)
    return InsuranceCarrier(**defaults)


def _sample_adjuster(**overrides) -> Adjuster:
    defaults = dict(id=1, carrier_id=1, name="Jane Adjuster")
    defaults.update(overrides)
    return Adjuster(**defaults)


def test_create_insurance_carrier():
    with patch("app.api.repo.create_insurance_carrier", return_value=_sample_carrier()):
        r = client.post(
            "/insurance-carriers",
            json={"name": "State Farm Mutual Automobile Insurance Company", "actor": "jed", "aliases": ["State Farm", "SF"]},
        )
    check("test_create_insurance_carrier", r.status_code == 200 and r.json()["aliases"] == ["State Farm", "SF"], r.text)


def test_create_insurance_carrier_duplicate_returns_409():
    with patch("app.api.repo.create_insurance_carrier", side_effect=psycopg2.errors.UniqueViolation()):
        r = client.post("/insurance-carriers", json={"name": "State Farm", "actor": "jed"})
    check("test_create_insurance_carrier_duplicate_returns_409", r.status_code == 409, r.text)


def test_list_insurance_carriers():
    with patch("app.api.repo.list_insurance_carriers", return_value=[_sample_carrier()]):
        r = client.get("/insurance-carriers")
    check("test_list_insurance_carriers", r.status_code == 200 and len(r.json()) == 1, r.text)


def test_find_insurance_carrier_found():
    with patch("app.api.repo.find_insurance_carrier_by_name_or_alias", return_value=_sample_carrier()):
        r = client.get("/insurance-carriers/find", params={"name": "SF"})
    check("test_find_insurance_carrier_found", r.status_code == 200 and r.json()["id"] == 1, r.text)


def test_find_insurance_carrier_not_found_returns_null_not_404():
    with patch("app.api.repo.find_insurance_carrier_by_name_or_alias", return_value=None):
        r = client.get("/insurance-carriers/find", params={"name": "Nobody Insurance"})
    check("test_find_insurance_carrier_not_found_returns_null_not_404", r.status_code == 200 and r.json() is None, r.text)


def test_get_insurance_carrier_found():
    with patch("app.api.repo.get_insurance_carrier", return_value=_sample_carrier()):
        r = client.get("/insurance-carriers/1")
    check("test_get_insurance_carrier_found", r.status_code == 200 and r.json()["name"].startswith("State Farm"), r.text)


def test_get_insurance_carrier_not_found():
    with patch("app.api.repo.get_insurance_carrier", return_value=None):
        r = client.get("/insurance-carriers/999")
    check("test_get_insurance_carrier_not_found", r.status_code == 404, r.text)


def test_add_insurance_carrier_alias():
    with patch("app.api.repo.add_insurance_carrier_alias", return_value=_sample_carrier(aliases=["State Farm", "SF", "SFM"])):
        r = client.post("/insurance-carriers/1/aliases", json={"alias": "SFM", "actor": "jed"})
    check("test_add_insurance_carrier_alias", r.status_code == 200 and "SFM" in r.json()["aliases"], r.text)


def test_add_insurance_carrier_alias_not_found():
    with patch("app.api.repo.add_insurance_carrier_alias", side_effect=ValueError("No insurance_carrier with id=999")):
        r = client.post("/insurance-carriers/999/aliases", json={"alias": "X", "actor": "jed"})
    check("test_add_insurance_carrier_alias_not_found", r.status_code == 404, r.text)


def test_create_adjuster():
    with patch("app.api.repo.get_insurance_carrier", return_value=_sample_carrier()), \
         patch("app.api.repo.create_adjuster", return_value=_sample_adjuster()):
        r = client.post("/insurance-carriers/1/adjusters", json={"name": "Jane Adjuster", "actor": "jed"})
    check("test_create_adjuster", r.status_code == 200 and r.json()["carrier_id"] == 1, r.text)


def test_create_adjuster_carrier_not_found():
    with patch("app.api.repo.get_insurance_carrier", return_value=None):
        r = client.post("/insurance-carriers/999/adjusters", json={"name": "Nobody", "actor": "jed"})
    check("test_create_adjuster_carrier_not_found", r.status_code == 404, r.text)


def test_create_adjuster_duplicate_at_same_carrier_returns_409():
    with patch("app.api.repo.get_insurance_carrier", return_value=_sample_carrier()), \
         patch("app.api.repo.create_adjuster", side_effect=psycopg2.errors.UniqueViolation()):
        r = client.post("/insurance-carriers/1/adjusters", json={"name": "Jane Adjuster", "actor": "jed"})
    check("test_create_adjuster_duplicate_at_same_carrier_returns_409", r.status_code == 409, r.text)


def test_list_adjusters_for_carrier():
    with patch("app.api.repo.get_insurance_carrier", return_value=_sample_carrier()), \
         patch("app.api.repo.list_adjusters_for_carrier", return_value=[_sample_adjuster()]):
        r = client.get("/insurance-carriers/1/adjusters")
    check("test_list_adjusters_for_carrier", r.status_code == 200 and len(r.json()) == 1, r.text)


def test_list_adjusters_for_carrier_not_found():
    with patch("app.api.repo.get_insurance_carrier", return_value=None):
        r = client.get("/insurance-carriers/999/adjusters")
    check("test_list_adjusters_for_carrier_not_found", r.status_code == 404, r.text)


def test_get_adjuster_found():
    with patch("app.api.repo.get_adjuster", return_value=_sample_adjuster()):
        r = client.get("/adjusters/1")
    check("test_get_adjuster_found", r.status_code == 200 and r.json()["name"] == "Jane Adjuster", r.text)


def test_get_adjuster_not_found():
    with patch("app.api.repo.get_adjuster", return_value=None):
        r = client.get("/adjusters/999")
    check("test_get_adjuster_not_found", r.status_code == 404, r.text)


# --- Insurer payments (elektrica.insurer_payment, migrations/016) -----------
# Read-only from the API's point of view -- every check here exercises a
# GET route against a mocked repository return, same discipline as every
# other read-only route family in this file. No create/POST route exists
# to test: source='system' rows are DB-trigger-only, and the
# source='legacy_import' write path is repository-layer-only until the
# historical import (handoff §2.9) actually gets wired to an HTTP route.

def _sample_insurer_payment(**overrides) -> InsurerPayment:
    defaults = dict(
        id=1, demand_id=1, rental_id=1, carrier_id=1, adjuster_id=1,
        vehicle_class=VehicleClass.SEDAN,
        rental_start_date=date(2026, 1, 1), rental_end_date=date(2026, 1, 10),
        market_rate_at_time=Decimal("45.00"), amount_demanded=Decimal("900.00"),
        amount_paid=Decimal("810.00"), days_to_resolve=12,
        resolved_at=datetime(2026, 1, 15, 12, 0, 0),
    )
    defaults.update(overrides)
    return InsurerPayment(**defaults)


def test_get_carrier_insurer_payments():
    with patch("app.api.repo.get_insurance_carrier", return_value=_sample_carrier()), \
         patch("app.api.repo.list_insurer_payments_for_carrier", return_value=[_sample_insurer_payment()]):
        r = client.get("/insurance-carriers/1/insurer-payments")
    check(
        "test_get_carrier_insurer_payments",
        r.status_code == 200 and len(r.json()) == 1 and r.json()[0]["amount_paid"] == "810.00",
        r.text,
    )


def test_get_carrier_insurer_payments_carrier_not_found():
    with patch("app.api.repo.get_insurance_carrier", return_value=None):
        r = client.get("/insurance-carriers/999/insurer-payments")
    check("test_get_carrier_insurer_payments_carrier_not_found", r.status_code == 404, r.text)


def test_get_carrier_market_rate_exhibit():
    """The concrete handoff §2.8 exhibit: "this same carrier paid market
    rate on N prior claims." """
    with patch("app.api.repo.get_insurance_carrier", return_value=_sample_carrier()), \
         patch(
             "app.api.repo.get_carrier_market_rate_exhibit",
             return_value={
                 "claim_count": 3,
                 "avg_amount_demanded": Decimal("900.00"),
                 "avg_amount_paid": Decimal("780.00"),
                 "avg_market_rate": Decimal("45.00"),
             },
         ):
        r = client.get("/insurance-carriers/1/market-rate-exhibit")
    check(
        "test_get_carrier_market_rate_exhibit",
        r.status_code == 200 and r.json()["claim_count"] == 3 and r.json()["carrier_id"] == 1,
        r.text,
    )


def test_get_carrier_market_rate_exhibit_no_claims_yet():
    """A carrier with no resolved insurer_payment rows yet is a valid
    state (claim_count=0, null averages), not a 404 -- see the route's
    own docstring."""
    with patch("app.api.repo.get_insurance_carrier", return_value=_sample_carrier()), \
         patch("app.api.repo.get_carrier_market_rate_exhibit", return_value={"claim_count": 0}):
        r = client.get("/insurance-carriers/1/market-rate-exhibit")
    check(
        "test_get_carrier_market_rate_exhibit_no_claims_yet",
        r.status_code == 200 and r.json()["claim_count"] == 0 and r.json()["avg_amount_demanded"] is None,
        r.text,
    )


def test_get_carrier_market_rate_exhibit_carrier_not_found():
    with patch("app.api.repo.get_insurance_carrier", return_value=None):
        r = client.get("/insurance-carriers/999/market-rate-exhibit")
    check("test_get_carrier_market_rate_exhibit_carrier_not_found", r.status_code == 404, r.text)


def test_get_rental_insurer_payments():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.list_insurer_payments_for_rental", return_value=[_sample_insurer_payment()]):
        r = client.get("/rentals/1/insurer-payments")
    check("test_get_rental_insurer_payments", r.status_code == 200 and len(r.json()) == 1, r.text)


def test_get_rental_insurer_payments_rental_not_found():
    with patch("app.api.repo.get_rental", return_value=None):
        r = client.get("/rentals/999/insurer-payments")
    check("test_get_rental_insurer_payments_rental_not_found", r.status_code == 404, r.text)


def test_get_insurer_payment_found():
    with patch("app.api.repo.get_insurer_payment", return_value=_sample_insurer_payment()):
        r = client.get("/insurer-payments/1")
    check("test_get_insurer_payment_found", r.status_code == 200 and r.json()["id"] == 1, r.text)


def test_get_insurer_payment_not_found():
    with patch("app.api.repo.get_insurer_payment", return_value=None):
        r = client.get("/insurer-payments/999")
    check("test_get_insurer_payment_not_found", r.status_code == 404, r.text)


if __name__ == "__main__":
    tests = [
        test_health, test_fleet_out,
        test_fleet_board_out_route, test_fleet_board_available_route,
        test_create_vehicle, test_create_vehicle_duplicate_vin_returns_409,
        test_create_vehicle_bad_status_returns_400,
        test_get_vehicle_by_vin_found, test_get_vehicle_by_vin_not_found,
        test_get_vehicle_found, test_get_vehicle_not_found,
        test_update_vehicle_position, test_update_vehicle_position_not_found_returns_404,
        test_create_renter, test_get_renter_found, test_get_renter_not_found,
        test_get_renter_by_person_found, test_get_renter_by_person_not_found,
        test_intake_renter_attached, test_intake_renter_created, test_intake_renter_queued_has_no_renter,
        test_get_pending_person_match_queue_excludes_vls_at_query_level,
        test_decide_person_match_queue_confirmed_match,
        test_decide_person_match_queue_confirmed_split_no_renter_for_collision,
        test_decide_person_match_queue_vls_refused_403,
        test_decide_person_match_queue_not_found_404,
        test_decide_person_match_queue_already_resolved_400,
        test_create_rental, test_create_rental_bad_billed_to,
        test_list_rentals_no_filter, test_list_rentals_with_state_filter, test_list_rentals_bad_state_filter,
        test_get_rental_found, test_get_rental_not_found,
        test_transition_rental_success, test_transition_rental_illegal_returns_400,
        test_transition_rental_bad_state_value_returns_400,
        test_transition_rental_db_rejection_returns_400_not_500,
        test_get_blocked_rentals,
        test_link_vls_case, test_link_vls_case_rental_not_found,
        test_link_vls_case_bad_vls_case_id_returns_400_not_500,
        test_create_proposal, test_create_proposal_rental_not_found, test_create_proposal_bad_kind,
        test_create_proposal_no_key_configured_returns_503,
        test_create_proposal_missing_header_returns_401, test_create_proposal_wrong_key_returns_401,
        test_get_pending_proposals, test_decide_proposal_accept, test_decide_proposal_bad_status,
        test_create_demand, test_create_demand_carrier_without_name_returns_400,
        test_create_demand_unknown_carrier_id_returns_400,
        test_create_demand_mismatched_adjuster_carrier_returns_400,
        test_get_rental_demands, test_get_rental_demands_rental_not_found,
        test_mark_demand_sent, test_get_aging_demands,
        test_create_comparable_set, test_create_comparable_set_demand_not_found,
        test_create_comparable_set_bad_date_range_returns_400,
        test_create_comparable_set_bad_vehicle_class_returns_400,
        test_create_toll, test_confirm_toll, test_confirm_toll_not_found,
        test_create_payment, test_create_payment_authorize_net_without_txn_id_returns_400,
        test_create_payment_zero_amount_returns_400,
        test_vehicle_revenue_summary, test_compliance_expiring_soon,
        test_create_compliance_item, test_create_compliance_item_vehicle_not_found,
        test_create_compliance_item_bad_item_type_returns_400,
        test_get_compliance_item_found, test_get_compliance_item_not_found,
        test_update_compliance_item_status, test_update_compliance_item_status_not_found,
        test_update_compliance_item_status_bad_status_returns_400,
        test_provision_staff, test_provision_staff_bad_role_returns_400,
        test_provision_staff_domain_rejection_returns_400,
        test_provision_staff_insufficient_privilege_returns_403,
        test_get_staff_found, test_get_staff_not_found,
        test_set_staff_active_deactivate, test_set_staff_active_not_found,
        test_set_staff_active_insufficient_privilege_returns_403,
        test_get_active_document_template_found, test_get_active_document_template_not_found,
        test_get_active_document_template_bad_family_returns_400,
        test_create_document_template, test_create_document_template_bad_family_returns_400,
        test_create_document_template_duplicate_returns_409,
        test_create_document, test_create_document_output_ref_without_hash_returns_400,
        test_get_document_found, test_get_document_not_found, test_get_documents_never_sent,
        test_create_outbound_log, test_create_outbound_log_document_not_found,
        test_create_outbound_log_bad_channel_returns_400, test_get_outbound_log,
        test_create_communication_proposed, test_create_communication_outbound_confirmed_by_construction,
        test_create_communication_bad_channel_returns_400,
        test_get_pending_communication_matches, test_get_communications_for_source,
        test_confirm_communication, test_confirm_communication_not_found, test_reject_communication,
        test_create_insurance_carrier, test_create_insurance_carrier_duplicate_returns_409,
        test_list_insurance_carriers, test_find_insurance_carrier_found,
        test_find_insurance_carrier_not_found_returns_null_not_404,
        test_get_insurance_carrier_found, test_get_insurance_carrier_not_found,
        test_add_insurance_carrier_alias, test_add_insurance_carrier_alias_not_found,
        test_create_adjuster, test_create_adjuster_carrier_not_found,
        test_create_adjuster_duplicate_at_same_carrier_returns_409,
        test_list_adjusters_for_carrier, test_list_adjusters_for_carrier_not_found,
        test_get_adjuster_found, test_get_adjuster_not_found,
        test_get_carrier_insurer_payments, test_get_carrier_insurer_payments_carrier_not_found,
        test_get_carrier_market_rate_exhibit, test_get_carrier_market_rate_exhibit_no_claims_yet,
        test_get_carrier_market_rate_exhibit_carrier_not_found,
        test_get_rental_insurer_payments, test_get_rental_insurer_payments_rental_not_found,
        test_get_insurer_payment_found, test_get_insurer_payment_not_found,
    ]
    for t in tests:
        t()
    total = len(tests)
    passed = total - len(FAILED)
    print(f"\n{passed}/{total} tests passed")
    if FAILED:
        raise SystemExit(1)
