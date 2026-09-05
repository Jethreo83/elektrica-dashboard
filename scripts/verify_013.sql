-- Verification harness for migration 013 (platform.insurance_carrier +
-- platform.adjuster). Verifies by direct query against live staging
-- data, not exit codes.

DO $$
DECLARE
  v_carrier_id BIGINT;
  v_adjuster_id BIGINT;
BEGIN
  INSERT INTO platform.insurance_carrier
    (name, aliases, fax, email, phone, claims_mailing_address, created_by, updated_by)
  VALUES
    ('State Farm Mutual Automobile Insurance Company',
     ARRAY['State Farm', 'SF'],
     '555-100-2000', 'claims@statefarm.example.com', '555-100-1000',
     'PO Box 1 Bloomington IL', 'test_harness', 'test_harness')
  RETURNING id INTO v_carrier_id;

  INSERT INTO platform.adjuster (carrier_id, name, phone, email, created_by, updated_by)
  VALUES (v_carrier_id, 'Jane Adjuster', '555-100-3000', 'jane.adjuster@statefarm.example.com',
          'test_harness', 'test_harness')
  RETURNING id INTO v_adjuster_id;

  RAISE NOTICE 'carrier_id=% adjuster_id=%', v_carrier_id, v_adjuster_id;
END $$;

-- CHECK 1: carrier + adjuster inserted, aliases round-trip as an array.
SELECT c.name, c.aliases, a.name AS adjuster_name
FROM platform.insurance_carrier c
JOIN platform.adjuster a ON a.carrier_id = c.id
WHERE c.name = 'State Farm Mutual Automobile Insurance Company';
-- EXPECT: 1 row, aliases={State Farm,SF}, adjuster_name='Jane Adjuster'

-- CHECK 2: duplicate canonical carrier name rejected (the "collapse to
-- canonical record" mechanism -- handoff §2.9.2).
DO $$
BEGIN
  BEGIN
    INSERT INTO platform.insurance_carrier (name, created_by, updated_by)
    VALUES ('State Farm Mutual Automobile Insurance Company', 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 2 FAILED: duplicate carrier name should have been rejected';
  EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE 'CHECK 2 PASSED: insurance_carrier_name_unique enforced';
  END;
END $$;

-- CHECK 3: adjuster requires a real carrier_id (FK enforced).
DO $$
BEGIN
  BEGIN
    INSERT INTO platform.adjuster (carrier_id, name, created_by, updated_by)
    VALUES (999999999, 'Nobody', 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 3 FAILED: bad carrier_id should have been rejected';
  EXCEPTION WHEN foreign_key_violation THEN
    RAISE NOTICE 'CHECK 3 PASSED: adjuster.carrier_id FK enforced';
  END;
END $$;

-- CHECK 4: same adjuster name allowed at a DIFFERENT carrier (people
-- move employers -- not a duplicate across carriers).
DO $$
DECLARE
  v_carrier2_id BIGINT;
BEGIN
  INSERT INTO platform.insurance_carrier (name, created_by, updated_by)
  VALUES ('Allstate Insurance Company', 'test_harness', 'test_harness')
  RETURNING id INTO v_carrier2_id;

  INSERT INTO platform.adjuster (carrier_id, name, created_by, updated_by)
  VALUES (v_carrier2_id, 'Jane Adjuster', 'test_harness', 'test_harness');
END $$;

SELECT count(*) AS jane_adjuster_rows_across_carriers
FROM platform.adjuster WHERE name = 'Jane Adjuster';
-- EXPECT: 2 (one per carrier)

-- CHECK 5: duplicate adjuster name AT THE SAME carrier rejected.
DO $$
DECLARE
  v_carrier_id BIGINT;
BEGIN
  SELECT id INTO v_carrier_id FROM platform.insurance_carrier
  WHERE name = 'State Farm Mutual Automobile Insurance Company';

  BEGIN
    INSERT INTO platform.adjuster (carrier_id, name, created_by, updated_by)
    VALUES (v_carrier_id, 'Jane Adjuster', 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 5 FAILED: duplicate adjuster-at-same-carrier should have been rejected';
  EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE 'CHECK 5 PASSED: adjuster_name_unique_per_carrier enforced';
  END;
END $$;

-- CHECK 6: updated_at trigger fires on UPDATE. NOTE: this check's DO
-- block must be its own top-level statement (which it already is,
-- separated by the semicolons above) -- if a harness ever collapses this
-- whole file into one single multi-statement .execute() call under one
-- implicit transaction, now() is fixed at transaction start and this
-- check will falsely report FAILED even though the trigger is correct.
-- Run statement-by-statement (psql's own default behavior, or an
-- equivalent split in whatever runner replaces it) to avoid that trap.
DO $$
DECLARE
  v_carrier_id BIGINT;
  v_before TIMESTAMPTZ;
  v_after TIMESTAMPTZ;
BEGIN
  SELECT id, updated_at INTO v_carrier_id, v_before FROM platform.insurance_carrier
  WHERE name = 'State Farm Mutual Automobile Insurance Company';

  PERFORM pg_sleep(0.05);

  UPDATE platform.insurance_carrier SET fax = '555-999-9999', updated_by = 'test_harness'
  WHERE id = v_carrier_id;

  SELECT updated_at INTO v_after FROM platform.insurance_carrier WHERE id = v_carrier_id;

  IF v_after > v_before THEN
    RAISE NOTICE 'CHECK 6 PASSED: updated_at advanced on UPDATE';
  ELSE
    RAISE EXCEPTION 'CHECK 6 FAILED: updated_at did not advance';
  END IF;
END $$;

-- CHECK 7: elektrica_app has the expected grants (SELECT/INSERT/UPDATE,
-- no DELETE) on both tables.
SELECT
  'platform.insurance_carrier' AS table_name,
  has_table_privilege('elektrica_app', 'platform.insurance_carrier', 'SELECT') AS can_select,
  has_table_privilege('elektrica_app', 'platform.insurance_carrier', 'INSERT') AS can_insert,
  has_table_privilege('elektrica_app', 'platform.insurance_carrier', 'UPDATE') AS can_update,
  has_table_privilege('elektrica_app', 'platform.insurance_carrier', 'DELETE') AS can_delete
UNION ALL
SELECT
  'platform.adjuster',
  has_table_privilege('elektrica_app', 'platform.adjuster', 'SELECT'),
  has_table_privilege('elektrica_app', 'platform.adjuster', 'INSERT'),
  has_table_privilege('elektrica_app', 'platform.adjuster', 'UPDATE'),
  has_table_privilege('elektrica_app', 'platform.adjuster', 'DELETE');
-- EXPECT: both rows can_select=t, can_insert=t, can_update=t, can_delete=f

SELECT 'ALL CHECKS COMPLETED' AS summary;
