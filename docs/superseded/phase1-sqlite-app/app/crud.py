"""
Generic CRUD helper used by each entity router to avoid repeating the same
get/list/create/update/delete boilerplate six times.

This is intentionally simple (no generic repository framework) -- just a
few small functions parameterized by SQLAlchemy model class.
"""
from typing import Any, TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


def get_one(db: Session, model: type[ModelT], obj_id: int) -> ModelT | None:
    return db.get(model, obj_id)


def get_list(
    db: Session, model: type[ModelT], skip: int = 0, limit: int = 100
) -> list[ModelT]:
    return db.query(model).offset(skip).limit(limit).all()


def create(db: Session, model: type[ModelT], data: dict[str, Any]) -> ModelT:
    obj = model(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, obj: ModelT, data: dict[str, Any]) -> ModelT:
    for field, value in data.items():
        if value is not None:
            setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, obj: ModelT) -> None:
    db.delete(obj)
    db.commit()
