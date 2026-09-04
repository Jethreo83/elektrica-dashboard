-- Verification harness for migration 006 (elektrica.demand + comparable_set).

DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_rental_id BIGINT;
  v_template_id BIGINT;
  v_document_id BIGINT;
  v_demand_id BIGINT;
  v_comparable_set_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, class, status, created_by, updated_by)
  VALUES ('TESTVIN0000000033', 'ev', 'available', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'DemandRenter', 'test.demandrenter@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.renter (person_id, created_by)
  VALUES (v_person_id, 'test_harness')
  RETURNING id INTO v_renter_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  VALUES (v_vehicle_id, v_renter_id, 'carrier', 'test_harness', 'test_harness')
  RETURNING id INTO v_rental_id;

  -- reuse an existing template row if migration 005's verify already ran in
  -- this session, else create one
  SELECT id INTO v_template_id FROM elektrica.document_template WHERE family = 'rental_demand' AND version = 1;
  IF v_template_id IS NULL THEN
    INSERT INTO elektrica.document_template (family, version, template_ref, created_by)
    VALUES ('rental_demand', 1, 'gdoc:test-template-v1', 'test_harness')
    RETURNING id INTO v_template_id;
  END IF;

  INSERT INTO elektrica.document
    (template_id, source_table, source_id, merge_data, output_ref, output_hash, generated_by)
  VALUES
    (v_template_id, 'elektrica.rental', v_rental_id, '{}'::jsonb,
     'drive:test-demand-doc-006', 'sha256:testhash006', 'test_harness')
  RETURNING id INTO v_document_id;

  INSERT INTO elektrica.demand
    (rental_id, demand_type, recipient_type, carrier_name, amount,
     generated_document_id, created_by, updated_by)
  VALUES
    (v_rental_id, 'primary_insurer', 'carrier', 'Test Insurance Co', 450.00,
     v_document_id, 'test_harness', 'test_harness')
  RETURNING id INTO v_demand_id;

  INSERT INTO elektrica.comparable_set
    (demand_id, scan_source, scan_timestamp, vehicle_class, date_range_start, date_range_end,
     comparables, computed_average, created_by)
  VALUES
    (v_demand_id, 'kayak', now(), 'ev', CURRENT_DATE - 7, CURRENT_DATE,
     '[{"vendor": "Hertz", "vehicle": "Tesla Model 3", "daily_rate": 65.00},
       {"vendor": "Enterprise", "vehicle": "Tesla Model 3", "daily_rate": 70.00}]'::jsonb,
     67.50, 'test_harness')
  RETURNING id INTO v_comparable_set_id;

  RAISE NOTICE 'rental_id=% demand_id=% comparable_set_id=%', v_rental_id, v_demand_id, v_comparable_set_id;
END $$;

-- CHECK 1: demand created with default status 'draft'.
SELECT demand_type, recipient_type, carrier_name, status, amount
FROM elektrica.demand WHERE carrier_name = 'Test Insurance Co';
-- EXPECT: 1 row, status=draft, amount=450.00

-- CHECK 2: carrier_name required when recipient_type='carrier'.
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000033';
  BEGIN
    INSERT INTO elektrica.demand (rental_id, demand_type, recipient_type, amount, created_by, updated_by)
    VALUES (v_rental_id, 'primary_insurer', 'carrier', 100.00, 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 2 FAILED: missing carrier_name should have been rejected';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'CHECK 2 PASSED: demand_carrier_name_required_for_carrier_recipient enforced';
  END;
END $$;

-- CHECK 3: draft demand cannot carry sent_via/sent_at.
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000033';
  BEGIN
    INSERT INTO elektrica.demand
      (rental_id, demand_type, recipient_type, carrier_name, amount, sent_via, sent_at, created_by, updated_by)
    VALUES (v_rental_id, 'primary_insurer', 'carrier', 'X', 100.00, 'fax', now(), 'test_harness', 'test_harness');
    RAISE EXCEPTION 'CHECK 3 FAILED: draft with sent_via/sent_at should have been rejected';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'CHECK 3 PASSED: demand_draft_has_no_send_record enforced';
  END;
END $$;

-- CHECK 4: comparable_set created, computed_average and comparables intact.
SELECT scan_source, vehicle_class, computed_average, jsonb_array_length(comparables) AS n_comparables
FROM elektrica.comparable_set WHERE scan_source = 'kayak';
-- EXPECT: 1 row, computed_average=67.50, n_comparables=2

-- CHECK 5: comparable_set is frozen — UPDATE rejected.
DO $$
DECLARE
  v_id BIGINT;
BEGIN
  SELECT id INTO v_id FROM elektrica.comparable_set WHERE scan_source = 'kayak';
  BEGIN
    UPDATE elektrica.comparable_set SET computed_average = 999.00 WHERE id = v_id;
    RAISE EXCEPTION 'CHECK 5 FAILED: UPDATE on comparable_set should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%frozen once created%' THEN
      RAISE NOTICE 'CHECK 5 PASSED: comparable_set UPDATE blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 6: comparable_set is frozen — DELETE rejected.
DO $$
DECLARE
  v_id BIGINT;
BEGIN
  SELECT id INTO v_id FROM elektrica.comparable_set WHERE scan_source = 'kayak';
  BEGIN
    DELETE FROM elektrica.comparable_set WHERE id = v_id;
    RAISE EXCEPTION 'CHECK 6 FAILED: DELETE on comparable_set should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%frozen once created%' THEN
      RAISE NOTICE 'CHECK 6 PASSED: comparable_set DELETE blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 7: prior_demand_id chain — a second demand can reference the first
-- as its predecessor (shortfall pre-fill linkage).
DO $$
DECLARE
  v_rental_id BIGINT;
  v_first_demand_id BIGINT;
  v_second_demand_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r
    JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000033';
  SELECT id INTO v_first_demand_id FROM elektrica.demand WHERE carrier_name = 'Test Insurance Co';

  INSERT INTO elektrica.demand
    (rental_id, demand_type, recipient_type, carrier_name, amount, prior_demand_id, created_by, updated_by)
  VALUES (v_rental_id, 'uim', 'carrier', 'Test UIM Carrier', 150.00, v_first_demand_id, 'test_harness', 'test_harness')
  RETURNING id INTO v_second_demand_id;

  RAISE NOTICE 'CHECK 7 PASSED: second demand % chains to prior demand %', v_second_demand_id, v_first_demand_id;
END $$;

-- CHECK 8: self-reference rejected.
DO $$
DECLARE
  v_demand_id BIGINT;
BEGIN
  SELECT id INTO v_demand_id FROM elektrica.demand WHERE carrier_name = 'Test Insurance Co';
  BEGIN
    UPDATE elektrica.demand SET prior_demand_id = v_demand_id WHERE id = v_demand_id;
    RAISE EXCEPTION 'CHECK 8 FAILED: self-referencing prior_demand_id should have been rejected';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'CHECK 8 PASSED: demand_prior_not_self enforced';
  END;
END $$;

-- CHECK 9: aging_demands view is empty for a fresh draft demand (not sent yet).
SELECT count(*) AS n_aging FROM elektrica.aging_demands
WHERE rental_id = (SELECT r.id FROM elektrica.rental r JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000033');
-- EXPECT: n_aging = 0 (nothing sent yet)

SELECT 'ALL CHECKS COMPLETED' AS summary;
