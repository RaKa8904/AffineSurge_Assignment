"""Pydantic schemas for Selections and Version-Pinned Nodes.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.node import NodeResponse


class SelectionCreateRequest(BaseModel):
    """Payload to create or retrieve a version-pinned selection."""
    version_id: str = Field(..., description="Target document version ID or version tag (e.g. 'v1.0')")
    node_ids: List[str] = Field(..., min_length=1, description="List of version-pinned node UUIDs")
    title: Optional[str] = Field("QA Test Case Selection", description="Title for this selection session")
    description: Optional[str] = Field(None, description="Optional description or rationale")
    created_by: str = Field("system", description="Identifier of the user or agent")


class SelectionNodeResponse(BaseModel):
    """Junction response for an individually pinned node."""
    id: str
    selection_id: str
    node_id: str
    pinned_version_id: str
    pinned_content_hash: str
    order_index: int
    notes: Optional[str] = None
    created_at: datetime
    title: Optional[str] = None
    section_number: Optional[str] = None
    node: Optional[NodeResponse] = None

    model_config = ConfigDict(from_attributes=True)


class SelectionResponse(BaseModel):
    """Complete representation of a version-pinned selection."""
    id: str
    version_id: str
    title: str
    description: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    total_nodes: int = 0
    items: List[SelectionNodeResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
