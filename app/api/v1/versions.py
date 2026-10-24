"""API routes for Document Versions.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models.version import DocumentVersion
from app.schemas.version import DocumentVersionResponse
from app.services.ingestion import get_version_diff_summary

router = APIRouter(prefix="/versions", tags=["Versions"])


@router.get("", response_model=List[DocumentVersionResponse])
def list_versions(db: Session = Depends(get_db)):
    """List all ingested document versions."""
    versions = db.query(DocumentVersion).order_by(DocumentVersion.created_at.desc()).all()
    return versions


@router.get("/{version_id}", response_model=DocumentVersionResponse)
def get_version(version_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a specific document version by UUID or version tag."""
    version = (
        db.query(DocumentVersion)
        .filter(
            or_(
                DocumentVersion.id == version_id,
                DocumentVersion.version_tag == version_id
            )
        )
        .first()
    )
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document version '{version_id}' not found"
        )
    return version


@router.get("/{version_id}/diff")
def get_version_diff(version_id: str, db: Session = Depends(get_db)):
    """Retrieve diff summary of changes between this version and its baseline."""
    version = (
        db.query(DocumentVersion)
        .filter(
            or_(
                DocumentVersion.id == version_id,
                DocumentVersion.version_tag == version_id
            )
        )
        .first()
    )
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document version '{version_id}' not found"
        )
    return get_version_diff_summary(db=db, version_id=version.id)
