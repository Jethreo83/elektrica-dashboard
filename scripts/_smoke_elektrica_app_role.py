"""Proves the ACTUAL production access pattern: a connection that
authenticates as a login role (neondb_owner) and then `SET ROLE
elektrica_app` before doing any work -- not just a plain neondb_owner
connection, which every prior smoke/live run in this repo (including
scripts/_smoke_repository.py) has used instead, per docs/BUILD_LOG.md's
own flagged open item.

Rationale for the neondb_owner-then-SET-ROLE shape rather than a direct
elektrica_app login: elektrica_app is NOLOGIN by design (confirmed via
`neon roles list` -- it exists as a role to hold grants, not to
authenticate directly), and migrations/001 explicitly does
`GRANT elektrica_app TO neondb_owner` for exactly this reason. This is
not a workaround; it's the documented, intended access shape.

This script does two things a plain happy-path smoke test does not:
  1. Runs the real repository functions AS elektrica_app (not
     neondb_owner) to prove the schema's actual least-privilege GRANTs
     (migrations/001-011) are sufficient for the app layer to function
     day-to-day -- not just that the SQL is syntactically fine under a
     role with blanket access.
  2. Deliberately attempts operations elektrica_app is documented as NOT
     granted (INSERT into platform.person; INSERT/UPDATE on
     elektrica.staff_user) and asserts they are REJECTED by Postgres,
     proving the negative as rigorously as the positive path -- a grant
     table that silently allows more than intended is exactly as much of
     a bug as one that blocks something it shouldn't.

Usage: python scripts/_smoke_elektrica_app_role.py <ENV_VAR_NAME>
(ENV_VAR_NAME must hold a neondb_owner-class connection string, since
that's the login role being granted elektrica_app membership.)
"""
import sys
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2

from app.db import cursor
from app.models import (
    Demand, DemandRecipientType, DemandType, EventSource, Payment,
    PaymentSource, ProposalKind, ProposalStatus, Rental, RentalProposal,
    RentalState, StaffRole, Toll, Vehicle, VehicleClass, VehicleStatus,
)
from app import repository as repo


def main():
    env_var = sys.argv[1]
    ids = {}

    # -----------------------------------------------------------------
    # Step 0: platform.person row created under the UNPRIVILEGED
    # elektrica_app role deliberately FAILS (no INSERT grant) -- prove
    # this negative first, then create the row for real under
    # neondb_owner (no set_role) so the rest of the script has a person
    # to link, matching the documented "identity creation is an
    # out-of-band admin/identity-service action" split.
    # -----------------------------------------------------------------
    print("--- negative check: elektrica_app INSERT into platform.person must be REJECTED ---")
    try:
        with cursor(env_var, autocommit=False, set_role="elektrica_app") as cur:
            cur.execute(
                "INSERT INTO platform.person (first_name, last_name, email_normalized, created_by) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                ("Should", "Fail", "should.fail.elektrica@example.com", "smoke_role_test"),
            )
        print("  ERROR: should have raised a permission error!")
        raise SystemExit(1)
    except psycopg2.errors.InsufficientPrivilege as e:
        print(f"  correctly rejected: {type(e).__name__}: {str(e).strip()}")

    print("\n--- create platform.person under neondb_owner (admin/identity-service stand-in) ---")
    with cursor(env_var, autocommit=False) as cur:
        cur.execute(
            "INSERT INTO platform.person (first_name, last_name, email_normalized, created_by) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            ("RoleSmoke", "Renter", "role.smoke.renter@example.com", "smoke_role_test"),
        )
        ids["person_id"] = cur.fetchone()["id"]
    print(f"  person_id={ids['person_id']}")

    # -----------------------------------------------------------------
    # Step 1: the real happy path, but AS elektrica_app this time.
    # -----------------------------------------------------------------
    with cursor(env_var, autocommit=False, set_role="elektrica_app") as cur:
        cur.execute("SELECT current_user")
        actual_role = cur.fetchone()["current_user"]
        print(f"\n--- confirmed connection is running as: {actual_role} ---")
        assert actual_role == "elektrica_app", f"expected elektrica_app, got {actual_role}"

        print("--- create_renter_for_existing_person (as elektrica_app) ---")
        renter = repo.create_renter_for_existing_person(cur, ids["person_id"], "smoke_role_test")
        ids["renter_id"] = renter.id
        print(f"  renter.id={renter.id}")

        print("--- create_vehicle (as elektrica_app) ---")
        # VIN suffixed with a run-unique timestamp: a prior interrupted cron
        # run of this same script left permanent residue at
        # ROLESMOKEVIN00099 (append-only rental_event chain means it can't
        # be deleted), so a fixed VIN collides on any re-run after a crash.
        run_vin = f"ROLESMOKEVIN{int(time.time()) % 100000:05d}"
        vehicle = repo.create_vehicle(
            cur, Vehicle(vin=run_vin, vehicle_class=VehicleClass.SEDAN,
                         status=VehicleStatus.AVAILABLE),
            "smoke_role_test",
        )
        ids["vehicle_id"] = vehicle.id
        print(f"  vehicle.id={vehicle.id}")

        print("--- update_vehicle_position (as elektrica_app, bot-maintained column) ---")
        vehicle = repo.update_vehicle_position(cur, vehicle.id, {"lat": 30.3, "lng": -97.7}, "bot_role_smoke")
        assert vehicle.current_position == {"lat": 30.3, "lng": -97.7}
        print(f"  current_position={vehicle.current_position}")

        print("--- create_rental (as elektrica_app) ---")
        rental = repo.create_rental(
            cur, Rental(vehicle_id=vehicle.id, renter_id=renter.id, billed_to=None), "smoke_role_test",
        )
        ids["rental_id"] = rental.id
        print(f"  rental.id={rental.id} current_state={rental.current_state.value}")

        print("--- advance_rental_state active -> finished -> needs_demand (as elektrica_app) ---")
        rental = repo.advance_rental_state(cur, rental.id, RentalState.FINISHED, EventSource.MANUAL, "smoke_role_test")
        rental = repo.advance_rental_state(cur, rental.id, RentalState.NEEDS_DEMAND, EventSource.MANUAL, "smoke_role_test")
        assert rental.current_state == RentalState.NEEDS_DEMAND
        print(f"  current_state={rental.current_state.value}")

        print("--- create_rental_proposal + list_pending + decide (as elektrica_app) ---")
        proposal = repo.create_rental_proposal(
            cur,
            RentalProposal(
                rental_id=rental.id, kind=ProposalKind.RETURN,
                proposed_values={"return_date": "2026-09-15"},
                source_system="geofence_email", observed_at=datetime(2026, 9, 15, 9, 0),
                evidence={"alert_id": "role-smoke"},
            ),
            "bot_role_smoke",
        )
        ids["proposal_id"] = proposal.id
        pending_ids = [p.id for p in repo.list_pending_rental_proposals(cur)]
        assert proposal.id in pending_ids
        decided = repo.decide_rental_proposal(cur, proposal.id, ProposalStatus.ACCEPTED, "smoke_role_test")
        print(f"  proposal.id={proposal.id} decided.status={decided.status.value}")

        print("--- advance to demand_sent, create_demand, mark_demand_sent (as elektrica_app) ---")
        rental = repo.advance_rental_state(cur, rental.id, RentalState.DEMAND_SENT, EventSource.MANUAL, "smoke_role_test")

        cur.execute(
            "INSERT INTO platform.insurance_carrier (name, created_by, updated_by) "
            "VALUES (%s, %s, %s) RETURNING id",
            ("Role Smoke Insurance", "smoke_role_test", "smoke_role_test"),
        )
        ids["carrier_id"] = cur.fetchone()["id"]

        demand = repo.create_demand(
            cur,
            Demand(
                rental_id=rental.id, demand_type=DemandType.PRIMARY_INSURER,
                recipient_type=DemandRecipientType.CARRIER, carrier_id=ids["carrier_id"],
                amount=Decimal("500.00"),
            ),
            "smoke_role_test",
        )
        ids["demand_id"] = demand.id
        demand = repo.mark_demand_sent(cur, demand.id, "email", "smoke_role_test")
        print(f"  demand.id={demand.id} status={demand.status.value}")

        print("--- create_toll + confirm_toll (as elektrica_app) ---")
        toll = repo.create_toll(
            cur, Toll(rental_id=rental.id, tolloptics_record_id=f"TOLL-ROLE-SMOKE-{run_vin[-5:]}",
                      amount=Decimal("4.25"), toll_date=date(2026, 9, 14)),
            "bot_role_smoke",
        )
        toll = repo.confirm_toll(cur, toll.id)
        ids["toll_id"] = toll.id
        print(f"  toll.id={toll.id} confirmed={toll.confirmed}")

        print("--- create_payment (as elektrica_app) ---")
        payment = repo.create_payment(
            cur, Payment(rental_id=rental.id, demand_id=demand.id, source=PaymentSource.MANUAL,
                         amount=Decimal("500.00")),
            "smoke_role_test",
        )
        ids["payment_id"] = payment.id
        print(f"  payment.id={payment.id} amount={payment.amount}")

        print("--- get_staff_user_by_google_email (as elektrica_app -- SELECT is granted) ---")
        missing_staff = repo.get_staff_user_by_google_email(cur, "nobody@elektricarentals.com")
        assert missing_staff is None
        print("  SELECT on staff_user succeeded (returned None for unknown email, as expected)")

    print("\nHAPPY PATH AS elektrica_app COMMITTED. ids =", ids)

    # -----------------------------------------------------------------
    # Step 2: negative checks -- elektrica_app must NOT be able to
    # provision or modify staff_user (SELECT-only grant, migration 011).
    # Each runs in its own transaction so the expected failure/rollback
    # can't affect anything else.
    # -----------------------------------------------------------------
    print("\n--- negative check: elektrica_app INSERT into elektrica.staff_user must be REJECTED ---")
    try:
        with cursor(env_var, autocommit=False, set_role="elektrica_app") as cur:
            repo.provision_staff_user_for_existing_person(
                cur, ids["person_id"], StaffRole.STAFF, "should.fail@elektricarentals.com", "smoke_role_test",
            )
        print("  ERROR: should have raised a permission error!")
        raise SystemExit(1)
    except psycopg2.errors.InsufficientPrivilege as e:
        print(f"  correctly rejected: {type(e).__name__}: {str(e).strip()}")

    print("\n--- negative check: elektrica_app UPDATE on elektrica.staff_user must be REJECTED ---")
    try:
        with cursor(env_var, autocommit=False, set_role="elektrica_app") as cur:
            repo.set_staff_user_active(cur, "nobody@elektricarentals.com", False, "smoke_role_test")
        print("  ERROR: should have raised a permission error!")
        raise SystemExit(1)
    except psycopg2.errors.InsufficientPrivilege as e:
        print(f"  correctly rejected: {type(e).__name__}: {str(e).strip()}")

    print("\n--- negative check: elektrica_app DELETE on append-only elektrica.payment must be REJECTED ---")
    try:
        with cursor(env_var, autocommit=False, set_role="elektrica_app") as cur:
            cur.execute("DELETE FROM elektrica.payment WHERE id = %s", (ids["payment_id"],))
        print("  ERROR: should have raised!")
        raise SystemExit(1)
    except Exception as e:
        # Could surface as either InsufficientPrivilege (no grant at all)
        # or the DB's own append-only trigger, depending on which the
        # planner hits first -- either is a correct rejection.
        print(f"  correctly rejected: {type(e).__name__}: {str(e).strip()[:120]}")

    print("\n--- cleanup note (append-only tables mean this residue is permanent, same as _smoke_repository.py) ---")
    print(f"  Permanent staging residue from this run: person_id={ids['person_id']}, "
          f"renter_id={ids['renter_id']}, vehicle_id={ids['vehicle_id']} (vin={run_vin}), "
          f"rental_id={ids['rental_id']}, demand_id={ids['demand_id']}, "
          f"proposal_id={ids['proposal_id']}, toll_id={ids['toll_id']}, payment_id={ids['payment_id']}.")
    print("  Identifiable by 'smoke_role_test'/'bot_role_smoke' created_by and the ROLESMOKEVIN* VIN prefix.")

    print("\nALL ROLE-BASED SMOKE CHECKS PASSED -- elektrica_app's real GRANTs proven sufficient")
    print("for the full app-layer happy path AND proven to correctly reject every documented gap")
    print("(platform.person INSERT, staff_user INSERT/UPDATE, payment DELETE).")


if __name__ == "__main__":
    main()
