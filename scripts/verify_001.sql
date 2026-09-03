-- Verification harness for migration 001 (elektrica.renter + RLS) — same
-- discipline as VLS verify_004.sql. Verify by actually switching role and
-- querying, not by reading the policy definition.

DO $$
DECLARE
  v_person_renter_id BIGINT;    -- has an elektrica.renter row -> visible to elektrica_app
  v_person_no_renter_id BIGINT; -- no elektrica.renter row -> invisible to elektrica_app
BEGIN
  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'RenterPerson', 'test.renter@example.com', 'test_harness')
  RETURNING id INTO v_person_renter_id;

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'NonRenterPerson', 'test.nonrenter@example.com', 'test_harness')
  RETURNING id INTO v_person_no_renter_id;

  INSERT INTO elektrica.renter (person_id, jotform_submission_ref, created_by)
  VALUES (v_person_renter_id, 'jotform_test_001', 'test_harness');

  RAISE NOTICE 'person_renter_id=% person_no_renter_id=%', v_person_renter_id, v_person_no_renter_id;
END $$;

-- CHECK 1: as table owner (FORCE RLS on platform.person set in VLS migration
-- 004 applies even to the owner unless it owns the table). Confirms both
-- person rows exist from the privileged connection.
SELECT id, first_name, last_name FROM platform.person WHERE last_name IN ('RenterPerson', 'NonRenterPerson') ORDER BY id;
-- EXPECT: 2 rows

-- CHECK 2: as elektrica_app, should see ONLY the person with an
-- elektrica.renter row.
SET ROLE elektrica_app;
SELECT id, first_name, last_name FROM platform.person WHERE last_name IN ('RenterPerson', 'NonRenterPerson') ORDER BY id;
-- EXPECT: 1 row — RenterPerson only. NonRenterPerson must be ABSENT, not
-- flagged, not null-masked — genuinely absent from the result set.
RESET ROLE;

-- CHECK 3: elektrica_app cannot INSERT into platform.person directly (must
-- go through the identity service, same rule as vls_app).
SET ROLE elektrica_app;
DO $$
BEGIN
  INSERT INTO platform.person (first_name, last_name, created_by)
  VALUES ('Should', 'Fail', 'elektrica_app');
  RAISE EXCEPTION 'CHECK 3 FAILED: elektrica_app should not be able to INSERT into platform.person';
EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'CHECK 3 PASSED: elektrica_app blocked from INSERT on platform.person';
END $$;
RESET ROLE;

-- CHECK 4: platform_identity_service (created in VLS migration 004) sees
-- everything, including Elektrica's renters — confirms the shared identity
-- service role's bypass policy is not scoped to VLS only.
SET ROLE platform_identity_service;
SELECT id, first_name, last_name FROM platform.person WHERE last_name IN ('RenterPerson', 'NonRenterPerson') ORDER BY id;
-- EXPECT: 2 rows
RESET ROLE;

-- CHECK 5: elektrica_app CAN read/write elektrica.renter — RLS is scoped to
-- platform.person only, not elektrica's own schema.
SET ROLE elektrica_app;
SELECT person_id, jotform_submission_ref FROM elektrica.renter WHERE jotform_submission_ref = 'jotform_test_001';
-- EXPECT: 1 row
RESET ROLE;

-- CHECK 6: elektrica.renter enforces one row per person.
DO $$
BEGIN
  INSERT INTO elektrica.renter (person_id, created_by)
  SELECT id, 'test_harness' FROM platform.person WHERE last_name = 'RenterPerson';
  RAISE EXCEPTION 'CHECK 6 FAILED: duplicate renter row for same person_id should have been rejected';
EXCEPTION WHEN unique_violation THEN
  RAISE NOTICE 'CHECK 6 PASSED: renter_one_row_per_person constraint enforced';
END $$;

SELECT 'ALL CHECKS COMPLETED — CHECK 2 must show exactly 1 row (RenterPerson)' AS summary;
