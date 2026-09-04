"""CRUD endpoints for ComplianceItem."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.models import ComplianceItem

router = APIRouter(prefix="/compliance-items", tags=["compliance"])


@router.post("/", response_model=schemas.ComplianceItemRead, status_code=201)
def create_compliance_item(payload: schemas.ComplianceItemCreate, db: Session = Depends(get_db)):
    return crud.create(db, ComplianceItem, payload.model_dump())


@router.get("/", response_model=list[schemas.ComplianceItemRead])
def list_compliance_items(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_list(db, ComplianceItem, skip, limit)


@router.get("/{item_id}", response_model=schemas.ComplianceItemRead)
def get_compliance_item(item_id: int, db: Session = Depends(get_db)):
    obj = crud.get_one(db, ComplianceItem, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="ComplianceItem not found")
    return obj


@router.patch("/{item_id}", response_model=schemas.ComplianceItemRead)
def update_compliance_item(item_id: int, payload: schemas.ComplianceItemUpdate, db: Session = Depends(get_db)):
    obj = crud.get_one(db, ComplianceItem, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="ComplianceItem not found")
    return crud.update(db, obj, payload.model_dump(exclude_unset=True))


@router.delete("/{item_id}", status_code=204)
def delete_compliance_item(item_id: int, db: Session = Depends(get_db)):
    obj = crud.get_one(db, ComplianceItem, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="ComplianceItem not found")
    crud.delete(db, obj)
    return None
