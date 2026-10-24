"""Pydantic schemas for Document Versions.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from app.models.version import VersionStatus


class DocumentVersionBase(BaseModel):
    document_name: str = Field(..., description="Document / device name, e.g. CT-200")
    version_tag: str = Field(..., description="Version label, e.g. v1.0")
    file_name: Optional[str] = None


class DocumentVersionCreate(DocumentVersionBase):
    file_hash: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class DocumentVersionResponse(DocumentVersionBase):
    id: str
    file_hash: Optional[str] = None
    status: VersionStatus
    total_pages: int = 0
    total_nodes: int = 0
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
