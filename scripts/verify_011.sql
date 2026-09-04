-- Verification harness for migration 011 (elektrica.staff_user).

DO $$
DECLARE
  v_person_id BIGINT;
  v_owner_id BIGINT;
BEGIN
  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Jed', 'TestOwner', 'jed.testowner@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.staff_user (person_id, role, google_email, created_by, updated_by)
  VALUES (v_person_id, 'owner', 'jed@elektricarentals.com', 'test_harness', 'test_harness')
  RETURNING id INTO v_owner_id;

  RAISE NOTICE 'owner staff_user_id=%', v_owner_id;
END $$;

-- CHECK 1: staff_user row created correctly.
SELECT role, google_email, active FROM elektrica.staff_user WHERE google_email = 'jed@elektricarentals.com';
-- EXPECT: 1 row, role=owner, active=true

-- CHECK 2: domain restriction enforced.
DO $$
DECLARE
  v_person_id BIGINT;
BEGIN
  INSERT INTO platform.person (first_name, last_name, created_by)
  VALUES ('Bad', 'Domain', 'test_harness')
  RETURNING id INTO v_person_id;

  BEGIN
    INSERT INTO elektrica.staff_user (person_id, role, google_email, created_by, updated_by)
    VALUES (v_person_id, 'staff', 'someone@gmail.com', 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 2 FAILED: non-elektricarentals.com email should have been rejected';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'CHECK 2 PASSED: staff_user_email_domain enforced';
  END;
END $$;

-- CHECK 3: one row per person enforced.
DO $$
DECLARE
  v_person_id BIGINT;
BEGIN
  SELECT person_id INTO v_person_id FROM elektrica.staff_user WHERE google_email = 'jed@elektricarentals.com';
  BEGIN
    INSERT INTO elektrica.staff_user (person_id, role, google_email, created_by, updated_by)
    VALUES (v_person_id, 'staff', 'jed2@elektricarentals.com', 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 3 FAILED: duplicate person_id should have been rejected';
  EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE 'CHECK 3 PASSED: staff_user_one_row_per_person enforced';
  END;
END $$;

-- CHECK 4: bootstrap chain — a second staff_user can be provisioned by
-- the first (provisioned_by_staff_user_id).
DO $$
DECLARE
  v_owner_staff_id BIGINT;
  v_person_id BIGINT;
  v_staff_id BIGINT;
BEGIN
  SELECT id INTO v_owner_staff_id FROM elektrica.staff_user WHERE google_email = 'jed@elektricarentals.com';

  INSERT INTO platform.person (first_name, last_name, created_by)
  VALUES ('Second', 'StaffMember', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.staff_user
    (person_id, role, google_email, provisioned_by_staff_user_id, created_by, updated_by)
  VALUES
    (v_person_id, 'staff', 'second@elektricarentals.com', v_owner_staff_id, 'test_harness', 'test_harness')
  RETURNING id INTO v_staff_id;

  RAISE NOTICE 'CHECK 4 PASSED: staff_user % provisioned by owner staff_user %', v_staff_id, v_owner_staff_id;
END $$;

-- CHECK 5: elektrica_app has SELECT-only (mirrors vls_app's tighter
-- pattern) — INSERT should be rejected for elektrica_app.
SET ROLE elektrica_app;
SELECT google_email FROM elektrica.staff_user WHERE role = 'owner';
-- EXPECT: 1 row, no error
DO $$
BEGIN
  BEGIN
    INSERT INTO elektrica.staff_user (person_id, role, google_email, created_by, updated_by)
    VALUES (999999, 'staff', 'should-fail@elektricarentals.com', 'elektrica_app', 'elektrica_app');
    RAISE EXCEPTION 'CHECK 5 FAILED: elektrica_app should not be able to INSERT into staff_user';
  EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'CHECK 5 PASSED: elektrica_app blocked from INSERT on staff_user (SELECT-only, matches vls_app pattern)';
  END;
END $$;
RESET ROLE;

-- CHECK 6: updated_at trigger fires on UPDATE (deactivating a staff member).
DO $$
DECLARE
  v_staff_id BIGINT;
  v_updated_before TIMESTAMPTZ;
  v_updated_after TIMESTAMPTZ;
BEGIN
  SELECT id, updated_at INTO v_staff_id, v_updated_before FROM elektrica.staff_user WHERE google_email = 'second@elektricarentals.com';
  PERFORM pg_sleep(0.01);
  UPDATE elektrica.staff_user SET active = false, updated_by = 'test_harness' WHERE id = v_staff_id;
  SELECT updated_at INTO v_updated_after FROM elektrica.staff_user WHERE id = v_staff_id;

  IF v_updated_after <= v_updated_before THEN
    RAISE EXCEPTION 'CHECK 6 FAILED: updated_at did not advance on UPDATE';
  END IF;
  RAISE NOTICE 'CHECK 6 PASSED: updated_at trigger fired correctly';
END $$;

SELECT 'ALL CHECKS COMPLETED' AS summary;
