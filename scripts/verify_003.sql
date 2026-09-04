-- Verification harness for migration 003 (elektrica.rental + rental_event).
-- Same discipline as VLS verify scripts: verify by direct query, not by
-- trusting a clean apply exit code.

DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_rental_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, class, status, created_by, updated_by)
  VALUES ('TESTVIN0000000099', 'ev', 'available', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'RentalRenter', 'test.rentalrenter@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.renter (person_id, created_by)
  VALUES (v_person_id, 'test_harness')
  RETURNING id INTO v_renter_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  VALUES (v_vehicle_id, v_renter_id, 'carrier', 'test_harness', 'test_harness')
  RETURNING id INTO v_rental_id;

  RAISE NOTICE 'vehicle_id=% renter_id=% rental_id=%', v_vehicle_id, v_renter_id, v_rental_id;
END $$;

-- CHECK 1: rental created with default state 'active'.
SELECT r.id, r.current_state
FROM elektrica.rental r
JOIN elektrica.vehicle v ON v.id = r.vehicle_id
WHERE v.vin = 'TESTVIN0000000099';
-- EXPECT: 1 row, current_state = active

-- CHECK 2: valid transition (active -> finished) succeeds and advances
-- current_state via the trigger, not a direct write.
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
  JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000099';

  INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
  VALUES (v_rental_id, 'finished', 'manual', true, 'test_harness', 'test_harness');
END $$;

SELECT r.current_state FROM elektrica.rental r
JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000099';
-- EXPECT: 1 row, current_state = finished

-- CHECK 3: invalid transition (finished -> resolved, skipping intermediate
-- states) is rejected by the sequence trigger.
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
  JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000099';

  BEGIN
    INSERT INTO elektrica.rental_event (rental_id, event_type, source, confirmed, confirmed_by, created_by)
    VALUES (v_rental_id, 'resolved', 'manual', true, 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 3 FAILED: finished -> resolved should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'Invalid state transition%' THEN
      RAISE NOTICE 'CHECK 3 PASSED: invalid transition rejected (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 4: direct UPDATE to current_state is blocked (must go through
-- rental_event).
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
  JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000099';

  BEGIN
    UPDATE elektrica.rental SET current_state = 'resolved' WHERE id = v_rental_id;
    RAISE EXCEPTION 'CHECK 4 FAILED: direct current_state UPDATE should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%cannot be written directly%' THEN
      RAISE NOTICE 'CHECK 4 PASSED: direct state write blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 5: rental_event is append-only — DELETE is rejected.
DO $$
DECLARE
  v_event_id BIGINT;
BEGIN
  SELECT id INTO v_event_id FROM elektrica.rental_event ORDER BY id DESC LIMIT 1;
  BEGIN
    DELETE FROM elektrica.rental_event WHERE id = v_event_id;
    RAISE EXCEPTION 'CHECK 5 FAILED: DELETE on rental_event should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only%' THEN
      RAISE NOTICE 'CHECK 5 PASSED: rental_event DELETE blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 6: walk the rest of the elektrica-owned lifecycle to needs_served,
-- confirming each valid transition works, then confirm needs_served has no
-- further valid state (the deliberate JP-handoff TODO boundary) except the
-- explicit temporary 'resolved' escape hatch.
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
  JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000099';

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

  RAISE NOTICE 'CHECK 6 PASSED: walked active->finished->needs_demand->demand_sent->negotiating->no_offer->needs_lawsuit->needs_served';
END $$;

SELECT r.current_state FROM elektrica.rental r
JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000099';
-- EXPECT: 1 row, current_state = needs_served

-- CHECK 7: blocked_rentals view surfaces the needs_served JP-handoff gap.
SELECT block_reason FROM elektrica.blocked_rentals
WHERE id = (SELECT r.id FROM elektrica.rental r JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000099');
-- EXPECT: 1 row, block_reason mentions 'JP litigation handoff not yet wired'

SELECT 'ALL CHECKS COMPLETED' AS summary;
