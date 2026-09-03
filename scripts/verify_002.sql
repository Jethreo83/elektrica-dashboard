-- Verification harness for migration 002 (elektrica.vehicle).
-- STAGING ONLY — this migration is not promoted to production (placeholder
-- enum values, see the banner in migrations/002_elektrica_vehicle.sql).
-- This script just confirms the shape works as designed; it does NOT and
-- cannot confirm the enum values are correct — that needs the real export.

DO $$
DECLARE
  v_vehicle_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, class, status, tracking_system, created_by, updated_by)
  VALUES ('TESTVIN0000000001', 'ev', 'available', 'bouncie', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  RAISE NOTICE 'vehicle_id=%', v_vehicle_id;
END $$;

-- CHECK 1: row exists with expected columns.
SELECT vin, class, status, tracking_system FROM elektrica.vehicle WHERE vin = 'TESTVIN0000000001';
-- EXPECT: 1 row, class=ev, status=available, tracking_system=bouncie

-- CHECK 2: vin uniqueness enforced.
DO $$
BEGIN
  INSERT INTO elektrica.vehicle (vin, status, created_by, updated_by)
  VALUES ('TESTVIN0000000001', 'available', 'test_harness', 'test_harness');
  RAISE EXCEPTION 'CHECK 2 FAILED: duplicate VIN should have been rejected';
EXCEPTION WHEN unique_violation THEN
  RAISE NOTICE 'CHECK 2 PASSED: vin uniqueness enforced';
END $$;

-- CHECK 3: elektrica_app can read/write elektrica.vehicle (explicit grant
-- in migration 002, since ALL TABLES IN SCHEMA grants in Postgres are a
-- snapshot at GRANT time, not dynamic — migration 001's blanket grant does
-- not retroactively cover this table without the explicit re-grant).
SET ROLE elektrica_app;
SELECT vin, class FROM elektrica.vehicle WHERE vin = 'TESTVIN0000000001';
-- EXPECT: 1 row
UPDATE elektrica.vehicle SET updated_by = 'elektrica_app', updated_at = now() WHERE vin = 'TESTVIN0000000001';
-- EXPECT: UPDATE 1, no error
RESET ROLE;

-- CHECK 4: default status is 'available' when omitted.
DO $$
DECLARE
  v_status elektrica.vehicle_status;
BEGIN
  INSERT INTO elektrica.vehicle (vin, created_by, updated_by)
  VALUES ('TESTVIN0000000002', 'test_harness', 'test_harness');

  SELECT status INTO v_status FROM elektrica.vehicle WHERE vin = 'TESTVIN0000000002';

  IF v_status <> 'available' THEN
    RAISE EXCEPTION 'CHECK 4 FAILED: expected default status available, got %', v_status;
  END IF;
  RAISE NOTICE 'CHECK 4 PASSED: default status is available';
END $$;

SELECT 'ALL CHECKS COMPLETED — reminder: enum values here are PLACEHOLDER, staging only' AS summary;
