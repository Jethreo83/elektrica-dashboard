-- Verification harness for migration 004 (elektrica.rental_proposal).
-- Same discipline: verify by direct query, not by trusting exit codes.

DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_rental_id BIGINT;
  v_proposal_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, class, status, created_by, updated_by)
  VALUES ('TESTVIN0000000077', 'ev', 'available', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'ProposalRenter', 'test.proposalrenter@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.renter (person_id, created_by)
  VALUES (v_person_id, 'test_harness')
  RETURNING id INTO v_renter_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  VALUES (v_vehicle_id, v_renter_id, 'carrier', 'test_harness', 'test_harness')
  RETURNING id INTO v_rental_id;

  INSERT INTO elektrica.rental_proposal
    (rental_id, kind, proposed_values, source_system, evidence, observed_at, created_by)
  VALUES
    (v_rental_id, 'return', '{"returned_at": "2026-09-02T18:00:00Z"}'::jsonb,
     'geofence_email', '{"message_id": "test-msg-001"}'::jsonb, now(), 'test_harness')
  RETURNING id INTO v_proposal_id;

  RAISE NOTICE 'vehicle_id=% rental_id=% proposal_id=%', v_vehicle_id, v_rental_id, v_proposal_id;
END $$;

-- CHECK 1: proposal created with default status 'pending', decided fields NULL.
SELECT kind, status, decided_by, decided_at
FROM elektrica.rental_proposal
WHERE source_system = 'geofence_email';
-- EXPECT: 1 row, status=pending, decided_by/decided_at both NULL

-- CHECK 2: pending_rental_proposals view surfaces it.
SELECT kind, source_system FROM elektrica.pending_rental_proposals
WHERE source_system = 'geofence_email';
-- EXPECT: 1 row

-- CHECK 3: decision constraint rejects status<>'pending' without decided_by/at.
DO $$
DECLARE
  v_proposal_id BIGINT;
BEGIN
  SELECT id INTO v_proposal_id FROM elektrica.rental_proposal WHERE source_system = 'geofence_email';
  BEGIN
    UPDATE elektrica.rental_proposal SET status = 'accepted' WHERE id = v_proposal_id;
    RAISE EXCEPTION 'CHECK 3 FAILED: accepted without decided_by/decided_at should have been rejected';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'CHECK 3 PASSED: decision-fields-together constraint enforced';
  END;
END $$;

-- CHECK 4: valid decision (accepted + decided_by + decided_at together) succeeds.
DO $$
DECLARE
  v_proposal_id BIGINT;
BEGIN
  SELECT id INTO v_proposal_id FROM elektrica.rental_proposal WHERE source_system = 'geofence_email';
  UPDATE elektrica.rental_proposal
  SET status = 'accepted', decided_by = 'test_harness', decided_at = now()
  WHERE id = v_proposal_id;
END $$;

SELECT status, decided_by IS NOT NULL AS has_decided_by, decided_at IS NOT NULL AS has_decided_at
FROM elektrica.rental_proposal WHERE source_system = 'geofence_email';
-- EXPECT: 1 row, status=accepted, has_decided_by=true, has_decided_at=true

-- CHECK 5: once decided, cannot be re-decided (status change blocked).
DO $$
DECLARE
  v_proposal_id BIGINT;
BEGIN
  SELECT id INTO v_proposal_id FROM elektrica.rental_proposal WHERE source_system = 'geofence_email';
  BEGIN
    UPDATE elektrica.rental_proposal SET status = 'rejected', decided_by = 'someone_else', decided_at = now()
    WHERE id = v_proposal_id;
    RAISE EXCEPTION 'CHECK 5 FAILED: re-deciding an already-decided proposal should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%decision cannot be changed once made%' THEN
      RAISE NOTICE 'CHECK 5 PASSED: decision immutability enforced (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 6: substantive fields (proposed_values etc.) cannot be edited even
-- while still pending.
DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_rental_id BIGINT;
  v_proposal_id BIGINT;
BEGIN
  SELECT id INTO v_vehicle_id FROM elektrica.vehicle WHERE vin = 'TESTVIN0000000077';
  SELECT r.id INTO v_rental_id FROM elektrica.rental r WHERE r.vehicle_id = v_vehicle_id;

  INSERT INTO elektrica.rental_proposal
    (rental_id, kind, proposed_values, source_system, observed_at, created_by)
  VALUES (v_rental_id, 'tolls', '{"amount": 12.50}'::jsonb, 'tolloptics', now(), 'test_harness')
  RETURNING id INTO v_proposal_id;

  BEGIN
    UPDATE elektrica.rental_proposal SET proposed_values = '{"amount": 999}'::jsonb WHERE id = v_proposal_id;
    RAISE EXCEPTION 'CHECK 6 FAILED: editing proposed_values should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%immutable except for its one-time decision%' THEN
      RAISE NOTICE 'CHECK 6 PASSED: substantive-field immutability enforced (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 7: append-only — DELETE rejected.
DO $$
DECLARE
  v_proposal_id BIGINT;
BEGIN
  SELECT id INTO v_proposal_id FROM elektrica.rental_proposal WHERE source_system = 'tolloptics';
  BEGIN
    DELETE FROM elektrica.rental_proposal WHERE id = v_proposal_id;
    RAISE EXCEPTION 'CHECK 7 FAILED: DELETE should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only%' THEN
      RAISE NOTICE 'CHECK 7 PASSED: rental_proposal DELETE blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 8: crucially, accepting a proposal did NOT change elektrica.rental's
-- current_state — proposals are never auto-applied to legal-record fields
-- (handoff §1.7). This is the single most important behavioral check here.
SELECT r.current_state
FROM elektrica.rental r
JOIN elektrica.vehicle v ON v.id = r.vehicle_id
WHERE v.vin = 'TESTVIN0000000077';
-- EXPECT: 1 row, current_state = active (unchanged — no rental_event was
-- inserted as a side effect of accepting the proposal above)

SELECT 'ALL CHECKS COMPLETED — CHECK 8 must show active (proposal accept did not touch rental state)' AS summary;
