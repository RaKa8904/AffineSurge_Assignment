"""API routes for Selections.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.selection import Selection
from app.schemas.selection import SelectionResponse

router = APIRouter(prefix="/selections", tags=["Selections"])


@router.get("", response_model=List[SelectionResponse])
def list_selections(db: Session = Depends(get_db)):
    """List all selections."""
    return db.query(Selection).order_by(Selection.created_at.desc()).all()


@router.get("/{selection_id}", response_model=SelectionResponse)
def get_selection(selection_id: str, db: Session = Depends(get_db)):
    """Retrieve selection details including pinned node items."""
    selection = db.query(Selection).filter(Selection.id == selection_id).first()
    if not selection:
        raise HTTPException(
            status_code=status.HTTP404_NOT_FOUND,
            detail=f"Selection '{selection_id}' not found"
        )
    return selection
