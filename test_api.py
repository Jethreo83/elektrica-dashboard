"""Tests for app/api.py -- no DB dependency. Every repository call is
mocked via unittest.mock.patch on app.repository's functions (imported
into app.api as `repo`), and the get_cursor dependency is overridden to
yield a harmless sentinel so no real connection is ever attempted. Same
discipline as Complete Collision's test_api.py.

Run: python test_api.py
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app, get_cursor
from app.models import (
    Demand, DemandRecipientType, DemandType, Payment, PaymentSource,
    ProposalKind, ProposalStatus, Rental, RentalBilledTo, RentalEvent,
    RentalProposal, RentalState, EventSource, Toll, Vehicle, VehicleClass,
    VehicleStatus,
)

FAILED = []


def _override_cursor():
    yield object()  # never touched -- every repo.* call in these tests is mocked


app.dependency_overrides[get_cursor] = _override_cursor
client = TestClient(app)


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} {detail}")
        FAILED.append(name)


def _sample_vehicle(**overrides) -> Vehicle:
    defaults = dict(id=1, vin="1FADP3F20EL123456", vehicle_class=VehicleClass.SEDAN, status=VehicleStatus.OUT)
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
        recipient_type=DemandRecipientType.CARRIER, carrier_name="Acme Ins",
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


def _sample_payment(**overrides) -> Payment:
    defaults = dict(id=1, rental_id=1, source=PaymentSource.MANUAL, amount=Decimal("450.00"))
    defaults.update(overrides)
    return Payment(**defaults)


def test_health():
    r = client.get("/health")
    check("test_health", r.status_code == 200 and r.json() == {"status": "ok"})


def test_fleet_out():
    with patch("app.api.repo.list_vehicles_by_status", return_value=[_sample_vehicle()]):
        r = client.get("/fleet/out")
    check("test_fleet_out_status", r.status_code == 200, r.text)
    check("test_fleet_out_body", r.json()[0]["status"] == "out")


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


def test_create_proposal():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()), \
         patch("app.api.repo.create_rental_proposal", return_value=_sample_proposal()):
        r = client.post(
            "/rentals/1/proposals",
            json={
                "kind": "return", "proposed_values": {"return_date": "2026-09-10"},
                "source_system": "geofence_email", "observed_at": "2026-09-10T14:30:00",
            },
        )
    check("test_create_proposal_status", r.status_code == 200, r.text)
    check("test_create_proposal_body", r.json()["status"] == "pending")


def test_create_proposal_rental_not_found():
    with patch("app.api.repo.get_rental", return_value=None):
        r = client.post(
            "/rentals/999/proposals",
            json={"kind": "return", "proposed_values": {}, "source_system": "bot", "observed_at": "2026-09-10T14:30:00"},
        )
    check("test_create_proposal_rental_not_found", r.status_code == 404)


def test_create_proposal_bad_kind():
    with patch("app.api.repo.get_rental", return_value=_sample_rental()):
        r = client.post(
            "/rentals/1/proposals",
            json={"kind": "not_a_kind", "proposed_values": {}, "source_system": "bot", "observed_at": "2026-09-10T14:30:00"},
        )
    check("test_create_proposal_bad_kind", r.status_code == 400, r.text)


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
                "amount": "450.00", "actor": "jed", "carrier_name": "Acme Ins",
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


if __name__ == "__main__":
    tests = [
        test_health, test_fleet_out, test_create_rental, test_create_rental_bad_billed_to,
        test_get_rental_found, test_get_rental_not_found,
        test_transition_rental_success, test_transition_rental_illegal_returns_400,
        test_transition_rental_bad_state_value_returns_400,
        test_transition_rental_db_rejection_returns_400_not_500,
        test_get_blocked_rentals,
        test_create_proposal, test_create_proposal_rental_not_found, test_create_proposal_bad_kind,
        test_get_pending_proposals, test_decide_proposal_accept, test_decide_proposal_bad_status,
        test_create_demand, test_create_demand_carrier_without_name_returns_400,
        test_mark_demand_sent, test_get_aging_demands,
        test_create_toll, test_confirm_toll, test_confirm_toll_not_found,
        test_create_payment, test_create_payment_authorize_net_without_txn_id_returns_400,
        test_create_payment_zero_amount_returns_400,
        test_vehicle_revenue_summary, test_compliance_expiring_soon,
    ]
    for t in tests:
        t()
    total = len(tests)
    passed = total - len(FAILED)
    print(f"\n{passed}/{total} tests passed")
    if FAILED:
        raise SystemExit(1)
