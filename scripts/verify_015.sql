-- Verification for migration 015 (drop elektrica.vehicle.class and
-- elektrica.vehicle.tracking_system, per Jed's confirmed answer that
-- these columns don't exist in the real Fleet data).

-- CHECK 1: the columns are actually gone.
SELECT count(*) AS n_class_or_tracking_columns
FROM information_schema.columns
WHERE table_schema = 'elektrica' AND table_name = 'vehicle'
  AND column_name IN ('class', 'tracking_system');
-- EXPECT: n_class_or_tracking_columns = 0

-- CHECK 2: elektrica.tracking_system TYPE is gone.
SELECT count(*) AS n_tracking_system_type
FROM pg_type WHERE typname = 'tracking_system' AND typnamespace = 'elektrica'::regnamespace;
-- EXPECT: n_tracking_system_type = 0

-- CHECK 3: elektrica.vehicle_class TYPE still exists (still used by
-- comparable_set -- this migration must NOT have dropped it).
SELECT count(*) AS n_vehicle_class_type
FROM pg_type WHERE typname = 'vehicle_class' AND typnamespace = 'elektrica'::regnamespace;
-- EXPECT: n_vehicle_class_type = 1

-- CHECK 4: elektrica.vehicle still works for everything else -- insert a
-- row with only the remaining real columns, confirm it round-trips.
DO $$
DECLARE
  v_vehicle_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, status, notes, created_by, updated_by)
  VALUES ('TESTVIN0000000200', 'available', 'post-drop smoke row', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  RAISE NOTICE 'CHECK 4 PASSED: vehicle_id=% created without class/tracking_system columns', v_vehicle_id;
END $$;

SELECT vin, status, notes FROM elektrica.vehicle WHERE vin = 'TESTVIN0000000200';
-- EXPECT: 1 row

-- CHECK 5: elektrica.comparable_set.vehicle_class still works (uses
-- elektrica.vehicle_class the TYPE directly, not FK'd to vehicle.class --
-- confirms the type survived and comparable_set is unaffected by the
-- column drop, per this migration's own header note).
DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_rental_id BIGINT;
  v_demand_id BIGINT;
BEGIN
  SELECT id INTO v_vehicle_id FROM elektrica.vehicle WHERE vin = 'TESTVIN0000000200';

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'PostDropRenter', 'test.postdroprenter@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.renter (person_id, created_by)
  VALUES (v_person_id, 'test_harness')
  RETURNING id INTO v_renter_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  VALUES (v_vehicle_id, v_renter_id, 'carrier', 'test_harness', 'test_harness')
  RETURNING id INTO v_rental_id;

  INSERT INTO elektrica.demand (rental_id, demand_type, recipient_type, carrier_id, amount, created_by, updated_by)
  SELECT v_rental_id, 'primary_insurer', 'carrier', c.id, 50.00, 'test_harness', 'test_harness'
  FROM platform.insurance_carrier c LIMIT 1
  RETURNING id INTO v_demand_id;

  IF v_demand_id IS NULL THEN
    -- No carrier exists yet in this staging run -- create one so this
    -- check can still exercise comparable_set.vehicle_class, which is
    -- the actual thing under test here, not the demand/carrier wiring
    -- (that's migration 013/014's own concern).
    INSERT INTO platform.insurance_carrier (name, created_by, updated_by)
    VALUES ('Test Carrier Post-Drop', 'test_harness', 'test_harness')
    RETURNING id INTO v_demand_id; -- reuse var, holds carrier id now
    INSERT INTO elektrica.demand (rental_id, demand_type, recipient_type, carrier_id, amount, created_by, updated_by)
    VALUES (v_rental_id, 'primary_insurer', 'carrier', v_demand_id, 50.00, 'test_harness', 'test_harness')
    RETURNING id INTO v_demand_id;
  END IF;

  INSERT INTO elektrica.comparable_set
    (demand_id, scan_source, scan_timestamp, vehicle_class, date_range_start, date_range_end,
     comparables, computed_average, created_by)
  VALUES
    (v_demand_id, 'kayak', now(), 'ev', CURRENT_DATE - 3, CURRENT_DATE,
     '[{"vendor": "Hertz", "vehicle": "Tesla Model 3", "daily_rate": 65.00}]'::jsonb,
     65.00, 'test_harness');

  RAISE NOTICE 'CHECK 5 PASSED: comparable_set.vehicle_class still works post-drop';
END $$;

SELECT scan_source, vehicle_class FROM elektrica.comparable_set WHERE scan_source = 'kayak' ORDER BY id DESC LIMIT 1;
-- EXPECT: 1 row, vehicle_class = ev

SELECT 'ALL CHECKS COMPLETED' AS summary;
