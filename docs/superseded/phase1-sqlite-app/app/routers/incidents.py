"""CRUD endpoints for Incident."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.models import Customer, Incident, Vehicle

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _validate_fks(db: Session, vehicle_id: int, customer_id: int | None) -> None:
    if crud.get_one(db, Vehicle, vehicle_id) is None:
        raise HTTPException(status_code=422, detail=f"vehicle_id {vehicle_id} does not exist")
    if customer_id is not None and crud.get_one(db, Customer, customer_id) is None:
        raise HTTPException(status_code=422, detail=f"customer_id {customer_id} does not exist")


@router.post("/", response_model=schemas.IncidentRead, status_code=201)
def create_incident(payload: schemas.IncidentCreate, db: Session = Depends(get_db)):
    _validate_fks(db, payload.vehicle_id, payload.customer_id)
    return crud.create(db, Incident, payload.model_dump())


@router.get("/", response_model=list[schemas.IncidentRead])
def list_incidents(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_list(db, Incident, skip, limit)


@router.get("/{incident_id}", response_model=schemas.IncidentRead)
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Incident, incident_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return obj


@router.patch("/{incident_id}", response_model=schemas.IncidentRead)
def update_incident(incident_id: int, payload: schemas.IncidentUpdate, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Incident, incident_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    data = payload.model_dump(exclude_unset=True)
    if "vehicle_id" in data or "customer_id" in data:
        _validate_fks(
            db,
            data.get("vehicle_id", obj.vehicle_id),
            data.get("customer_id", obj.customer_id),
        )
    return crud.update(db, obj, data)


@router.delete("/{incident_id}", status_code=204)
def delete_incident(incident_id: int, db: Session = Depends(get_db)):
    obj = crud.get_one(db, Incident, incident_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    crud.delete(db, obj)
    return None
