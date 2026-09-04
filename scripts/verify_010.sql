-- Verification harness for migration 010 (platform.communication).
-- Verifies by direct query against live staging data, not exit codes.

DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_rental_id BIGINT;
  v_comm_outbound_id BIGINT;
  v_comm_inbound_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, class, status, created_by, updated_by)
  VALUES ('TESTVIN0000000099', 'ev', 'available', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'CommRenter', 'test.commrenter@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.renter (person_id, created_by)
  VALUES (v_person_id, 'test_harness')
  RETURNING id INTO v_renter_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  VALUES (v_vehicle_id, v_renter_id, 'carrier', 'test_harness', 'test_harness')
  RETURNING id INTO v_rental_id;

  -- CHECK 1 setup: outbound comm the app authored itself -- confirmed by
  -- construction, no human match step needed.
  INSERT INTO platform.communication
    (source_table, source_id, direction, channel, occurred_at, from_ref, to_ref,
     subject, source_system, match_status, matched_by, matched_at, created_by)
  VALUES
    ('rental', v_rental_id, 'outbound', 'email', now(), 'elektrica@example.com', 'renter@example.com',
     'Your rental agreement', 'app', 'confirmed', 'app', now(), 'test_harness')
  RETURNING id INTO v_comm_outbound_id;

  -- CHECK setup: inbound carrier email, auto-matched by claim number,
  -- pending human confirmation.
  INSERT INTO platform.communication
    (source_table, source_id, direction, channel, occurred_at, from_ref, to_ref,
     subject, source_system, match_status, match_evidence, created_by)
  VALUES
    ('rental', v_rental_id, 'inbound', 'email', now(), 'adjuster@carrier.example.com', 'demands@elektrica.example.com',
     'RE: Claim 12345', 'inbound_email_matcher', 'proposed', '{"matched_claim_number": "12345"}'::jsonb, 'test_harness')
  RETURNING id INTO v_comm_inbound_id;

  RAISE NOTICE 'vehicle_id=% rental_id=% outbound_comm_id=% inbound_comm_id=%',
    v_vehicle_id, v_rental_id, v_comm_outbound_id, v_comm_inbound_id;
END $$;

-- CHECK 1: outbound app-authored comm inserted as confirmed with matched_by/at set.
SELECT direction, channel, match_status, matched_by IS NOT NULL AS has_matched_by
FROM platform.communication
WHERE source_system = 'app';
-- EXPECT: 1 row, direction=outbound, match_status=confirmed, has_matched_by=true

-- CHECK 2: inbound proposed comm surfaces in the pending-match queue view.
SELECT direction, subject, match_evidence
FROM platform.pending_communication_matches
WHERE source_system = 'inbound_email_matcher';
-- EXPECT: 1 row, direction=inbound, subject='RE: Claim 12345'

-- CHECK 3: match-fields-together constraint rejects 'proposed' with matched_by set.
DO $$
BEGIN
  BEGIN
    INSERT INTO platform.communication
      (source_table, source_id, direction, channel, occurred_at, source_system,
       match_status, matched_by, matched_at, created_by)
    VALUES
      ('rental', 999999, 'inbound', 'email', now(), 'test_bad',
       'proposed', 'someone', now(), 'test_harness');
    RAISE EXCEPTION 'CHECK 3 FAILED: proposed with matched_by/at set should have been rejected';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'CHECK 3 PASSED: match-fields-together constraint enforced';
  END;
END $$;

-- CHECK 4: confirming a proposed match (the one-time decision) succeeds.
DO $$
DECLARE
  v_comm_id BIGINT;
BEGIN
  SELECT id INTO v_comm_id FROM platform.communication WHERE source_system = 'inbound_email_matcher';
  UPDATE platform.communication
  SET match_status = 'confirmed', matched_by = 'test_harness', matched_at = now()
  WHERE id = v_comm_id;
END $$;

SELECT match_status, matched_by IS NOT NULL AS has_matched_by
FROM platform.communication WHERE source_system = 'inbound_email_matcher';
-- EXPECT: 1 row, match_status=confirmed, has_matched_by=true

-- CHECK 5: once decided, cannot be re-decided.
DO $$
DECLARE
  v_comm_id BIGINT;
BEGIN
  SELECT id INTO v_comm_id FROM platform.communication WHERE source_system = 'inbound_email_matcher';
  BEGIN
    UPDATE platform.communication SET match_status = 'rejected', matched_by = 'someone_else', matched_at = now()
    WHERE id = v_comm_id;
    RAISE EXCEPTION 'CHECK 5 FAILED: re-deciding an already-decided communication should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%match decision cannot be changed once made%' THEN
      RAISE NOTICE 'CHECK 5 PASSED: match-decision immutability enforced (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 6: substantive fields (subject etc.) cannot be edited even while
-- still 'proposed'.
DO $$
DECLARE
  v_rental_id BIGINT;
  v_vehicle_id BIGINT;
  v_comm_id BIGINT;
BEGIN
  SELECT id INTO v_vehicle_id FROM elektrica.vehicle WHERE vin = 'TESTVIN0000000099';
  SELECT r.id INTO v_rental_id FROM elektrica.rental r WHERE r.vehicle_id = v_vehicle_id;

  INSERT INTO platform.communication
    (source_table, source_id, direction, channel, occurred_at, subject, source_system,
     match_status, match_evidence, created_by)
  VALUES
    ('rental', v_rental_id, 'inbound', 'email', now(), 'RE: Claim 99999', 'inbound_email_matcher_2',
     'proposed', '{"matched_claim_number": "99999"}'::jsonb, 'test_harness')
  RETURNING id INTO v_comm_id;

  BEGIN
    UPDATE platform.communication SET subject = 'tampered subject' WHERE id = v_comm_id;
    RAISE EXCEPTION 'CHECK 6 FAILED: editing subject should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%immutable except for its one-time match decision%' THEN
      RAISE NOTICE 'CHECK 6 PASSED: substantive-field immutability enforced (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 7: append-only -- DELETE rejected.
DO $$
DECLARE
  v_comm_id BIGINT;
BEGIN
  SELECT id INTO v_comm_id FROM platform.communication WHERE source_system = 'inbound_email_matcher_2';
  BEGIN
    DELETE FROM platform.communication WHERE id = v_comm_id;
    RAISE EXCEPTION 'CHECK 7 FAILED: DELETE should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only%' THEN
      RAISE NOTICE 'CHECK 7 PASSED: platform.communication DELETE blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 8: rejecting a proposed match is a valid decision path too (not
-- just confirming) -- e.g. a wrong-claim-number auto-match a human catches.
DO $$
DECLARE
  v_rental_id BIGINT;
  v_vehicle_id BIGINT;
  v_comm_id BIGINT;
BEGIN
  SELECT id INTO v_vehicle_id FROM elektrica.vehicle WHERE vin = 'TESTVIN0000000099';
  SELECT r.id INTO v_rental_id FROM elektrica.rental r WHERE r.vehicle_id = v_vehicle_id;

  INSERT INTO platform.communication
    (source_table, source_id, direction, channel, occurred_at, subject, source_system,
     match_status, match_evidence, created_by)
  VALUES
    ('rental', v_rental_id, 'inbound', 'email', now(), 'RE: Claim WRONG', 'inbound_email_matcher_3',
     'proposed', '{"matched_claim_number": "WRONG"}'::jsonb, 'test_harness')
  RETURNING id INTO v_comm_id;

  UPDATE platform.communication
  SET match_status = 'rejected', matched_by = 'test_harness', matched_at = now()
  WHERE id = v_comm_id;
END $$;

SELECT match_status FROM platform.communication WHERE source_system = 'inbound_email_matcher_3';
-- EXPECT: 1 row, match_status=rejected

SELECT 'ALL CHECKS COMPLETED' AS summary;
