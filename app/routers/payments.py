"""CRUD endpoints for Payment."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.models import Lease, Payment

router = APIRouter(prefix="/payments", tags=["payments"])


def _validate_lease(db: Session, lease_id: int) -> None:
    if crud.get_one(db, Lease, lease_id) is None:
        raise HTTPException(status_code=422, detail=f"lease_id {lease_id} does not exist")


@router.post("/", response_model=schemas.PaymentRead, status_code=201)
def create_payment(payload: schemas.PaymentCreate, db: Session = Depends(get_db)):
    _validate_lease(db, payload.lease_id)
    return crud.create(db, Payment, payload.model_dump())


@router.get("/", response_model=list[schemas.PaymentRead])
def list_payments(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_list(db, Payment, skip, limit)


@router.get("/{payment_id}", response_model=schemas.PaymentRead)
def get_payment(payment_id: int, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Payment, payment_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return obj


@router.patch("/{payment_id}", response_model=schemas.PaymentRead)
def update_payment(payment_id: int, payload: schemas.PaymentUpdate, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Payment, payment_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    data = payload.model_dump(exclude_unset=True)
    if "lease_id" in data:
        _validate_lease(db, data["lease_id"])
    return crud.update(db, obj, data)


@router.delete("/{payment_id}", status_code=204)
def delete_payment(payment_id: int, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Payment, payment_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    crud.delete(db, obj)
    return None
