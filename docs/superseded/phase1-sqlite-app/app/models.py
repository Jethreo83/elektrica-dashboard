"""
SQLAlchemy ORM models for Phase 1 of the Elektrica Rentals dashboard.

Entities per Jed's Phase 1 instruction, matching workspace/PLAN.md's
original data-model draft (section 4): Vehicle, Customer, Lease, Payment,
Incident, ComplianceItem.

Design decisions (see LOG.md for the full rationale trail):
- Integer autoincrement primary keys. This is a deliberate, local choice
  for this SQLite track and is NOT the same convention as the elektrica.*
  Postgres schema (which uses UUIDs keyed to platform.person). The two
  schemas are not meant to be compatible right now -- see database.py's
  module docstring.
- Enums are plain Python str-Enums stored as TEXT columns (SQLite has no
  native enum type). Values are validated at the Pydantic layer on the way
  in; the DB column itself is just TEXT so manual/CSV data entry or direct
  sqlite3 inspection isn't blocked by a strict CHECK constraint in v1.
- Money fields use Numeric via SQLAlchemy (stored as fixed-point) rather
  than Float, to avoid rounding surprises on currency.
- Dates are stored as native Date/DateTime (SQLite stores these as TEXT
  under the hood via SQLAlchemy's adapters).
- `notes` / free-text fields are nullable Text.
- No soft-delete flag in Phase 1 -- deletes are hard deletes. Flagged as an
  open question in LOG.md (Jed may want audit history / soft delete later,
  especially for Incident and Payment records).

Note on the `dt_date` import alias: Incident has a field literally named
`date`. Both Pydantic and Python's own typing.get_type_hints resolve
annotations using the class's own namespace, so a class attribute named
`date` shadows the `datetime.date` type for every annotation in that same
class -- this broke schemas.py's IncidentUpdate at import time (see that
module's docstring for the full story, and LOG.md for when it was caught).
Models.py aliases the same way defensively/for consistency, even though
SQLAlchemy declarative's own annotation resolution did not reproduce the
crash in testing.
"""
from datetime import date as dt_date
from datetime import datetime
import enum

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class VehicleStatus(str, enum.Enum):
    AVAILABLE = "available"
    LEASED = "leased"
    SUBLEASED = "subleased"
    SERVICE = "service"
    SOLD = "sold"


class TitleStatus(str, enum.Enum):
    CLEAN = "clean"
    LIENHOLDER = "lienholder"
    SALVAGE = "salvage"
    PENDING = "pending"


class CustomerType(str, enum.Enum):
    LESSEE = "lessee"
    SUBLESSEE = "sublessee"


class LeaseType(str, enum.Enum):
    PRIMARY_LEASE = "primary_lease"
    SUBLEASE = "sublease"


class LeaseStatus(str, enum.Enum):
    ACTIVE = "active"
    ENDED = "ended"
    TERMINATED = "terminated"


class PaymentStatus(str, enum.Enum):
    PAID = "paid"
    LATE = "late"
    OUTSTANDING = "outstanding"
    WAIVED = "waived"


class AtFault(str, enum.Enum):
    SELF = "self"
    OTHER = "other"
    UNKNOWN = "unknown"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    IN_NEGOTIATION = "in_negotiation"
    SETTLED = "settled"
    CLOSED = "closed"


class ComplianceType(str, enum.Enum):
    DEALER_LICENSE = "dealer_license"
    REGISTRATION = "registration"
    INSURANCE = "insurance"
    OTHER = "other"


class ComplianceStatus(str, enum.Enum):
    CURRENT = "current"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vin: Mapped[str] = mapped_column(String(17), unique=True, index=True, nullable=False)
    make: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    acquisition_date: Mapped[dt_date | None] = mapped_column(Date, nullable=True)
    acquisition_cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    title_status: Mapped[TitleStatus] = mapped_column(
        Enum(TitleStatus, native_enum=False, length=32),
        default=TitleStatus.PENDING,
        nullable=False,
    )
    status: Mapped[VehicleStatus] = mapped_column(
        Enum(VehicleStatus, native_enum=False, length=32),
        default=VehicleStatus.AVAILABLE,
        nullable=False,
    )
    odometer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hv_battery_warranty_expiration: Mapped[dt_date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    leases: Mapped[list["Lease"]] = relationship(back_populates="vehicle")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="vehicle")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    type: Mapped[CustomerType] = mapped_column(
        Enum(CustomerType, native_enum=False, length=32),
        default=CustomerType.LESSEE,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    leases: Mapped[list["Lease"]] = relationship(back_populates="customer")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="customer")


class Lease(Base):
    __tablename__ = "leases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    type: Mapped[LeaseType] = mapped_column(
        Enum(LeaseType, native_enum=False, length=32),
        default=LeaseType.PRIMARY_LEASE,
        nullable=False,
    )
    agreement_template_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_date: Mapped[dt_date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt_date | None] = mapped_column(Date, nullable=True)
    monthly_rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    deposit_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[LeaseStatus] = mapped_column(
        Enum(LeaseStatus, native_enum=False, length=32),
        default=LeaseStatus.ACTIVE,
        nullable=False,
    )
    signed_doc_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    vehicle: Mapped["Vehicle"] = relationship(back_populates="leases")
    customer: Mapped["Customer"] = relationship(back_populates="leases")
    payments: Mapped[list["Payment"]] = relationship(back_populates="lease")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lease_id: Mapped[int] = mapped_column(ForeignKey("leases.id"), nullable=False)
    due_date: Mapped[dt_date] = mapped_column(Date, nullable=False)
    amount_due: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    amount_paid: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    paid_date: Mapped[dt_date | None] = mapped_column(Date, nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False, length=32),
        default=PaymentStatus.OUTSTANDING,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    lease: Mapped["Lease"] = relationship(back_populates="payments")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    date: Mapped[dt_date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    at_fault: Mapped[AtFault] = mapped_column(
        Enum(AtFault, native_enum=False, length=16),
        default=AtFault.UNKNOWN,
        nullable=False,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, native_enum=False, length=32),
        default=IncidentStatus.OPEN,
        nullable=False,
    )
    counterparty_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Phase 1 simplification: related documents stored as a newline-separated
    # string of paths rather than a child table. Flagged as an open question
    # in LOG.md -- a proper many-to-many IncidentDocument table is the more
    # correct design if Jed wants structured document tracking later.
    related_doc_paths: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    vehicle: Mapped["Vehicle"] = relationship(back_populates="incidents")
    customer: Mapped["Customer | None"] = relationship(back_populates="incidents")


class ComplianceItem(Base):
    __tablename__ = "compliance_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[ComplianceType] = mapped_column(
        Enum(ComplianceType, native_enum=False, length=32),
        default=ComplianceType.OTHER,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(256), nullable=False)
    expiration_date: Mapped[dt_date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ComplianceStatus] = mapped_column(
        Enum(ComplianceStatus, native_enum=False, length=32),
        default=ComplianceStatus.CURRENT,
        nullable=False,
    )
    related_doc_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
