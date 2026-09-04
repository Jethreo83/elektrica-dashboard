"""
Pydantic schemas (request/response models) for Phase 1 CRUD endpoints.

Convention: for each entity we define
  - <Entity>Base    shared fields
  - <Entity>Create  fields required/allowed on create (inherits Base)
  - <Entity>Update  all fields optional (PATCH-style partial update)
  - <Entity>Read    what's returned to the client (adds id + timestamps)

model_config = ConfigDict(from_attributes=True) lets these read models be
built directly from SQLAlchemy ORM instances.

Note on the `dt_date` import alias: Incident has a field literally named
`date`. Pydantic (and Python's typing.get_type_hints in general) resolves
string/deferred annotations using the *class's own namespace* as part of
localns -- so a class attribute named `date` (created by e.g.
`date: date | None = None`, which assigns `date = None` in the class body)
shadows the `datetime.date` type for every annotation in that same class,
including its own. This raised `TypeError: unsupported operand type(s) for
|: 'NoneType' and 'NoneType'` at import time (caught by pytest during Phase
1 build, logged in LOG.md). Aliasing the type import to `dt_date` and never
spelling the bare identifier `date` in a type position sidesteps the
collision entirely; the field is still named/serialized as `date` in the
API (JSON keys come from the field name, not the type name).
"""
from datetime import date as dt_date
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import (
    AtFault,
    ComplianceStatus,
    ComplianceType,
    CustomerType,
    IncidentStatus,
    LeaseStatus,
    LeaseType,
    PaymentStatus,
    TitleStatus,
    VehicleStatus,
)


# ---------------------------------------------------------------------------
# Vehicle
# ---------------------------------------------------------------------------

class VehicleBase(BaseModel):
    vin: str
    make: str
    model: str
    year: int
    acquisition_date: dt_date | None = None
    acquisition_cost: float | None = None
    title_status: TitleStatus = TitleStatus.PENDING
    status: VehicleStatus = VehicleStatus.AVAILABLE
    odometer: int | None = None
    hv_battery_warranty_expiration: dt_date | None = None
    notes: str | None = None


class VehicleCreate(VehicleBase):
    pass


class VehicleUpdate(BaseModel):
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    acquisition_date: dt_date | None = None
    acquisition_cost: float | None = None
    title_status: TitleStatus | None = None
    status: VehicleStatus | None = None
    odometer: int | None = None
    hv_battery_warranty_expiration: dt_date | None = None
    notes: str | None = None


class VehicleRead(VehicleBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class CustomerBase(BaseModel):
    name: str
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    type: CustomerType = CustomerType.LESSEE
    notes: str | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    type: CustomerType | None = None
    notes: str | None = None


class CustomerRead(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Lease
# ---------------------------------------------------------------------------

class LeaseBase(BaseModel):
    vehicle_id: int
    customer_id: int
    type: LeaseType = LeaseType.PRIMARY_LEASE
    agreement_template_version: str | None = None
    start_date: dt_date
    end_date: dt_date | None = None
    monthly_rate: float
    deposit_amount: float | None = None
    status: LeaseStatus = LeaseStatus.ACTIVE
    signed_doc_path: str | None = None


class LeaseCreate(LeaseBase):
    pass


class LeaseUpdate(BaseModel):
    vehicle_id: int | None = None
    customer_id: int | None = None
    type: LeaseType | None = None
    agreement_template_version: str | None = None
    start_date: dt_date | None = None
    end_date: dt_date | None = None
    monthly_rate: float | None = None
    deposit_amount: float | None = None
    status: LeaseStatus | None = None
    signed_doc_path: str | None = None


class LeaseRead(LeaseBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class PaymentBase(BaseModel):
    lease_id: int
    due_date: dt_date
    amount_due: float
    amount_paid: float | None = None
    paid_date: dt_date | None = None
    status: PaymentStatus = PaymentStatus.OUTSTANDING


class PaymentCreate(PaymentBase):
    pass


class PaymentUpdate(BaseModel):
    lease_id: int | None = None
    due_date: dt_date | None = None
    amount_due: float | None = None
    amount_paid: float | None = None
    paid_date: dt_date | None = None
    status: PaymentStatus | None = None


class PaymentRead(PaymentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------

class IncidentBase(BaseModel):
    vehicle_id: int
    customer_id: int | None = None
    date: dt_date
    description: str
    at_fault: AtFault = AtFault.UNKNOWN
    status: IncidentStatus = IncidentStatus.OPEN
    counterparty_name: str | None = None
    related_doc_paths: str | None = None


class IncidentCreate(IncidentBase):
    pass


class IncidentUpdate(BaseModel):
    vehicle_id: int | None = None
    customer_id: int | None = None
    date: dt_date | None = None
    description: str | None = None
    at_fault: AtFault | None = None
    status: IncidentStatus | None = None
    counterparty_name: str | None = None
    related_doc_paths: str | None = None


class IncidentRead(IncidentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ComplianceItem
# ---------------------------------------------------------------------------

class ComplianceItemBase(BaseModel):
    type: ComplianceType = ComplianceType.OTHER
    description: str
    expiration_date: dt_date | None = None
    status: ComplianceStatus = ComplianceStatus.CURRENT
    related_doc_path: str | None = None


class ComplianceItemCreate(ComplianceItemBase):
    pass


class ComplianceItemUpdate(BaseModel):
    type: ComplianceType | None = None
    description: str | None = None
    expiration_date: dt_date | None = None
    status: ComplianceStatus | None = None
    related_doc_path: str | None = None


class ComplianceItemRead(ComplianceItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
