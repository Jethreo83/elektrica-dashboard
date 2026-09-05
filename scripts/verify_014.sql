-- Verification harness for migration 014 (elektrica.demand carrier_id/
-- adjuster_id FK wiring, replacing the migration-006 placeholder
-- carrier_name/adjuster_name free-text columns).
--
-- Run statement-by-statement (each DO $$ ... $$ block is already its
-- own top-level statement) -- NOT as one multi-statement .execute() --
-- per the transaction-boundary trap documented in verify_013.sql's
-- CHECK 6 comment (now() is fixed at transaction start, so any
-- before/after now() comparison collapsed into one implicit transaction
-- gives a false result). This script has no now()-comparison check, but
-- keeping the same execution discipline avoids reintroducing that class
-- of bug in a future check added here.

DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_rental_id BIGINT;
  v_carrier_id BIGINT;
  v_carrier2_id BIGINT;
  v_adjuster_id BIGINT;
  v_adjuster2_id BIGINT;
  v_demand_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, class, status, created_by, updated_by)
  VALUES ('TESTVIN0000000014', 'ev', 'available', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'Migration014Renter', 'test.migration014renter@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.renter (person_id, created_by)
  VALUES (v_person_id, 'test_harness')
  RETURNING id INTO v_renter_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  VALUES (v_vehicle_id, v_renter_id, 'carrier', 'test_harness', 'test_harness')
  RETURNING id INTO v_rental_id;

  INSERT INTO platform.insurance_carrier (name, created_by, updated_by)
  VALUES ('Migration014 Test Carrier', 'test_harness', 'test_harness')
  RETURNING id INTO v_carrier_id;

  INSERT INTO platform.insurance_carrier (name, created_by, updated_by)
  VALUES ('Migration014 Test Carrier Two', 'test_harness', 'test_harness')
  RETURNING id INTO v_carrier2_id;

  INSERT INTO platform.adjuster (carrier_id, name, created_by, updated_by)
  VALUES (v_carrier_id, 'Migration014 Adjuster', 'test_harness', 'test_harness')
  RETURNING id INTO v_adjuster_id;

  INSERT INTO platform.adjuster (carrier_id, name, created_by, updated_by)
  VALUES (v_carrier2_id, 'Migration014 Adjuster Two', 'test_harness', 'test_harness')
  RETURNING id INTO v_adjuster2_id;

  INSERT INTO elektrica.demand
    (rental_id, demand_type, recipient_type, carrier_id, adjuster_id, amount, created_by, updated_by)
  VALUES
    (v_rental_id, 'primary_insurer', 'carrier', v_carrier_id, v_adjuster_id, 450.00, 'test_harness', 'test_harness')
  RETURNING id INTO v_demand_id;

  RAISE NOTICE 'rental_id=% carrier_id=% adjuster_id=% demand_id=%', v_rental_id, v_carrier_id, v_adjuster_id, v_demand_id;
END $$;

-- CHECK 1: demand created with carrier_id/adjuster_id, no carrier_name/
-- adjuster_name columns exist any more.
SELECT d.carrier_id, d.adjuster_id, c.name AS carrier_name, a.name AS adjuster_name
FROM elektrica.demand d
JOIN platform.insurance_carrier c ON c.id = d.carrier_id
JOIN platform.adjuster a ON a.id = d.adjuster_id
WHERE c.name = 'Migration014 Test Carrier';
-- EXPECT: 1 row, carrier_name='Migration014 Test Carrier', adjuster_name='Migration014 Adjuster'

-- CHECK 2: carrier_name/adjuster_name columns are actually gone.
SELECT count(*) AS n_old_columns
FROM information_schema.columns
WHERE table_schema = 'elektrica' AND table_name = 'demand'
  AND column_name IN ('carrier_name', 'adjuster_name');
-- EXPECT: n_old_columns = 0

-- CHECK 3: recipient_type='carrier' without carrier_id rejected (the
-- FK-based replacement for the old free-text CHECK).
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000014';
  BEGIN
    INSERT INTO elektrica.demand (rental_id, demand_type, recipient_type, amount, created_by, updated_by)
    VALUES (v_rental_id, 'primary_insurer', 'carrier', 100.00, 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 3 FAILED: missing carrier_id should have been rejected';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'CHECK 3 PASSED: demand_carrier_required_for_carrier_recipient enforced';
  END;
END $$;

-- CHECK 4: a bad carrier_id (FK violation) is rejected.
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000014';
  BEGIN
    INSERT INTO elektrica.demand (rental_id, demand_type, recipient_type, carrier_id, amount, created_by, updated_by)
    VALUES (v_rental_id, 'primary_insurer', 'carrier', 999999999, 100.00, 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 4 FAILED: bad carrier_id should have been rejected';
  EXCEPTION WHEN foreign_key_violation THEN
    RAISE NOTICE 'CHECK 4 PASSED: demand.carrier_id FK enforced';
  END;
END $$;

-- CHECK 5: adjuster_id belonging to a DIFFERENT carrier than carrier_id
-- is rejected (the new cross-table invariant this migration adds).
DO $$
DECLARE
  v_rental_id BIGINT;
  v_carrier_id BIGINT;
  v_adjuster2_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000014';
  SELECT id INTO v_carrier_id FROM platform.insurance_carrier WHERE name = 'Migration014 Test Carrier';
  SELECT id INTO v_adjuster2_id FROM platform.adjuster WHERE name = 'Migration014 Adjuster Two';

  BEGIN
    INSERT INTO elektrica.demand
      (rental_id, demand_type, recipient_type, carrier_id, adjuster_id, amount, created_by, updated_by)
    VALUES (v_rental_id, 'primary_insurer', 'carrier', v_carrier_id, v_adjuster2_id, 100.00, 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 5 FAILED: mismatched adjuster/carrier should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%belongs to carrier_id%but demand.carrier_id is%' THEN
      RAISE NOTICE 'CHECK 5 PASSED: trg_demand_check_adjuster_carrier_match enforced (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 6: recipient_type='renter' demand needs no carrier_id at all
-- (unchanged behavior, confirms the new CHECK didn't over-tighten).
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000014';
  INSERT INTO elektrica.demand (rental_id, demand_type, recipient_type, amount, created_by, updated_by)
  VALUES (v_rental_id, 'balance_to_renter', 'renter', 75.00, 'test_harness', 'test_harness');
  RAISE NOTICE 'CHECK 6 PASSED: renter-recipient demand created with no carrier_id';
END $$;

-- CHECK 7: UPDATE path also enforced -- moving an existing demand's
-- carrier_id to a different carrier while keeping the old adjuster_id
-- is rejected by the same trigger (BEFORE INSERT OR UPDATE).
DO $$
DECLARE
  v_demand_id BIGINT;
  v_carrier2_id BIGINT;
BEGIN
  SELECT d.id INTO v_demand_id FROM elektrica.demand d
    JOIN platform.insurance_carrier c ON c.id = d.carrier_id
    WHERE c.name = 'Migration014 Test Carrier';
  SELECT id INTO v_carrier2_id FROM platform.insurance_carrier WHERE name = 'Migration014 Test Carrier Two';

  BEGIN
    UPDATE elektrica.demand SET carrier_id = v_carrier2_id WHERE id = v_demand_id;
    RAISE EXCEPTION 'CHECK 7 FAILED: UPDATE creating a mismatched adjuster/carrier should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%belongs to carrier_id%but demand.carrier_id is%' THEN
      RAISE NOTICE 'CHECK 7 PASSED: trigger also fires on UPDATE';
    ELSE
      RAISE;
    END IF;
  END;
END $$;

SELECT 'ALL CHECKS COMPLETED' AS summary;
