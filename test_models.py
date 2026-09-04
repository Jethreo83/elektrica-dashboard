"""Tests for app/models.py -- pure logic, no DB dependency.
Run with: python test_models.py
"""
from datetime import date, datetime
from decimal import Decimal

from app.models import (
    ComparableSet,
    Communication,
    CommunicationChannel,
    CommunicationDirection,
    CommunicationMatchStatus,
    Demand,
    DemandRecipientType,
    DemandStatus,
    DemandType,
    Document,
    EventSource,
    Payment,
    PaymentSource,
    RentalEvent,
    RentalState,
    StaffRole,
    StaffUser,
    validate_rental_transition,
)

FAILED = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} {detail}")
        FAILED.append(name)


def test_validate_rental_transition_allows_forward():
    validate_rental_transition(RentalState.ACTIVE, RentalState.FINISHED)
    validate_rental_transition(RentalState.NEEDS_DEMAND, RentalState.DEMAND_SENT)
    validate_rental_transition(RentalState.NEEDS_SERVED, RentalState.IN_LITIGATION)
    check("test_validate_rental_transition_allows_forward", True)


def test_validate_rental_transition_allows_rework_loop():
    # needs_more_information <-> needs_demand is bidirectional per handoff §2.4
    validate_rental_transition(RentalState.NEEDS_DEMAND, RentalState.NEEDS_MORE_INFORMATION)
    validate_rental_transition(RentalState.NEEDS_MORE_INFORMATION, RentalState.NEEDS_DEMAND)
    check("test_validate_rental_transition_allows_rework_loop", True)


def test_validate_rental_transition_rejects_skip():
    try:
        validate_rental_transition(RentalState.ACTIVE, RentalState.NEEDS_SERVED)
        check("test_validate_rental_transition_rejects_skip", False)
    except ValueError:
        check("test_validate_rental_transition_rejects_skip", True)


def test_validate_rental_transition_rejects_backward():
    try:
        validate_rental_transition(RentalState.NEGOTIATING, RentalState.NEEDS_DEMAND)
        check("test_validate_rental_transition_rejects_backward", False)
    except ValueError:
        check("test_validate_rental_transition_rejects_backward", True)


def test_validate_rental_transition_resolved_is_terminal():
    try:
        validate_rental_transition(RentalState.RESOLVED, RentalState.ACTIVE)
        check("test_validate_rental_transition_resolved_is_terminal", False)
    except ValueError:
        check("test_validate_rental_transition_resolved_is_terminal", True)


def test_rental_event_requires_source_ref_for_non_manual():
    try:
        RentalEvent(
            rental_id=1, event_type=RentalState.FINISHED,
            source=EventSource.BOT_PROPOSAL, source_ref=None,
        )
        check("test_rental_event_requires_source_ref_for_non_manual", False)
    except ValueError:
        check("test_rental_event_requires_source_ref_for_non_manual", True)


def test_rental_event_manual_source_ref_optional():
    ev = RentalEvent(
        rental_id=1, event_type=RentalState.FINISHED, source=EventSource.MANUAL, confirmed_by="jed",
    )
    check("test_rental_event_manual_source_ref_optional", ev.source_ref is None)


def test_rental_event_confirmed_requires_confirmed_by():
    try:
        RentalEvent(
            rental_id=1, event_type=RentalState.FINISHED,
            source=EventSource.MANUAL, confirmed=True, confirmed_by=None,
        )
        check("test_rental_event_confirmed_requires_confirmed_by", False)
    except ValueError:
        check("test_rental_event_confirmed_requires_confirmed_by", True)


def test_rental_event_unconfirmed_confirmed_by_optional():
    ev = RentalEvent(
        rental_id=1, event_type=RentalState.FINISHED,
        source=EventSource.BOT_PROPOSAL, source_ref="geofence-1", confirmed=False,
    )
    check("test_rental_event_unconfirmed_confirmed_by_optional", ev.confirmed_by is None)


def test_demand_carrier_recipient_requires_carrier_name():
    try:
        Demand(
            rental_id=1, demand_type=DemandType.PRIMARY_INSURER,
            recipient_type=DemandRecipientType.CARRIER, amount=Decimal("500.00"),
            carrier_name=None,
        )
        check("test_demand_carrier_recipient_requires_carrier_name", False)
    except ValueError:
        check("test_demand_carrier_recipient_requires_carrier_name", True)


def test_demand_renter_recipient_no_carrier_name_needed():
    d = Demand(
        rental_id=1, demand_type=DemandType.BALANCE_TO_RENTER,
        recipient_type=DemandRecipientType.RENTER, amount=Decimal("120.00"),
    )
    check("test_demand_renter_recipient_no_carrier_name_needed", d.carrier_name is None)


def test_demand_draft_cannot_have_send_record():
    try:
        Demand(
            rental_id=1, demand_type=DemandType.UIM, recipient_type=DemandRecipientType.RENTER,
            amount=Decimal("100.00"), status=DemandStatus.DRAFT, sent_via="fax",
        )
        check("test_demand_draft_cannot_have_send_record", False)
    except ValueError:
        check("test_demand_draft_cannot_have_send_record", True)


def test_demand_sent_status_allows_send_record():
    d = Demand(
        rental_id=1, demand_type=DemandType.UIM, recipient_type=DemandRecipientType.RENTER,
        amount=Decimal("100.00"), status=DemandStatus.SENT, sent_via="fax",
        sent_at=datetime(2026, 9, 4),
    )
    check("test_demand_sent_status_allows_send_record", d.sent_via == "fax")


def test_comparable_set_rejects_invalid_date_range():
    try:
        ComparableSet(
            demand_id=1, scan_source="kayak", scan_timestamp=datetime(2026, 9, 4),
            date_range_start=date(2026, 9, 10), date_range_end=date(2026, 9, 1),
            comparables=[], computed_average=Decimal("55.00"),
        )
        check("test_comparable_set_rejects_invalid_date_range", False)
    except ValueError:
        check("test_comparable_set_rejects_invalid_date_range", True)


def test_comparable_set_accepts_valid_date_range():
    cs = ComparableSet(
        demand_id=1, scan_source="kayak", scan_timestamp=datetime(2026, 9, 4),
        date_range_start=date(2026, 9, 1), date_range_end=date(2026, 9, 10),
        comparables=[{"vendor": "Hertz", "vehicle": "Model 3", "daily_rate": "60.00"}],
        computed_average=Decimal("60.00"),
    )
    check("test_comparable_set_accepts_valid_date_range", cs.computed_average == Decimal("60.00"))


def test_payment_rejects_zero_amount():
    try:
        Payment(rental_id=1, source=PaymentSource.MANUAL, amount=Decimal("0.00"))
        check("test_payment_rejects_zero_amount", False)
    except ValueError:
        check("test_payment_rejects_zero_amount", True)


def test_payment_authorize_net_requires_external_id():
    try:
        Payment(rental_id=1, source=PaymentSource.AUTHORIZE_NET, amount=Decimal("50.00"))
        check("test_payment_authorize_net_requires_external_id", False)
    except ValueError:
        check("test_payment_authorize_net_requires_external_id", True)


def test_payment_manual_no_external_id_needed():
    p = Payment(rental_id=1, source=PaymentSource.MANUAL, amount=Decimal("50.00"))
    check("test_payment_manual_no_external_id_needed", p.external_transaction_id is None)


def test_staff_user_rejects_wrong_domain():
    try:
        StaffUser(person_id=1, role=StaffRole.OWNER, google_email="jed@gmail.com")
        check("test_staff_user_rejects_wrong_domain", False)
    except ValueError:
        check("test_staff_user_rejects_wrong_domain", True)


def test_staff_user_accepts_correct_domain_and_lowercases():
    su = StaffUser(person_id=1, role=StaffRole.OWNER, google_email="Jed@ElektricaRentals.com")
    check("test_staff_user_accepts_correct_domain_and_lowercases", su.google_email == "jed@elektricarentals.com")


def test_document_rejects_output_ref_without_hash():
    try:
        Document(
            template_id=1, source_table="elektrica.rental", source_id=1,
            merge_data={"renter_name": "Jane Doe"}, output_ref="drive:abc123", output_hash=None,
        )
        check("test_document_rejects_output_ref_without_hash", False)
    except ValueError:
        check("test_document_rejects_output_ref_without_hash", True)


def test_document_accepts_output_ref_with_hash():
    d = Document(
        template_id=1, source_table="elektrica.rental", source_id=1,
        merge_data={"renter_name": "Jane Doe"}, output_ref="drive:abc123", output_hash="sha256:deadbeef",
    )
    check("test_document_accepts_output_ref_with_hash", d.output_hash == "sha256:deadbeef")


def test_document_defaults_attachments_to_empty_list():
    d = Document(template_id=1, source_table="elektrica.rental", source_id=1, merge_data={})
    check("test_document_defaults_attachments_to_empty_list", d.attachments == [])


def test_communication_proposed_rejects_matched_fields():
    try:
        Communication(
            source_table="elektrica.rental", source_id=1,
            direction=CommunicationDirection.INBOUND, channel=CommunicationChannel.EMAIL,
            occurred_at=datetime(2026, 9, 4), source_system="ringcentral",
            match_status=CommunicationMatchStatus.PROPOSED, matched_by="jed",
        )
        check("test_communication_proposed_rejects_matched_fields", False)
    except ValueError:
        check("test_communication_proposed_rejects_matched_fields", True)


def test_communication_confirmed_requires_matched_fields():
    try:
        Communication(
            source_table="elektrica.rental", source_id=1,
            direction=CommunicationDirection.OUTBOUND, channel=CommunicationChannel.SMS,
            occurred_at=datetime(2026, 9, 4), source_system="app",
            match_status=CommunicationMatchStatus.CONFIRMED,
        )
        check("test_communication_confirmed_requires_matched_fields", False)
    except ValueError:
        check("test_communication_confirmed_requires_matched_fields", True)


def test_communication_proposed_accepts_no_matched_fields():
    c = Communication(
        source_table="elektrica.rental", source_id=1,
        direction=CommunicationDirection.INBOUND, channel=CommunicationChannel.EMAIL,
        occurred_at=datetime(2026, 9, 4), source_system="ringcentral",
        match_status=CommunicationMatchStatus.PROPOSED,
    )
    check("test_communication_proposed_accepts_no_matched_fields", c.matched_by is None)


def test_communication_confirmed_accepts_full_matched_fields():
    c = Communication(
        source_table="elektrica.rental", source_id=1,
        direction=CommunicationDirection.OUTBOUND, channel=CommunicationChannel.SMS,
        occurred_at=datetime(2026, 9, 4), source_system="app",
        match_status=CommunicationMatchStatus.CONFIRMED, matched_by="app", matched_at=datetime(2026, 9, 4),
    )
    check("test_communication_confirmed_accepts_full_matched_fields", c.matched_by == "app")


if __name__ == "__main__":
    tests = [
        test_validate_rental_transition_allows_forward,
        test_validate_rental_transition_allows_rework_loop,
        test_validate_rental_transition_rejects_skip,
        test_validate_rental_transition_rejects_backward,
        test_validate_rental_transition_resolved_is_terminal,
        test_rental_event_requires_source_ref_for_non_manual,
        test_rental_event_manual_source_ref_optional,
        test_rental_event_confirmed_requires_confirmed_by,
        test_rental_event_unconfirmed_confirmed_by_optional,
        test_demand_carrier_recipient_requires_carrier_name,
        test_demand_renter_recipient_no_carrier_name_needed,
        test_demand_draft_cannot_have_send_record,
        test_demand_sent_status_allows_send_record,
        test_comparable_set_rejects_invalid_date_range,
        test_comparable_set_accepts_valid_date_range,
        test_payment_rejects_zero_amount,
        test_payment_authorize_net_requires_external_id,
        test_payment_manual_no_external_id_needed,
        test_staff_user_rejects_wrong_domain,
        test_staff_user_accepts_correct_domain_and_lowercases,
        test_document_rejects_output_ref_without_hash,
        test_document_accepts_output_ref_with_hash,
        test_document_defaults_attachments_to_empty_list,
        test_communication_proposed_rejects_matched_fields,
        test_communication_confirmed_requires_matched_fields,
        test_communication_proposed_accepts_no_matched_fields,
        test_communication_confirmed_accepts_full_matched_fields,
    ]
    for t in tests:
        t()
    total = len(tests)
    passed = total - len(FAILED)
    print(f"\n{passed}/{total} tests passed")
    if FAILED:
        raise SystemExit(1)
