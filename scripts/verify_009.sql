-- Verification harness for migration 009 (document generator relocated
-- from elektrica.* to platform.*, correcting drift against
-- docs/SHARED_CONVENTIONS.md convention #2).

-- CHECK 1: tables/types actually moved — confirm elektrica no longer has
-- them, platform does.
SELECT count(*) AS n_in_elektrica FROM pg_tables WHERE schemaname = 'elektrica' AND tablename IN ('document', 'document_template', 'outbound_log');
-- EXPECT: n_in_elektrica = 0

SELECT count(*) AS n_in_platform FROM pg_tables WHERE schemaname = 'platform' AND tablename IN ('document', 'document_template', 'outbound_log');
-- EXPECT: n_in_platform = 3

-- CHECK 2: the pre-existing FK from elektrica.demand.generated_document_id
-- to document(id) survived the schema move — same OID, new schema. Insert
-- a full chain and confirm it resolves.
DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_rental_id BIGINT;
  v_template_id BIGINT;
  v_document_id BIGINT;
  v_demand_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, class, status, created_by, updated_by)
  VALUES ('TESTVIN0000000099009', 'ev', 'available', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'PlatformDocRenter', 'test.platformdocrenter@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.renter (person_id, created_by)
  VALUES (v_person_id, 'test_harness')
  RETURNING id INTO v_renter_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  VALUES (v_vehicle_id, v_renter_id, 'carrier', 'test_harness', 'test_harness')
  RETURNING id INTO v_rental_id;

  INSERT INTO platform.document_template (family, version, template_ref, created_by)
  VALUES ('rental_demand', 99, 'gdoc:test-platform-migration', 'test_harness')
  RETURNING id INTO v_template_id;

  INSERT INTO platform.document
    (template_id, source_table, source_id, merge_data, output_ref, output_hash, generated_by)
  VALUES
    (v_template_id, 'elektrica.rental', v_rental_id, '{}'::jsonb,
     'drive:test-platform-migration-doc', 'sha256:testhash009', 'test_harness')
  RETURNING id INTO v_document_id;

  INSERT INTO elektrica.demand
    (rental_id, demand_type, recipient_type, carrier_name, amount, generated_document_id, created_by, updated_by)
  VALUES
    (v_rental_id, 'primary_insurer', 'carrier', 'Platform Migration Test Co', 100.00,
     v_document_id, 'test_harness', 'test_harness')
  RETURNING id INTO v_demand_id;

  RAISE NOTICE 'CHECK 2 PASSED: demand % -> document % -> template % chain intact across the schema move', v_demand_id, v_document_id, v_template_id;
END $$;

SELECT d.id, dt.family, dt.version
FROM elektrica.demand d
JOIN platform.document doc ON doc.id = d.generated_document_id
JOIN platform.document_template dt ON dt.id = doc.template_id
WHERE d.carrier_name = 'Platform Migration Test Co';
-- EXPECT: 1 row, family=rental_demand, version=99

-- CHECK 3: platform.documents_never_sent view works against the new location.
SELECT document_id FROM platform.documents_never_sent
WHERE document_id = (SELECT id FROM platform.document WHERE output_ref = 'drive:test-platform-migration-doc');
-- EXPECT: 1 row

-- CHECK 4: elektrica_app can still read/write the relocated tables (grants
-- survived/were re-issued correctly).
SET ROLE elektrica_app;
SELECT template_ref FROM platform.document_template WHERE version = 99;
INSERT INTO platform.document
  (template_id, source_table, source_id, merge_data, output_ref, output_hash, generated_by)
SELECT id, 'elektrica.rental', 1, '{}'::jsonb, 'drive:elektrica-app-write-test', 'sha256:elektricaapptest', 'elektrica_app'
FROM platform.document_template WHERE version = 99;
RESET ROLE;
-- EXPECT: no errors; SELECT returns 1 row, INSERT succeeds

SELECT count(*) AS n FROM platform.document WHERE output_ref = 'drive:elektrica-app-write-test';
-- EXPECT: n = 1

-- CHECK 5: append-only enforcement on platform.document survived the move
-- (the trigger functions were defined in the elektrica schema but attached
-- to the table object itself, which retains its triggers across a schema
-- move).
DO $$
DECLARE
  v_document_id BIGINT;
BEGIN
  SELECT id INTO v_document_id FROM platform.document WHERE output_ref = 'drive:test-platform-migration-doc';
  BEGIN
    DELETE FROM platform.document WHERE id = v_document_id;
    RAISE EXCEPTION 'CHECK 5 FAILED: DELETE on platform.document should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only generation log%' THEN
      RAISE NOTICE 'CHECK 5 PASSED: append-only trigger survived the schema move (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

SELECT 'ALL CHECKS COMPLETED' AS summary;
