"""Pydantic schemas for Document Tree Nodes.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from app.models.node import NodeType, ChangeStatus


class NodeBase(BaseModel):
    node_type: NodeType = NodeType.PARAGRAPH
    title: Optional[str] = None
    section_number: Optional[str] = None
    content: str
    depth: int = 0
    order_index: int = 0
    page_number: Optional[int] = None
    hierarchical_path: Optional[str] = None


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

    model_config = ConfigDict(from_attributes=True)


class NodeTreeNode(NodeResponse):
    """Recursive tree structure node for hierarchical document browsing."""
    children: List["NodeTreeNode"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class NodeSearchResult(BaseModel):
    node: NodeResponse
    matched_text_snippet: str
    score: float
