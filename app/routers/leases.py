"""CRUD endpoints for Lease."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.models import Customer, Lease, Payment, Vehicle

router = APIRouter(prefix="/leases", tags=["leases"])


def _validate_fks(db: Session, vehicle_id: int, customer_id: int) -> None:
    if crud.get_one(db, Vehicle, vehicle_id) is None:
        raise HTTPException(status_code=422, detail=f"vehicle_id {vehicle_id} does not exist")
    if crud.get_one(db, Customer, customer_id) is None:
        raise HTTPException(status_code=422, detail=f"customer_id {customer_id} does not exist")


@router.post("/", response_model=schemas.LeaseRead, status_code=201)
def create_lease(payload: schemas.LeaseCreate, db: Session = Depends(get_db)):
    _validate_fks(db, payload.vehicle_id, payload.customer_id)
    return crud.create(db, Lease, payload.model_dump())


@router.get("/", response_model=list[schemas.LeaseRead])
def list_leases(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_list(db, Lease, skip, limit)


@router.get("/{lease_id}", response_model=schemas.LeaseRead)
def get_lease(lease_id: int, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Lease, lease_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Lease not found")
    return obj


@router.patch("/{lease_id}", response_model=schemas.LeaseRead)
def update_lease(lease_id: int, payload: schemas.LeaseUpdate, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Lease, lease_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Lease not found")
    data = payload.model_dump(exclude_unset=True)
    if "vehicle_id" in data or "customer_id" in data:
        _validate_fks(
            db,
            data.get("vehicle_id", obj.vehicle_id),
            data.get("customer_id", obj.customer_id),
        )
    return crud.update(db, obj, data)


@router.delete("/{lease_id}", status_code=204)
def delete_lease(lease_id: int, db: Session = Depends(get_db)):
    """Blocks deletion if any Payment still references this lease (NOT NULL FK)."""
    obj = crud.get_one(db, Lease, lease_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Lease not found")
    if db.query(Payment).filter(Payment.lease_id == lease_id).first() is not None:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete lease: one or more payments reference it. Delete those payments first.",
        )
    crud.delete(db, obj)
    return None
