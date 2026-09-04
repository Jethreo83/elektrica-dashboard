"""
Elektrica Rentals Dashboard -- FastAPI application entrypoint.

Phase 1 scope (per Jed's approved instruction): local-only, single-user,
SQLite-backed CRUD API for Vehicle/Customer/Lease/Payment/Incident/
ComplianceItem, plus a lightweight home/summary endpoint. No auth in
Phase 1 (single-user local tool) -- flagged as an open question in LOG.md
for whenever this needs to run anywhere Jed isn't the only person with
filesystem access to it.

Run locally (never exposed externally without explicit approval):
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8420
"""
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import ComplianceItem, ComplianceStatus, Incident, IncidentStatus, Lease, LeaseStatus, Payment, PaymentStatus, Vehicle, VehicleStatus
from app.routers import compliance_items, customers, incidents, leases, payments, vehicles


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Elektrica Rentals Dashboard API",
    description=(
        "Phase 1 local CRUD API for fleet/lease/payment/incident/compliance "
        "tracking. Local-only; not exposed externally."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(vehicles.router)
app.include_router(customers.router)
app.include_router(leases.router)
app.include_router(payments.router)
app.include_router(incidents.router)
app.include_router(compliance_items.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/summary")
def summary(db: Session = Depends(get_db)):
    """
    At-a-glance home view per workspace/PLAN.md section 2 ("Reporting / home
    view"): fleet count & status, leases expiring soon, payments overdue,
    open incidents, upcoming compliance deadlines.

    "Soon" windows are a Phase 1 default (30 days) -- flagged as an open
    question in LOG.md in case Jed wants this configurable per item type.
    """
    soon_cutoff = date.today() + timedelta(days=30)
    today = date.today()

    vehicle_counts = {}
    for status in VehicleStatus:
        vehicle_counts[status.value] = (
            db.query(Vehicle).filter(Vehicle.status == status).count()
        )

    leases_expiring_soon = (
        db.query(Lease)
        .filter(
            Lease.status == LeaseStatus.ACTIVE,
            Lease.end_date.isnot(None),
            Lease.end_date <= soon_cutoff,
        )
        .count()
    )

    payments_overdue = (
        db.query(Payment)
        .filter(
            Payment.status.in_([PaymentStatus.OUTSTANDING, PaymentStatus.LATE]),
            Payment.due_date < today,
        )
        .count()
    )

    open_incidents = (
        db.query(Incident)
        .filter(Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.IN_NEGOTIATION]))
        .count()
    )

    compliance_expiring_soon = (
        db.query(ComplianceItem)
        .filter(
            ComplianceItem.expiration_date.isnot(None),
            ComplianceItem.expiration_date <= soon_cutoff,
            ComplianceItem.status != ComplianceStatus.EXPIRED,
        )
        .count()
    )

    return {
        "fleet": {
            "total": sum(vehicle_counts.values()),
            "by_status": vehicle_counts,
        },
        "leases_expiring_within_30d": leases_expiring_soon,
        "payments_overdue": payments_overdue,
        "open_incidents": open_incidents,
        "compliance_items_expiring_within_30d": compliance_expiring_soon,
    }
