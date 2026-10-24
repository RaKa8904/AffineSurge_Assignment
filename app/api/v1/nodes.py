"""API routes for Tree Nodes and Search.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.node import Node
from app.schemas.node import NodeResponse

router = APIRouter(prefix="/nodes", tags=["Nodes"])


@router.get("/{node_id}", response_model=NodeResponse)
def get_node(node_id: str, db: Session = Depends(get_db)):
    """Retrieve an individual node by its UUID."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP404_NOT_FOUND,
            detail=f"Node '{node_id}' not found"
        )
    return node


@router.get("/search", response_model=List[NodeResponse])
def search_nodes(
    q: str = Query(..., min_length=2, description="Text search query"),
    version_id: str = Query(None, description="Optional version filter"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Search node content and titles."""
    query = db.query(Node)
    if version_id:
        query = query.filter(Node.version_id == version_id)
    query = query.filter(
        (Node.content.ilike(f"%{q}%")) | (Node.title.ilike(f"%{q}%"))
    )
    return query.limit(limit).all()
