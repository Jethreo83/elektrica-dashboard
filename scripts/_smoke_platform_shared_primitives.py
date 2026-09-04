"""One-off script exercising app.repository's NEW document generator
(platform.document_template/document/outbound_log) and communication
timeline (platform.communication) functions against REAL staging data.
These tables (migrations/005/009/010) had schema but zero app-layer code
until this cron cycle -- this proves the new repository.py functions
actually work against real Postgres, not just that they parse.

Usage: python scripts/_smoke_platform_shared_primitives.py <ENV_VAR_NAME>

Per docs/BUILD_LOG.md's own lesson (crash-and-resume residue collision):
every natural key here is derived from the current timestamp, not
hardcoded, so a crash mid-run never collides with a retry.
"""
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import cursor
from app.models import (
    Communication, CommunicationChannel, CommunicationDirection,
    CommunicationMatchStatus, Document, DocumentTemplate,
    DocumentTemplateFamily, OutboundChannel, OutboundLog, Rental,
    RentalBilledTo, Vehicle, VehicleClass, VehicleStatus,
)
from app import repository as repo


def main():
    env_var = sys.argv[1]
    stamp = str(int(time.time()))
    ids = {}

    with cursor(env_var, autocommit=False) as cur:
        print("--- setup: platform.person + elektrica.renter + vehicle + rental ---")
        cur.execute(
            "INSERT INTO platform.person (first_name, last_name, email_normalized, created_by) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            ("SmokeDoc", "Renter", f"smoke.doc.renter.{stamp}@example.com", "smoke_test"),
        )
        ids["person_id"] = cur.fetchone()["id"]
        renter = repo.create_renter_for_existing_person(cur, ids["person_id"], "smoke_test")
        ids["renter_id"] = renter.id

        vehicle = repo.create_vehicle(
            cur, Vehicle(vin=f"SMOKEDOCVIN{stamp[-6:]}", vehicle_class=VehicleClass.SEDAN,
                         status=VehicleStatus.AVAILABLE),
            "smoke_test",
        )
        ids["vehicle_id"] = vehicle.id

        rental = repo.create_rental(
            cur, Rental(vehicle_id=vehicle.id, renter_id=renter.id, billed_to=RentalBilledTo.CARRIER),
            "smoke_test",
        )
        ids["rental_id"] = rental.id
        print(f"  rental.id={rental.id}")

        print("--- document generator: template -> document -> outbound_log ---")
        template = repo.get_active_document_template(cur, DocumentTemplateFamily.RENTAL_DEMAND)
        if template is None:
            template = repo.create_document_template(
                cur,
                DocumentTemplate(
                    family=DocumentTemplateFamily.RENTAL_DEMAND, version=1,
                    template_ref=f"gdoc:smoke-template-{stamp}",
                ),
                "smoke_test",
            )
            print(f"  created template.id={template.id} (no active rental_demand template existed)")
        else:
            print(f"  reused existing active template.id={template.id}")
        ids["template_id"] = template.id

        doc = repo.create_document(
            cur,
            Document(
                template_id=template.id, source_table="elektrica.rental", source_id=rental.id,
                merge_data={"renter_name": "Smoke Doc Renter", "amount": "450.00"},
                attachments=[{"ref": f"drive:receipt-{stamp}", "label": "receipt"}],
                output_ref=f"drive:demand-{stamp}", output_hash=f"sha256:{stamp}",
            ),
            "smoke_test",
        )
        ids["document_id"] = doc.id
        print(f"  document.id={doc.id} output_hash={doc.output_hash}")
        assert doc.source_id == rental.id

        fetched = repo.get_document(cur, doc.id)
        assert fetched is not None and fetched.id == doc.id
        print(f"  get_document round-trip OK")

        never_sent_before = {d["document_id"] for d in repo.list_documents_never_sent(cur)}
        assert doc.id in never_sent_before, "freshly generated, not-yet-sent document should appear in documents_never_sent"
        print(f"  documents_never_sent correctly includes doc.id={doc.id} before any send")

        outbound = repo.create_outbound_log(
            cur,
            OutboundLog(
                document_id=doc.id, channel=OutboundChannel.FAX, recipient="555-0100",
                delivery_confirmation_ref=f"fax-conf-{stamp}",
            ),
            "smoke_test",
        )
        ids["outbound_log_id"] = outbound.id
        print(f"  outbound_log.id={outbound.id}")

        never_sent_after = {d["document_id"] for d in repo.list_documents_never_sent(cur)}
        assert doc.id not in never_sent_after, "document should drop off documents_never_sent once an outbound_log row exists"
        print(f"  documents_never_sent correctly EXCLUDES doc.id={doc.id} after send -- 'generated but never sent' visibility proven both ways")

        logs = repo.list_outbound_log_for_document(cur, doc.id)
        assert len(logs) == 1 and logs[0].id == outbound.id
        print(f"  list_outbound_log_for_document round-trip OK")

        print("--- communication timeline: outbound (confirmed-by-construction) ---")
        outbound_comm = repo.create_communication(
            cur,
            Communication(
                source_table="elektrica.rental", source_id=rental.id,
                direction=CommunicationDirection.OUTBOUND, channel=CommunicationChannel.EMAIL,
                occurred_at=datetime.now(), source_system="app",
                from_ref="dashboard@elektricarentals.com", to_ref="claimsadjuster@example.com",
                subject=f"Demand smoke test {stamp}",
                match_status=CommunicationMatchStatus.CONFIRMED, matched_by="app", matched_at=datetime.now(),
            ),
            "smoke_test",
        )
        ids["outbound_comm_id"] = outbound_comm.id
        print(f"  communication.id={outbound_comm.id} (outbound, confirmed by construction)")

        print("--- communication timeline: inbound proposed match -> confirm ---")
        inbound_comm = repo.create_communication(
            cur,
            Communication(
                source_table="elektrica.rental", source_id=rental.id,
                direction=CommunicationDirection.INBOUND, channel=CommunicationChannel.EMAIL,
                occurred_at=datetime.now(), source_system="ringcentral",
                from_ref="claimsadjuster@example.com", subject=f"RE: claim {stamp}",
                match_status=CommunicationMatchStatus.PROPOSED,
                match_evidence={"matched_claim_number": stamp},
            ),
            "smoke_test",
        )
        ids["inbound_comm_id"] = inbound_comm.id
        print(f"  communication.id={inbound_comm.id} (inbound, proposed)")

        pending = [p for p in repo.list_pending_communication_matches(cur) if p["id"] == inbound_comm.id]
        assert len(pending) == 1, "freshly proposed inbound communication should appear in the pending-match queue"
        print(f"  list_pending_communication_matches correctly surfaces id={inbound_comm.id}")

        confirmed = repo.confirm_communication_match(cur, inbound_comm.id, "smoke_test")
        assert confirmed.match_status == CommunicationMatchStatus.CONFIRMED
        assert confirmed.matched_by == "smoke_test"
        print(f"  confirm_communication_match: id={inbound_comm.id} now confirmed")

        pending_after = [p for p in repo.list_pending_communication_matches(cur) if p["id"] == inbound_comm.id]
        assert len(pending_after) == 0, "confirmed communication should drop off the pending queue"
        print(f"  pending queue correctly no longer shows id={inbound_comm.id}")

        # Negative: a second decision on the same row must be rejected --
        # migrations/010's trigger only permits ONE proposed -> decided move.
        try:
            repo.confirm_communication_match(cur, inbound_comm.id, "smoke_test")
            print(f"  UNEXPECTED: re-confirming an already-confirmed communication did NOT raise")
            raise AssertionError("expected ValueError re-deciding an already-decided communication")
        except ValueError as e:
            print(f"  correctly rejected re-deciding an already-decided communication: {e}")

        timeline = repo.list_communications_for_source(cur, "elektrica.rental", rental.id)
        timeline_ids = {c.id for c in timeline}
        assert {outbound_comm.id, inbound_comm.id} <= timeline_ids
        print(f"  list_communications_for_source returns both rows for rental.id={rental.id} ({len(timeline)} total)")

        print(f"\nAll assertions passed. IDs created this run: {ids}")

    print("\nCommitted. Append-only tables (platform.document, platform.outbound_log, "
          "platform.communication) cannot be deleted by design -- residue left "
          "intentionally, same discipline as every other smoke run in this repo. "
          "platform.person/elektrica.renter/elektrica.vehicle/elektrica.rental rows "
          "also left (rental has dependent append-only rows via document.source_id).")


if __name__ == "__main__":
    main()
