"""Pydantic schemas for Selections and Version-Pinned Nodes.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.node import NodeResponse


class SelectionItemInput(BaseModel):
    node_id: str = Field(..., description="Target node ID to pin")
    notes: Optional[str] = None
    order_index: int = 0


class SelectionCreateRequest(BaseModel):
    version_id: str = Field(..., description="Target version ID")
    title: str = Field(..., description="Descriptive selection title")
    description: Optional[str] = None
    created_by: str = "system"
    node_ids: List[str] = Field(..., min_length=1, description="List of version-pinned node IDs")
    notes: Optional[str] = None


class SelectionNodeResponse(BaseModel):
    id: str
    selection_id: str
    node_id: str
    pinned_version_id: str
    pinned_content_hash: str
    order_index: int
    notes: Optional[str] = None
    created_at: datetime
    node: Optional[NodeResponse] = None

    model_config = ConfigDict(from_attributes=True)


class SelectionResponse(BaseModel):
    id: str
    version_id: str
    title: str
    description: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    items: List[SelectionNodeResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
