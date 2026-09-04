-- Verification harness for migration 008 (payment, toll, compliance_item).

DO $$
DECLARE
  v_vehicle_id BIGINT;
  v_person_id BIGINT;
  v_renter_id BIGINT;
  v_rental_id BIGINT;
BEGIN
  INSERT INTO elektrica.vehicle (vin, class, status, created_by, updated_by)
  VALUES ('TESTVIN0000000088', 'ev', 'available', 'test_harness', 'test_harness')
  RETURNING id INTO v_vehicle_id;

  INSERT INTO platform.person (first_name, last_name, email_normalized, created_by)
  VALUES ('Test', 'PaymentRenter', 'test.paymentrenter@example.com', 'test_harness')
  RETURNING id INTO v_person_id;

  INSERT INTO elektrica.renter (person_id, created_by)
  VALUES (v_person_id, 'test_harness')
  RETURNING id INTO v_renter_id;

  INSERT INTO elektrica.rental (vehicle_id, renter_id, billed_to, created_by, updated_by)
  VALUES (v_vehicle_id, v_renter_id, 'self', 'test_harness', 'test_harness')
  RETURNING id INTO v_rental_id;

  INSERT INTO elektrica.payment (rental_id, source, amount, created_by)
  VALUES (v_rental_id, 'manual', 250.00, 'test_harness');

  INSERT INTO elektrica.toll (rental_id, tolloptics_record_id, amount, toll_date, created_by)
  VALUES (v_rental_id, 'tolloptics-test-001', 5.75, CURRENT_DATE - 3, 'test_harness');

  RAISE NOTICE 'vehicle_id=% rental_id=%', v_vehicle_id, v_rental_id;
END $$;

-- CHECK 1: payment created correctly.
SELECT source, amount FROM elektrica.payment
WHERE rental_id = (SELECT r.id FROM elektrica.rental r JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000088');
-- EXPECT: 1 row, source=manual, amount=250.00

-- CHECK 2: authorize_net payments require external_transaction_id.
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000088';
  BEGIN
    INSERT INTO elektrica.payment (rental_id, source, amount, created_by)
    VALUES (v_rental_id, 'authorize_net', 100.00, 'test_harness');
    RAISE EXCEPTION 'CHECK 2 FAILED: authorize_net without external_transaction_id should have been rejected';
  EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'CHECK 2 PASSED: payment_external_txn_id_required_for_authorize_net enforced';
  END;
END $$;

-- CHECK 3: payment is append-only (UPDATE + DELETE both blocked).
DO $$
DECLARE
  v_payment_id BIGINT;
BEGIN
  SELECT id INTO v_payment_id FROM elektrica.payment WHERE amount = 250.00;
  BEGIN
    UPDATE elektrica.payment SET amount = 999.00 WHERE id = v_payment_id;
    RAISE EXCEPTION 'CHECK 3a FAILED: UPDATE on payment should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only financial record%' THEN
      RAISE NOTICE 'CHECK 3a PASSED: payment UPDATE blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
  BEGIN
    DELETE FROM elektrica.payment WHERE id = v_payment_id;
    RAISE EXCEPTION 'CHECK 3b FAILED: DELETE on payment should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%append-only financial record%' THEN
      RAISE NOTICE 'CHECK 3b PASSED: payment DELETE blocked (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

-- CHECK 4: toll uniqueness on tolloptics_record_id enforced.
DO $$
DECLARE
  v_rental_id BIGINT;
BEGIN
  SELECT r.id INTO v_rental_id FROM elektrica.rental r JOIN elektrica.vehicle v ON v.id = r.vehicle_id WHERE v.vin = 'TESTVIN0000000088';
  BEGIN
    INSERT INTO elektrica.toll (rental_id, tolloptics_record_id, amount, toll_date, created_by)
    VALUES (v_rental_id, 'tolloptics-test-001', 9.99, CURRENT_DATE, 'test_harness');
    RAISE EXCEPTION 'CHECK 4 FAILED: duplicate tolloptics_record_id should have been rejected';
  EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE 'CHECK 4 PASSED: toll_one_row_per_tolloptics_record enforced';
  END;
END $$;

-- CHECK 5: toll's confirmed flag can be flipped, other fields cannot.
DO $$
DECLARE
  v_toll_id BIGINT;
BEGIN
  SELECT id INTO v_toll_id FROM elektrica.toll WHERE tolloptics_record_id = 'tolloptics-test-001';
  UPDATE elektrica.toll SET confirmed = true WHERE id = v_toll_id;

  BEGIN
    UPDATE elektrica.toll SET amount = 999.00 WHERE id = v_toll_id;
    RAISE EXCEPTION 'CHECK 5 FAILED: editing toll.amount should have been rejected';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%immutable except its confirmed flag%' THEN
      RAISE NOTICE 'CHECK 5 PASSED: confirmed flippable, other fields immutable (%)', SQLERRM;
    ELSE
      RAISE;
    END IF;
  END;
END $$;

SELECT confirmed FROM elektrica.toll WHERE tolloptics_record_id = 'tolloptics-test-001';
-- EXPECT: 1 row, confirmed = true

-- CHECK 6: compliance_item created, expiring-soon view picks it up.
DO $$
DECLARE
  v_vehicle_id BIGINT;
BEGIN
  SELECT id INTO v_vehicle_id FROM elektrica.vehicle WHERE vin = 'TESTVIN0000000088';
  INSERT INTO elektrica.compliance_item (item_type, description, vehicle_id, expiration_date, created_by, updated_by)
  VALUES ('registration', 'Test vehicle registration', v_vehicle_id, CURRENT_DATE + 10, 'test_harness', 'test_harness');

  INSERT INTO elektrica.compliance_item (item_type, description, expiration_date, created_by, updated_by)
  VALUES ('dealer_license', 'Texas Dealer License', CURRENT_DATE + 200, 'test_harness', 'test_harness');
END $$;

SELECT item_type, days_until_expiration FROM elektrica.compliance_items_expiring_soon
WHERE description = 'Test vehicle registration';
-- EXPECT: 1 row, item_type=registration, days_until_expiration=10

SELECT count(*) AS n_far_out FROM elektrica.compliance_items_expiring_soon
WHERE description = 'Texas Dealer License';
-- EXPECT: n_far_out = 0 (200 days out, not within the 30-day window)

-- CHECK 7: vehicle_revenue_summary reflects the payment recorded above.
SELECT vin, vehicle_status, total_revenue, total_rentals
FROM elektrica.vehicle_revenue_summary WHERE vin = 'TESTVIN0000000088';
-- EXPECT: 1 row, total_revenue=250.00 (the one manual payment; the
-- rejected authorize_net attempt never inserted), total_rentals=1

SELECT 'ALL CHECKS COMPLETED' AS summary;
