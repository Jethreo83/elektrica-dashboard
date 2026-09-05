-- Verification harness for migration 016 (elektrica.insurer_payment).
-- Verifies by direct query against live staging data, not exit codes.
-- Run statement-by-statement (each DO $$ block is its own top-level
-- statement already) to avoid the same "now() fixed at transaction
-- start" trap noted in verify_013.sql's own header.

-- Setup: a real carrier, a real vehicle/renter/rental, a resolved
-- carrier-recipient demand with a comparable_set and a payment row --
-- exercises the FULL automatic-population path end to end, not a bare
-- INSERT into insurer_payment directly.

DO $$
DECLARE
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_vehicle_id BIGINT;
  v_rental_id BIGINT;
  v_carrier_id BIGINT;
  v_adjuster_id BIGINT;
  v_demand_id BIGINT;
BEGIN
  INSERT INTO platform.person (first_name, last_name, created_by)
    VALUES ('Verify016', 'Testcase', 'verify_016') RETURNING id INTO v_person_id;
  INSERT INTO elektrica.renter (person_id, created_by) VALUES (v_person_id, 'verify_016') RETURNING id INTO v_renter_id;
  INSERT INTO elektrica.vehicle (vin, created_by, updated_by)
    VALUES ('VERIFY016VIN0000X', 'verify_016', 'verify_016') RETURNING id INTO v_vehicle_id;
  INSERT INTO elektrica.rental (vehicle_id, renter_id, start_date, end_date, created_by, updated_by)
    VALUES (v_vehicle_id, v_renter_id, '2026-01-01', '2026-01-10', 'verify_016', 'verify_016')
    RETURNING id INTO v_rental_id;

  INSERT INTO platform.insurance_carrier (name, created_by, updated_by)
    VALUES ('Verify016 Insurance Co', 'verify_016', 'verify_016') RETURNING id INTO v_carrier_id;
  INSERT INTO platform.adjuster (carrier_id, name, created_by, updated_by)
    VALUES (v_carrier_id, 'Verify016 Adjuster', 'verify_016', 'verify_016') RETURNING id INTO v_adjuster_id;

  INSERT INTO elektrica.demand (
    rental_id, demand_type, recipient_type, carrier_id, adjuster_id,
    amount, status, sent_via, sent_at, created_by, updated_by
  ) VALUES (
    v_rental_id, 'primary_insurer', 'carrier', v_carrier_id, v_adjuster_id,
    900.00, 'sent', 'fax', now() - INTERVAL '12 days', 'verify_016', 'verify_016'
  ) RETURNING id INTO v_demand_id;

  INSERT INTO elektrica.comparable_set (
    demand_id, scan_source, scan_timestamp, vehicle_class,
    date_range_start, date_range_end, comparables, computed_average, created_by
  ) VALUES (
    v_demand_id, 'verify_016_scan', now(), 'sedan',
    '2026-01-01', '2026-01-10',
    '[{"vendor":"Enterprise","vehicle":"Camry","daily_rate":45}]'::jsonb,
    45.00, 'verify_016'
  );

  INSERT INTO elektrica.payment (rental_id, demand_id, source, amount, created_by)
  VALUES (v_rental_id, v_demand_id, 'insurer_eft', 810.00, 'verify_016');

  -- The transition that should fire the trigger: draft/sent -> resolved.
  UPDATE elektrica.demand SET status = 'resolved', updated_by = 'verify_016' WHERE id = v_demand_id;

  RAISE NOTICE 'setup complete: demand_id=%', v_demand_id;
END $$;

-- CHECK 1: exactly one insurer_payment row was auto-created, with the
-- right amounts/dates pulled from the demand/comparable_set/payment.
SELECT ip.carrier_id, ip.adjuster_id, ip.vehicle_class,
       ip.market_rate_at_time, ip.amount_demanded, ip.amount_paid,
       ip.rental_start_date, ip.rental_end_date, ip.source, ip.frozen,
       ip.days_to_resolve IS NOT NULL AS has_days
FROM elektrica.insurer_payment ip
JOIN elektrica.demand d ON d.id = ip.demand_id
WHERE d.created_by = 'verify_016';
-- EXPECT: 1 row, vehicle_class='sedan', market_rate_at_time=45.00,
-- amount_demanded=900.00, amount_paid=810.00, source='system',
-- frozen=true, has_days=true

-- CHECK 2: re-resolving (no-op status flip does nothing, but even a
-- genuine second resolve attempt) does NOT create a second row --
-- ON CONFLICT DO NOTHING + the UNIQUE(demand_id) constraint.
DO $$
DECLARE
  v_demand_id BIGINT;
  v_count_before INTEGER;
  v_count_after INTEGER;
BEGIN
  SELECT id INTO v_demand_id FROM elektrica.demand WHERE created_by = 'verify_016';
  SELECT count(*) INTO v_count_before FROM elektrica.insurer_payment WHERE demand_id = v_demand_id;

  -- flip away and back to force the trigger condition again
  UPDATE elektrica.demand SET status = 'negotiating', updated_by = 'verify_016' WHERE id = v_demand_id;
  UPDATE elektrica.demand SET status = 'resolved', updated_by = 'verify_016' WHERE id = v_demand_id;

  SELECT count(*) INTO v_count_after FROM elektrica.insurer_payment WHERE demand_id = v_demand_id;

  IF v_count_before = 1 AND v_count_after = 1 THEN
    RAISE NOTICE 'CHECK 2 PASSED: re-resolve did not duplicate the insurer_payment row (count stayed at 1)';
  ELSE
    RAISE EXCEPTION 'CHECK 2 FAILED: count_before=% count_after=%', v_count_before, v_count_after;
  END IF;
END $$;

-- CHECK 3: a 'balance_to_renter' demand resolving does NOT create an
-- insurer_payment row (handoff §2.8 is carrier/adjuster-specific).
DO $$
DECLARE
  v_rental_id BIGINT;
  v_demand_id BIGINT;
  v_count INTEGER;
BEGIN
  SELECT id INTO v_rental_id FROM elektrica.rental
  WHERE created_by = 'verify_016' LIMIT 1;

  INSERT INTO elektrica.demand (
    rental_id, demand_type, recipient_type, amount, status, created_by, updated_by
  ) VALUES (
    v_rental_id, 'balance_to_renter', 'renter', 150.00, 'draft', 'verify_016', 'verify_016'
  ) RETURNING id INTO v_demand_id;

  UPDATE elektrica.demand SET status = 'resolved', updated_by = 'verify_016' WHERE id = v_demand_id;

  SELECT count(*) INTO v_count FROM elektrica.insurer_payment WHERE demand_id = v_demand_id;

  IF v_count = 0 THEN
    RAISE NOTICE 'CHECK 3 PASSED: balance_to_renter resolve created no insurer_payment row';
  ELSE
    RAISE EXCEPTION 'CHECK 3 FAILED: expected 0 rows, got %', v_count;
  END IF;
END $$;

-- CHECK 4: direct UPDATE/DELETE on insurer_payment are blocked (frozen).
DO $$
DECLARE
  v_id BIGINT;
BEGIN
  SELECT ip.id INTO v_id FROM elektrica.insurer_payment ip
  JOIN elektrica.demand d ON d.id = ip.demand_id WHERE d.created_by = 'verify_016' LIMIT 1;

  BEGIN
    UPDATE elektrica.insurer_payment SET amount_paid = 999 WHERE id = v_id;
    RAISE EXCEPTION 'CHECK 4a FAILED: UPDATE should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only/frozen%' THEN
      RAISE NOTICE 'CHECK 4a PASSED: UPDATE blocked';
    ELSE
      RAISE;
    END IF;
  END;

  BEGIN
    DELETE FROM elektrica.insurer_payment WHERE id = v_id;
    RAISE EXCEPTION 'CHECK 4b FAILED: DELETE should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only/frozen%' THEN
      RAISE NOTICE 'CHECK 4b PASSED: DELETE blocked';
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 5: the exhibit view joins carrier/adjuster names correctly.
SELECT carrier_name, adjuster_name, vehicle_class, amount_demanded, amount_paid
FROM elektrica.insurer_payment_exhibit
WHERE carrier_name = 'Verify016 Insurance Co';
-- EXPECT: 1 row, adjuster_name='Verify016 Adjuster'

-- CHECK 6: elektrica_app has SELECT/INSERT but not UPDATE/DELETE.
SELECT
  has_table_privilege('elektrica_app', 'elektrica.insurer_payment', 'SELECT') AS can_select,
  has_table_privilege('elektrica_app', 'elektrica.insurer_payment', 'INSERT') AS can_insert,
  has_table_privilege('elektrica_app', 'elektrica.insurer_payment', 'UPDATE') AS can_update,
  has_table_privilege('elektrica_app', 'elektrica.insurer_payment', 'DELETE') AS can_delete;
-- EXPECT: can_select=t, can_insert=t, can_update=f, can_delete=f

SELECT 'ALL CHECKS COMPLETED' AS summary;
