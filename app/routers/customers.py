"""CRUD endpoints for Customer."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.models import Customer, Lease

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("/", response_model=schemas.CustomerRead, status_code=201)
def create_customer(payload: schemas.CustomerCreate, db: Session = Depends(get_db)):
    return crud.create(db, Customer, payload.model_dump())


@router.get("/", response_model=list[schemas.CustomerRead])
def list_customers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_list(db, Customer, skip, limit)


@router.get("/{customer_id}", response_model=schemas.CustomerRead)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Customer, customer_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return obj


@router.patch("/{customer_id}", response_model=schemas.CustomerRead)
def update_customer(customer_id: int, payload: schemas.CustomerUpdate, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Customer, customer_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return crud.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    """
    Blocks deletion if any Lease still references this customer (NOT NULL
    FK) -- see the matching guard/comment in routers/vehicles.py for why.
    Incident.customer_id is nullable, so incidents referencing this customer
    are allowed to have their FK nulled out rather than blocking the delete.
    """
    obj = crud.get_one(db, Customer, customer_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    if db.query(Lease).filter(Lease.customer_id == customer_id).first() is not None:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete customer: one or more leases reference it. Delete or reassign those leases first.",
        )
    crud.delete(db, obj)
    return None
