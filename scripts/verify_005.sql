-- Verification harness for migration 005 (document generator storage/log).
-- Same discipline: verify by direct query.

DO $$
DECLARE
  v_template_id BIGINT;
  v_vehicle_id BIGINT;
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_rental_id BIGINT;
  v_document_id BIGINT;
BEGIN
  INSERT INTO elektrica.document_template (family, version, template_ref, created_by)
  VALUES ('rental_demand', 1, 'gdoc:test-template-v1', 'test_harness')
  RETURNING id INTO v_template_id;

  INSERT INTO elektrica.vehicle (vin, class, status, created_by, updated_by)
  VALUES ('TESTVIN0000000055', 'ev', 'available', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'DocumentRenter', 'test.documentrenter@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.renter (person_id, created_by)
  VALUES (v_person_id, 'test_harness')
  RETURNING id INTO v_renter_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  VALUES (v_vehicle_id, v_renter_id, 'carrier', 'test_harness', 'test_harness')
  RETURNING id INTO v_rental_id;

  INSERT INTO elektrica.document
    (template_id, source_table, source_id, merge_data, attachments, output_ref, output_hash, generated_by)
  VALUES
    (v_template_id, 'elektrica.rental', v_rental_id,
     '{"renter_name": "Test DocumentRenter", "amount": 450.00}'::jsonb,
     '[{"label": "receipt", "ref": "drive:test-receipt-001"}]'::jsonb,
     'drive:test-demand-001', 'sha256:testhash', 'test_harness')
  RETURNING id INTO v_document_id;

  RAISE NOTICE 'template_id=% rental_id=% document_id=%', v_template_id, v_rental_id, v_document_id;
END $$;

-- CHECK 1: document row created with expected fields.
SELECT source_table, source_id, output_ref, output_hash
FROM elektrica.document WHERE output_ref = 'drive:test-demand-001';
-- EXPECT: 1 row, source_table=elektrica.rental, output_hash=sha256:testhash

-- CHECK 2: template family/version uniqueness enforced.
DO $$
BEGIN
  INSERT INTO elektrica.document_template (family, version, template_ref, created_by)
  VALUES ('rental_demand', 1, 'gdoc:duplicate', 'test_harness');
  RAISE EXCEPTION 'CHECK 2 FAILED: duplicate family+version should have been rejected';
EXCEPTION WHEN unique_violation THEN
  RAISE NOTICE 'CHECK 2 PASSED: document_template_family_version_unique enforced';
END $$;

-- CHECK 3: output_hash required once output_ref is set.
DO $$
DECLARE
  v_template_id BIGINT;
  v_rental_id BIGINT;
BEGIN
  SELECT id INTO v_template_id FROM elektrica.document_template WHERE family = 'rental_demand' AND version = 1;
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000055';

  BEGIN
    INSERT INTO elektrica.document
      (template_id, source_table, source_id, merge_data, output_ref, generated_by)
    VALUES (v_template_id, 'elektrica.rental', v_rental_id, '{}'::jsonb, 'drive:missing-hash', 'test_harness');
    RAISE EXCEPTION 'CHECK 3 FAILED: output_ref without output_hash should have been rejected';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'CHECK 3 PASSED: document_output_hash_required_once_generated enforced';
  END;
END $$;

-- CHECK 4: document is append-only — UPDATE rejected.
DO $$
DECLARE
  v_document_id BIGINT;
BEGIN
  SELECT id INTO v_document_id FROM elektrica.document WHERE output_ref = 'drive:test-demand-001';
  BEGIN
    UPDATE elektrica.document SET output_hash = 'sha256:tampered' WHERE id = v_document_id;
    RAISE EXCEPTION 'CHECK 4 FAILED: UPDATE on document should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only generation log%' THEN
      RAISE NOTICE 'CHECK 4 PASSED: document UPDATE blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 5: document is append-only — DELETE rejected.
DO $$
DECLARE
  v_document_id BIGINT;
BEGIN
  SELECT id INTO v_document_id FROM elektrica.document WHERE output_ref = 'drive:test-demand-001';
  BEGIN
    DELETE FROM elektrica.document WHERE id = v_document_id;
    RAISE EXCEPTION 'CHECK 5 FAILED: DELETE on document should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only generation log%' THEN
      RAISE NOTICE 'CHECK 5 PASSED: document DELETE blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 6: "generated but never sent" visibility — before any outbound_log
-- row, the document should appear in documents_never_sent.
SELECT document_id FROM elektrica.documents_never_sent
WHERE document_id = (SELECT id FROM elektrica.document WHERE output_ref = 'drive:test-demand-001');
-- EXPECT: 1 row

-- CHECK 7: after logging a send, the document disappears from
-- documents_never_sent.
DO $$
DECLARE
  v_document_id BIGINT;
BEGIN
  SELECT id INTO v_document_id FROM elektrica.document WHERE output_ref = 'drive:test-demand-001';
  INSERT INTO elektrica.outbound_log (document_id, channel, recipient, sent_by, delivery_confirmation_ref)
  VALUES (v_document_id, 'fax', '+15125550100', 'test_harness', 'ringcentral:test-conf-001');
END $$;

SELECT document_id FROM elektrica.documents_never_sent
WHERE document_id = (SELECT id FROM elektrica.document WHERE output_ref = 'drive:test-demand-001');
-- EXPECT: 0 rows

-- CHECK 8: outbound_log is append-only too.
DO $$
DECLARE
  v_log_id BIGINT;
BEGIN
  SELECT id INTO v_log_id FROM elektrica.outbound_log WHERE delivery_confirmation_ref = 'ringcentral:test-conf-001';
  BEGIN
    DELETE FROM elektrica.outbound_log WHERE id = v_log_id;
    RAISE EXCEPTION 'CHECK 8 FAILED: DELETE on outbound_log should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only%' THEN
      RAISE NOTICE 'CHECK 8 PASSED: outbound_log DELETE blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

SELECT 'ALL CHECKS COMPLETED' AS summary;
