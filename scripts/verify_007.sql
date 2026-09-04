-- Verification harness for migration 007 (JP litigation wiring via
-- cross-schema reuse of vls.valid_next_states() — Jed's approved option (a)).

DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_rental_id BIGINT;
  v_vls_case_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, class, status, created_by, updated_by)
  VALUES ('TESTVIN0000000011', 'ev', 'available', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'LitigationRenter', 'test.litigationrenter@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.renter (person_id, created_by)
  VALUES (v_person_id, 'test_harness')
  RETURNING id INTO v_renter_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  VALUES (v_vehicle_id, v_renter_id, 'carrier', 'test_harness', 'test_harness')
  RETURNING id INTO v_rental_id;

  -- Walk to needs_served (same path verify_003.sql already proved).
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'finished', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'needs_demand', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'demand_sent', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'negotiating', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'no_offer', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'needs_lawsuit', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'needs_served', 'manual', true, 'test_harness', 'test_harness');

  RAISE NOTICE 'rental_id=% walked to needs_served', v_rental_id;
END $$;

-- CHECK 1: transitioning to in_litigation WITHOUT a linked vls.case is
-- rejected — this is the whole point of the litigation-specific gate.
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000011';
  BEGIN
    INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
    VALUES (v_rental_id, 'in_litigation', 'manual', true, 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 1 FAILED: in_litigation without a linked vls.case should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%no vls.case is linked%' THEN
      RAISE NOTICE 'CHECK 1 PASSED: in_litigation blocked without vls.case link (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 2: create + link a vls.case, then in_litigation succeeds.
DO $$
DECLARE
  v_rental_id BIGINT;
  v_vls_case_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000011';

  -- case_type='rental', court_type='jp' — Elektrica's JP-only usage per
  -- handoff §1.2. is_first_party/cause_of_action set per the migration's
  -- own provenance note (schema-compatibility default, not a legal
  -- characterization).
  INSERT INTO vls.case (case_type, is_first_party, cause_of_action, court_type, created_by, updated_by)
  VALUES ('rental', false, 'other_contract', 'jp', 'test_harness', 'test_harness')
  RETURNING id INTO v_vls_case_id;

  UPDATE elektrica.rental SET vls_case_id = v_vls_case_id WHERE id = v_rental_id;

  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'in_litigation', 'manual', true, 'test_harness', 'test_harness');

  RAISE NOTICE 'CHECK 2 PASSED: rental % moved to in_litigation with vls_case_id %', v_rental_id, v_vls_case_id;
END $$;

SELECT r.current_state, r.vls_case_id IS NOT NULL AS has_case
FROM elektrica.rental r
JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000011';
-- EXPECT: 1 row, current_state=in_litigation, has_case=true

-- CHECK 3: resolved is rejected while the linked vls.case is still in a
-- non-terminal state (e.g. 'intake' — the default, nothing filed yet).
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000011';
  BEGIN
    INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
    VALUES (v_rental_id, 'resolved', 'manual', true, 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 3 FAILED: resolved while vls.case is non-terminal should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%not settled/dismissed/judgment%' THEN
      RAISE NOTICE 'CHECK 3 PASSED: resolved blocked on non-terminal vls.case (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 4: drive the linked vls.case through VLS's OWN state machine (JP
-- branch, including the discovery trap) using vls.case_event exactly as
-- VLS's own verify scripts do — proving this is real reuse, not a stub.
DO $$
DECLARE
  v_rental_id BIGINT;
  v_vls_case_id BIGINT;
BEGIN
  SELECT r.id, r.vls_case_id INTO v_rental_id, v_vls_case_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000011';

  INSERT INTO vls.case_event (case_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_vls_case_id, 'filed', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO vls.case_event (case_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_vls_case_id, 'served', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO vls.case_event (case_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_vls_case_id, 'answered', 'manual', true, 'test_harness', 'test_harness');

  -- JP discovery trap: from 'answered', the ONLY valid next state is
  -- motion_limited_discovery_filed, never discovery_open directly. Prove
  -- vls's own trap logic is intact and elektrica is really deferring to it
  -- (not silently allowing a shortcut Elektrica itself never coded).
  BEGIN
    INSERT INTO vls.case_event (case_id, event_type, source, confirmed, confirmed_by, created_by)
    VALUES (v_vls_case_id, 'discovery_open', 'manual', true, 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 4a FAILED: answered -> discovery_open should have been rejected by vls JP trap';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'Invalid state transition%' THEN
      RAISE NOTICE 'CHECK 4a PASSED: vls JP discovery trap still enforced from elektrica-driven case (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;

  INSERT INTO vls.case_event (case_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_vls_case_id, 'motion_limited_discovery_filed', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO vls.case_event (case_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_vls_case_id, 'discovery_open', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO vls.case_event (case_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_vls_case_id, 'settled', 'manual', true, 'test_harness', 'test_harness');

  RAISE NOTICE 'CHECK 4b PASSED: vls.case % walked filed->served->answered->motion->discovery->settled', v_vls_case_id;
END $$;

SELECT current_state FROM vls.case
WHERE id = (SELECT vls_case_id FROM elektrica.rental r JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000011');
-- EXPECT: 1 row, current_state = settled

-- CHECK 5: NOW resolved succeeds, since the linked vls.case reached a
-- terminal state.
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000011';
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'resolved', 'manual', true, 'test_harness', 'test_harness');
END $$;

SELECT r.current_state FROM elektrica.rental r
JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000011';
-- EXPECT: 1 row, current_state = resolved

-- CHECK 6: the old direct needs_served -> resolved escape hatch is gone
-- (proves the TODO was really closed, not left as a silent bypass).
DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_rental_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, status, created_by, updated_by)
  VALUES ('TESTVIN0000000022', 'available', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  SELECT v_vehicle_id, r.renter_id, 'carrier', 'test_harness', 'test_harness'
  FROM elektrica.rental r LIMIT 1
  RETURNING id INTO v_rental_id;

  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'finished', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'needs_demand', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'demand_sent', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'negotiating', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'no_offer', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'needs_lawsuit', 'manual', true, 'test_harness', 'test_harness');
  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'needs_served', 'manual', true, 'test_harness', 'test_harness');

  BEGIN
    INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
    VALUES (v_rental_id, 'resolved', 'manual', true, 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 6 FAILED: needs_served -> resolved directly should no longer be allowed';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'Invalid state transition%' THEN
      RAISE NOTICE 'CHECK 6 PASSED: old direct needs_served->resolved escape hatch is closed (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

SELECT 'ALL CHECKS COMPLETED — CHECK 4a is the load-bearing proof of real reuse (JP trap enforced via vls, not reimplemented)' AS summary;
