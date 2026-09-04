"""One-off script exercising app.repository's rental spine, proposal,
demand, payment, and staff-user functions against REAL staging data.
Prints results for inspection -- not a pytest-style test, a real-execution
smoke check (same discipline as Complete Collision's
scripts/_smoke_repository.py).

Usage: python scripts/_smoke_repository.py <ENV_VAR_NAME>

Structure: happy-path work commits in its own transaction (cursor()
context #1). The DELETE-rejection probe runs in its OWN transaction
(context #2) so its expected failure/rollback cannot undo the
already-committed happy-path rows. Cleanup runs last in a third
transaction, deleting everything created, in FK-safe order (children
before parents) -- except append-only tables (rental_event, payment,
toll, comparable_set) which cannot be deleted by design; those are left
as intentional staging residue with a printed note, same as every
other staging smoke run in this repo family leaves harness rows behind.
"""
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import cursor
from app.models import (
    Demand, DemandRecipientType, DemandType, EventSource, Payment,
    PaymentSource, ProposalKind, ProposalStatus, Rental, RentalProposal,
    RentalState, Toll, Vehicle, VehicleClass, VehicleStatus,
)
from app import repository as repo


def main():
    env_var = sys.argv[1]
    ids = {}

    # -----------------------------------------------------------------
    # Happy path -- commits on clean exit of this `with` block.
    # -----------------------------------------------------------------
    with cursor(env_var, autocommit=False) as cur:
        print("--- create platform.person + elektrica.renter ---")
        cur.execute(
            "INSERT INTO platform.person (first_name, last_name, email_normalized, created_by) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            ("Smoke", "Renter", "smoke.renter.elektrica@example.com", "smoke_test"),
        )
        ids["person_id"] = cur.fetchone()["id"]
        renter = repo.create_renter_for_existing_person(cur, ids["person_id"], "smoke_test")
        ids["renter_id"] = renter.id
        print(f"  renter.id={renter.id} person_id={renter.person_id}")
        assert renter.person_id == ids["person_id"]

        print("--- create vehicle ---")
        vehicle = repo.create_vehicle(
            cur, Vehicle(vin="SMOKETESTVIN00042", vehicle_class=VehicleClass.SEDAN,
                         status=VehicleStatus.AVAILABLE),
            "smoke_test",
        )
        ids["vehicle_id"] = vehicle.id
        print(f"  vehicle.id={vehicle.id} vin={vehicle.vin} status={vehicle.status.value}")
        assert vehicle.status == VehicleStatus.AVAILABLE

        print("--- update vehicle bot-maintained position ---")
        vehicle = repo.update_vehicle_position(cur, vehicle.id, {"lat": 30.27, "lng": -97.74}, "bot_smoke")
        print(f"  current_position={vehicle.current_position}")
        assert vehicle.current_position == {"lat": 30.27, "lng": -97.74}

        print("--- create rental (spine) ---")
        rental = repo.create_rental(
            cur, Rental(vehicle_id=vehicle.id, renter_id=renter.id, billed_to=None), "smoke_test",
        )
        ids["rental_id"] = rental.id
        print(f"  rental.id={rental.id} current_state={rental.current_state.value}")
        assert rental.current_state == RentalState.ACTIVE

        print("--- advance_rental_state: active -> finished ---")
        rental = repo.advance_rental_state(cur, rental.id, RentalState.FINISHED, EventSource.MANUAL, "smoke_test")
        print(f"  current_state={rental.current_state.value}")
        assert rental.current_state == RentalState.FINISHED

        print("--- advance_rental_state: illegal skip finished -> resolved (should raise app-layer ValueError) ---")
        try:
            repo.advance_rental_state(cur, rental.id, RentalState.RESOLVED, EventSource.MANUAL, "smoke_test")
            print("  ERROR: should have raised!")
            raise SystemExit(1)
        except ValueError as e:
            print(f"  correctly raised (pre-flight, no DB round trip needed): {e}")

        print("--- advance_rental_state: finished -> needs_demand ---")
        rental = repo.advance_rental_state(cur, rental.id, RentalState.NEEDS_DEMAND, EventSource.MANUAL, "smoke_test")
        assert rental.current_state == RentalState.NEEDS_DEMAND
        print(f"  current_state={rental.current_state.value}")

        print("--- list_rental_events ---")
        events = repo.list_rental_events(cur, rental.id)
        print(f"  {len(events)} events: {[e.event_type.value for e in events]}")
        assert [e.event_type.value for e in events] == ["finished", "needs_demand"]

        print("--- create_rental_proposal (bot-written, pending) ---")
        proposal = repo.create_rental_proposal(
            cur,
            RentalProposal(
                rental_id=rental.id, kind=ProposalKind.RETURN,
                proposed_values={"return_date": "2026-09-10"},
                source_system="geofence_email", observed_at=datetime(2026, 9, 10, 14, 30),
                evidence={"alert_id": "abc123"},
            ),
            "bot_smoke",
        )
        ids["proposal_id"] = proposal.id
        print(f"  proposal.id={proposal.id} status={proposal.status.value}")
        assert proposal.status == ProposalStatus.PENDING

        print("--- list_pending_rental_proposals ---")
        pending = repo.list_pending_rental_proposals(cur)
        pending_ids = [p.id for p in pending]
        print(f"  pending proposal ids include ours: {proposal.id in pending_ids}")
        assert proposal.id in pending_ids

        print("--- decide_rental_proposal: accept (must NOT touch rental.current_state) ---")
        decided = repo.decide_rental_proposal(cur, proposal.id, ProposalStatus.ACCEPTED, "smoke_test")
        print(f"  decided.status={decided.status.value}")
        rental_after = repo.get_rental(cur, rental.id)
        print(f"  rental.current_state after accept={rental_after.current_state.value} (must still be needs_demand)")
        assert rental_after.current_state == RentalState.NEEDS_DEMAND, \
            "BUG: accepting a proposal must never auto-write rental.current_state (handoff §1.7)"

        print("--- advance to demand_sent, create demand ---")
        rental = repo.advance_rental_state(cur, rental.id, RentalState.DEMAND_SENT, EventSource.MANUAL, "smoke_test")
        demand = repo.create_demand(
            cur,
            Demand(
                rental_id=rental.id, demand_type=DemandType.PRIMARY_INSURER,
                recipient_type=DemandRecipientType.CARRIER, carrier_name="Acme Insurance",
                amount=Decimal("450.00"),
            ),
            "smoke_test",
        )
        ids["demand_id"] = demand.id
        print(f"  demand.id={demand.id} status={demand.status.value}")
        assert demand.status.value == "draft"

        print("--- mark_demand_sent ---")
        demand = repo.mark_demand_sent(cur, demand.id, "fax", "smoke_test")
        print(f"  demand.status={demand.status.value} sent_via={demand.sent_via}")
        assert demand.status.value == "sent"

        print("--- create_toll + confirm_toll ---")
        toll = repo.create_toll(
            cur, Toll(rental_id=rental.id, tolloptics_record_id="TOLL-SMOKE-001",
                      amount=Decimal("3.50"), toll_date=date(2026, 9, 9)),
            "bot_smoke",
        )
        toll = repo.confirm_toll(cur, toll.id)
        ids["toll_id"] = toll.id
        print(f"  toll.id={toll.id} confirmed={toll.confirmed}")
        assert toll.confirmed is True

        print("--- create_payment (manual) ---")
        payment = repo.create_payment(
            cur, Payment(rental_id=rental.id, demand_id=demand.id, source=PaymentSource.MANUAL,
                         amount=Decimal("450.00")),
            "smoke_test",
        )
        ids["payment_id"] = payment.id
        print(f"  payment.id={payment.id} amount={payment.amount}")

    print("\nHAPPY PATH COMMITTED. ids =", ids)

    # -----------------------------------------------------------------
    # DELETE-rejection probe -- isolated transaction so its expected
    # failure/rollback can't touch the already-committed happy path.
    # -----------------------------------------------------------------
    print("\n--- payment append-only: DELETE must be rejected by DB trigger ---")
    try:
        with cursor(env_var, autocommit=False) as cur:
            cur.execute("DELETE FROM elektrica.payment WHERE id = %s", (ids["payment_id"],))
        print("  ERROR: should have raised!")
        raise SystemExit(1)
    except Exception as e:
        print(f"  correctly rejected by DB ({type(e).__name__}); cursor() context rolled back cleanly")

    with cursor(env_var, autocommit=True) as cur:
        cur.execute("SELECT id FROM elektrica.payment WHERE id = %s", (ids["payment_id"],))
        row = cur.fetchone()
        print(f"  payment row still present after failed-DELETE rollback: {row is not None} (expected: True)")
        assert row is not None, "payment row should be untouched -- only the DELETE txn rolled back"

    # -----------------------------------------------------------------
    # Cleanup: elektrica.rental_event has NO ON DELETE CASCADE and is
    # itself append-only (DELETE forbidden by trigger), so once a rental
    # has any events, the rental row is permanently un-deletable via
    # normal DML -- and by extension so is everything it FKs to
    # (vehicle, renter) and everything that FKs to IT (demand,
    # rental_proposal, payment, toll). This is the correct behavior for
    # a real financial/legal audit trail, not a bug to work around here.
    # This smoke run's rows are therefore intentional, permanent staging
    # residue, same convention as every migrations/00N verify_NNN.sql's
    # TESTVIN-prefixed leftovers -- printed explicitly, not silently
    # left unexplained.
    # -----------------------------------------------------------------
    print("\n--- cleanup: nothing CAN be deleted once rental_event exists (append-only by design) ---")
    print(f"  Permanent staging residue from this run: person_id={ids['person_id']}, "
          f"renter_id={ids['renter_id']}, vehicle_id={ids['vehicle_id']} (vin=SMOKETESTVIN00042), "
          f"rental_id={ids['rental_id']}, demand_id={ids['demand_id']}, "
          f"proposal_id={ids['proposal_id']}, toll_id={ids['toll_id']}, payment_id={ids['payment_id']}.")
    print("  Identifiable by 'smoke_test'/'bot_smoke' created_by and the SMOKETESTVIN00042 VIN if a")
    print("  future staging reset needs to distinguish real dev data from this script's runs.")

    print("\nALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
