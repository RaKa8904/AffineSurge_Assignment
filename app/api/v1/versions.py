"""API routes for Document Versions.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.version import DocumentVersion
from app.schemas.version import DocumentVersionResponse

router = APIRouter(prefix="/versions", tags=["Versions"])


@router.get("", response_model=List[DocumentVersionResponse])
def list_versions(db: Session = Depends(get_db)):
    """List all ingested document versions."""
    versions = db.query(DocumentVersion).order_by(DocumentVersion.created_at.desc()).all()
    return versions


@router.get("/{version_id}", response_model=DocumentVersionResponse)
def get_version(version_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a specific document version."""
    version = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
    if not version:
        raise HTTPException(
            status_code=status.HTTP404_NOT_FOUND,
            detail=f"Document version '{version_id}' not found"
        )
    return version
