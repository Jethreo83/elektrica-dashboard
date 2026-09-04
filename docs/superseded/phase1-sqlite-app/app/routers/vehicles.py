"""CRUD endpoints for Vehicle."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.models import Incident, Lease, Vehicle

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.post("/", response_model=schemas.VehicleRead, status_code=201)
def create_vehicle(payload: schemas.VehicleCreate, db: Session = Depends(get_db)):
    existing = db.query(Vehicle).filter(Vehicle.vin == payload.vin).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Vehicle with VIN {payload.vin} already exists")
    return crud.create(db, Vehicle, payload.model_dump())


@router.get("/", response_model=list[schemas.VehicleRead])
def list_vehicles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_list(db, Vehicle, skip, limit)


@router.get("/{vehicle_id}", response_model=schemas.VehicleRead)
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Vehicle, vehicle_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return obj


@router.patch("/{vehicle_id}", response_model=schemas.VehicleRead)
def update_vehicle(vehicle_id: int, payload: schemas.VehicleUpdate, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Vehicle, vehicle_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return crud.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    """
    Blocks deletion if any Lease or Incident still references this vehicle
    (both FKs are NOT NULL). Without this check, SQLAlchemy's default
    save-update cascade tries to null out the child FK on delete and SQLite
    raises an unhandled IntegrityError -> bare 500. Caught by manual testing
    during Phase 1 build (see LOG.md); every entity with NOT NULL child FKs
    gets the same explicit guard, not just Vehicle.
    """
    obj = crud.get_one(db, Vehicle, vehicle_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if db.query(Lease).filter(Lease.vehicle_id == vehicle_id).first() is not None:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete vehicle: one or more leases reference it. Delete or reassign those leases first.",
        )
    if db.query(Incident).filter(Incident.vehicle_id == vehicle_id).first() is not None:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete vehicle: one or more incidents reference it. Delete or reassign those incidents first.",
        )
    crud.delete(db, obj)
    return None
