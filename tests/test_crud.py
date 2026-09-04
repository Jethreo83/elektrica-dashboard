"""End-to-end CRUD tests for each Phase 1 entity, run against an isolated
in-memory SQLite DB via the fixtures in conftest.py."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_vehicle_crud(client):
    payload = {
        "vin": "5YJ3E1EA1KF000001",
        "make": "Tesla",
        "model": "Model 3",
        "year": 2023,
        "status": "available",
        "title_status": "clean",
    }
    r = client.post("/vehicles/", json=payload)
    assert r.status_code == 201, r.text
    vehicle = r.json()
    assert vehicle["vin"] == payload["vin"]
    vid = vehicle["id"]

    # duplicate VIN rejected
    r = client.post("/vehicles/", json=payload)
    assert r.status_code == 409

    r = client.get(f"/vehicles/{vid}")
    assert r.status_code == 200
    assert r.json()["make"] == "Tesla"

    r = client.get("/vehicles/")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.patch(f"/vehicles/{vid}", json={"status": "leased", "odometer": 1200})
    assert r.status_code == 200
    assert r.json()["status"] == "leased"
    assert r.json()["odometer"] == 1200

    r = client.delete(f"/vehicles/{vid}")
    assert r.status_code == 204

    r = client.get(f"/vehicles/{vid}")
    assert r.status_code == 404


def test_vehicle_delete_blocked_by_dependent_lease(client):
    """
    Regression test for a real bug caught during Phase 1 manual testing:
    deleting a Vehicle/Customer/Lease with dependent rows (NOT NULL FK)
    used to raise an unhandled sqlite3.IntegrityError -> bare 500. Now it
    should return a clean 409 with an explanatory message.
    """
    vid = _make_vehicle(client, vin="5YJ3E1EA1KF0000AA")
    cid = _make_customer(client, name="Dependent Test Customer")
    r = client.post(
        "/leases/",
        json={
            "vehicle_id": vid,
            "customer_id": cid,
            "start_date": "2026-01-01",
            "monthly_rate": "500.00",
        },
    )
    assert r.status_code == 201, r.text

    r = client.delete(f"/vehicles/{vid}")
    assert r.status_code == 409
    assert "lease" in r.json()["detail"].lower()

    r = client.delete(f"/customers/{cid}")
    assert r.status_code == 409
    assert "lease" in r.json()["detail"].lower()


def test_customer_crud(client):
    payload = {"name": "Jane Doe", "contact_email": "jane@example.com", "type": "lessee"}
    r = client.post("/customers/", json=payload)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r = client.get(f"/customers/{cid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Jane Doe"

    r = client.patch(f"/customers/{cid}", json={"contact_phone": "555-1234"})
    assert r.status_code == 200
    assert r.json()["contact_phone"] == "555-1234"

    r = client.delete(f"/customers/{cid}")
    assert r.status_code == 204


def _make_vehicle(client, vin="5YJ3E1EA1KF000002"):
    r = client.post(
        "/vehicles/",
        json={"vin": vin, "make": "Tesla", "model": "Model 3", "year": 2023},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _make_customer(client, name="John Smith"):
    r = client.post("/customers/", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_lease_requires_valid_fks(client):
    r = client.post(
        "/leases/",
        json={
            "vehicle_id": 999,
            "customer_id": 999,
            "start_date": "2026-01-01",
            "monthly_rate": "500.00",
        },
    )
    assert r.status_code == 422


def test_lease_crud(client):
    vid = _make_vehicle(client)
    cid = _make_customer(client)

    r = client.post(
        "/leases/",
        json={
            "vehicle_id": vid,
            "customer_id": cid,
            "type": "primary_lease",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "monthly_rate": "650.00",
            "deposit_amount": "500.00",
        },
    )
    assert r.status_code == 201, r.text
    lease = r.json()
    lid = lease["id"]
    assert lease["status"] == "active"

    r = client.get(f"/leases/{lid}")
    assert r.status_code == 200

    r = client.patch(f"/leases/{lid}", json={"status": "terminated"})
    assert r.status_code == 200
    assert r.json()["status"] == "terminated"


def test_payment_crud(client):
    vid = _make_vehicle(client)
    cid = _make_customer(client)
    r = client.post(
        "/leases/",
        json={
            "vehicle_id": vid,
            "customer_id": cid,
            "start_date": "2026-01-01",
            "monthly_rate": "650.00",
        },
    )
    lid = r.json()["id"]

    r = client.post(
        "/payments/",
        json={
            "lease_id": lid,
            "due_date": "2026-02-01",
            "amount_due": "650.00",
            "status": "outstanding",
        },
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r = client.patch(
        f"/payments/{pid}",
        json={"amount_paid": "650.00", "paid_date": "2026-02-01", "status": "paid"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "paid"

    r = client.post("/payments/", json={"lease_id": 999, "due_date": "2026-02-01", "amount_due": "1.00"})
    assert r.status_code == 422


def test_lease_delete_blocked_by_dependent_payment(client):
    vid = _make_vehicle(client, vin="5YJ3E1EA1KF0000BB")
    cid = _make_customer(client, name="Payment Dependent Customer")
    r = client.post(
        "/leases/",
        json={"vehicle_id": vid, "customer_id": cid, "start_date": "2026-01-01", "monthly_rate": "650.00"},
    )
    lid = r.json()["id"]
    r = client.post(
        "/payments/", json={"lease_id": lid, "due_date": "2026-02-01", "amount_due": "650.00"}
    )
    assert r.status_code == 201

    r = client.delete(f"/leases/{lid}")
    assert r.status_code == 409
    assert "payment" in r.json()["detail"].lower()


def test_incident_crud(client):
    vid = _make_vehicle(client)
    cid = _make_customer(client)

    r = client.post(
        "/incidents/",
        json={
            "vehicle_id": vid,
            "customer_id": cid,
            "date": "2026-03-01",
            "description": "Rear-ended at a stoplight.",
            "at_fault": "other",
            "counterparty_name": "State Farm insured",
        },
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]

    r = client.patch(f"/incidents/{iid}", json={"status": "in_negotiation"})
    assert r.status_code == 200
    assert r.json()["status"] == "in_negotiation"


def test_compliance_item_crud(client):
    r = client.post(
        "/compliance-items/",
        json={
            "type": "dealer_license",
            "description": "Texas Dealer Pre-License",
            "expiration_date": "2027-01-01",
            "status": "current",
        },
    )
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]

    r = client.patch(f"/compliance-items/{item_id}", json={"status": "expiring_soon"})
    assert r.status_code == 200
    assert r.json()["status"] == "expiring_soon"

    r = client.delete(f"/compliance-items/{item_id}")
    assert r.status_code == 204


def test_summary_endpoint(client):
    vid = _make_vehicle(client)
    cid = _make_customer(client)
    client.post(
        "/leases/",
        json={
            "vehicle_id": vid,
            "customer_id": cid,
            "start_date": "2026-01-01",
            "end_date": "2026-01-15",  # expires "soon" relative to a fixed test date far in the past/future is not guaranteed, so just check shape
            "monthly_rate": "650.00",
        },
    )
    r = client.get("/summary")
    assert r.status_code == 200
    body = r.json()
    assert "fleet" in body
    assert "by_status" in body["fleet"]
    assert body["fleet"]["total"] == 1
    assert "leases_expiring_within_30d" in body
    assert "payments_overdue" in body
    assert "open_incidents" in body
    assert "compliance_items_expiring_within_30d" in body
