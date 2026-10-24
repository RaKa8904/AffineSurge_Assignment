"""Pydantic schemas for Document Tree Nodes and Browse APIs.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.node import NodeType, ChangeStatus


class NodeBase(BaseModel):
    node_type: NodeType = NodeType.PARAGRAPH
    title: Optional[str] = None
    section_number: Optional[str] = None
    content: str
    depth: int = 0
    level: int = 0
    order_index: int = 0
    page_number: Optional[int] = None
    hierarchical_path: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def sync_level_and_depth(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "depth" in data and "level" not in data:
                data["level"] = data["depth"]
            elif "level" in data and "depth" not in data:
                data["depth"] = data["level"]
        elif hasattr(data, "depth") and not hasattr(data, "level"):
            # ORM model
            pass
        return data


class NodeCreate(NodeBase):
    version_id: str
    parent_id: Optional[str] = None
    linked_node_id: Optional[str] = None
    bbox_json: Optional[List[float]] = None
    table_data: Optional[Dict[str, Any]] = None
    change_status: ChangeStatus = ChangeStatus.UNCHANGED
    similarity_score: Optional[float] = None
    change_summary: Optional[str] = None


class NodeResponse(NodeBase):
    id: str
    version_id: str
    parent_id: Optional[str] = None
    linked_node_id: Optional[str] = None
    content_hash: str
    change_status: ChangeStatus
    similarity_score: Optional[float] = None
    change_summary: Optional[str] = None
    page_number: Optional[int] = None
    bbox_json: Optional[Any] = None
    table_data: Optional[Any] = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def set_level_from_orm(cls, data: Any) -> Any:
        if hasattr(data, "depth") and not isinstance(data, dict):
            # Create a proxy dict or let from_attributes handle it with level=depth
            pass
        return data

    model_config = ConfigDict(from_attributes=True)


class NodeTreeNode(NodeResponse):
    """Recursive tree structure node for hierarchical document browsing."""
    children: List["NodeTreeNode"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class NodeDiffSummary(BaseModel):
    """Lightweight diff summary for nodes linked to a previous version."""
    change_status: ChangeStatus
    linked_node_id: Optional[str] = None
    similarity_score: Optional[float] = None
    change_summary: Optional[str] = None
    prior_content_hash: Optional[str] = None
    prior_title: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class NodeDetailResponse(NodeResponse):
    """Detailed response for a single node including full text, children, and diff."""
    children: List[NodeResponse] = Field(default_factory=list)
    diff_summary: Optional[NodeDiffSummary] = None

    model_config = ConfigDict(from_attributes=True)


class NodeSearchResult(BaseModel):
    """Search match result across headings and content."""
    id: str
    version_id: str
    section_number: Optional[str] = None
    title: Optional[str] = None
    node_type: NodeType
    content: str
    snippet: str
    content_hash: str
    page_number: Optional[int] = None
    score: float = 1.0

    model_config = ConfigDict(from_attributes=True)
