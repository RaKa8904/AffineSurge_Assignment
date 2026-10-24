"""API routes for Tree Nodes, Browsing, and Search.
"""

import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models.node import Node, ChangeStatus
from app.models.version import DocumentVersion, VersionStatus
from app.schemas.node import (
    NodeTreeNode,
    NodeDetailResponse,
    NodeDiffSummary,
    NodeSearchResult,
    NodeResponse,
)

router = APIRouter(prefix="/nodes", tags=["Nodes"])


def resolve_version(db: Session, version_identifier: Optional[str]) -> Optional[DocumentVersion]:
    """Resolves a version from either a UUID or a version tag (e.g., 'v1.0').
    Defaults to the latest parsed version if not specified.
    """
    if version_identifier:
        # Check by ID first, then by version_tag
        version = (
            db.query(DocumentVersion)
            .filter(
                or_(
                    DocumentVersion.id == version_identifier,
                    DocumentVersion.version_tag == version_identifier
                )
            )
            .first()
        )
        return version

    # Default to latest parsed version
    return (
        db.query(DocumentVersion)
        .filter(DocumentVersion.status == VersionStatus.PARSED.value)
        .order_by(DocumentVersion.created_at.desc())
        .first()
    )


def build_search_snippet(content: str, query: str, window: int = 120) -> str:
    """Extracts a relevant contextual snippet around query match."""
    if not content:
        return ""
    match = re.search(re.escape(query), content, re.IGNORECASE)
    if not match:
        return content[:window] + ("..." if len(content) > window else "")
    start = max(0, match.start() - 40)
    end = min(len(content), match.end() + 80)
    snippet = content[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    return snippet


@router.get("", response_model=List[NodeTreeNode])
def list_top_level_nodes(
    version: Optional[str] = Query(None, description="Version ID or tag (e.g. 'v1.0', 'v2.0'). Defaults to latest."),
    db: Session = Depends(get_db),
):
    """List top-level sections (root nodes) with their recursive hierarchy.
    Defaults to the latest ingested document version.
    """
    target_version = resolve_version(db, version)
    if not target_version:
        return []

    # Query top-level nodes (parent_id is None, or depth == 0)
    root_nodes = (
        db.query(Node)
        .filter(
            Node.version_id == target_version.id,
            Node.parent_id.is_(None)
        )
        .order_by(Node.order_index)
        .all()
    )

    # Fallback if no explicit root with parent_id=None
    if not root_nodes:
        root_nodes = (
            db.query(Node)
            .filter(
                Node.version_id == target_version.id,
                Node.depth <= 1
            )
            .order_by(Node.order_index)
            .all()
        )

    return root_nodes


@router.get("/search", response_model=List[NodeSearchResult])
def search_nodes(
    q: str = Query(..., min_length=1, description="Search term matching heading or body text"),
    version: Optional[str] = Query(None, description="Optional version ID or tag filter"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
    db: Session = Depends(get_db),
):
    """Search across node headings and body text with relevance snippet."""
    query_builder = db.query(Node)

    if version:
        target_version = resolve_version(db, version)
        if target_version:
            query_builder = query_builder.filter(Node.version_id == target_version.id)
        else:
            return []

    # Case-insensitive substring match in content or title
    search_filter = or_(
        Node.content.ilike(f"%{q}%"),
        Node.title.ilike(f"%{q}%"),
        Node.section_number.ilike(f"%{q}%")
    )
    matches = query_builder.filter(search_filter).limit(limit).all()

    results: List[NodeSearchResult] = []
    for node in matches:
        snippet = build_search_snippet(node.content or node.title or "", q)
        # Compute simple score bonus for title matches
        score = 1.0
        if node.title and q.lower() in node.title.lower():
            score = 1.5

        results.append(
            NodeSearchResult(
                id=node.id,
                version_id=node.version_id,
                section_number=node.section_number,
                title=node.title,
                node_type=node.node_type,
                content=node.content,
                snippet=snippet,
                content_hash=node.content_hash,
                page_number=node.page_number,
                score=score,
            )
        )

    # Sort results by score descending
    results.sort(key=lambda r: r.score, reverse=True)
    return results


@router.get("/{node_id}", response_model=NodeDetailResponse)
def get_node(node_id: str, db: Session = Depends(get_db)):
    """Retrieve an individual node by ID.
    Includes full text, direct children, content hash, and diff summary if linked.
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found"
        )

    # Build lightweight diff summary
    diff_summary = None
    if node.linked_node_id:
        prior_node = db.query(Node).filter(Node.id == node.linked_node_id).first()
        diff_summary = NodeDiffSummary(
            change_status=node.change_status,
            linked_node_id=node.linked_node_id,
            similarity_score=node.similarity_score,
            change_summary=node.change_summary,
            prior_content_hash=prior_node.content_hash if prior_node else None,
            prior_title=prior_node.title if prior_node else None,
        )
    elif node.change_status == ChangeStatus.ADDED.value:
        diff_summary = NodeDiffSummary(
            change_status=ChangeStatus.ADDED,
            change_summary=node.change_summary or "New section added in this version."
        )
    else:
        diff_summary = NodeDiffSummary(
            change_status=node.change_status,
            change_summary=node.change_summary
        )

    children_dto = [NodeResponse.model_validate(c) for c in node.children]

    response_data = NodeDetailResponse(
        id=node.id,
        version_id=node.version_id,
        parent_id=node.parent_id,
        linked_node_id=node.linked_node_id,
        node_type=node.node_type,
        title=node.title,
        section_number=node.section_number,
        content=node.content,
        content_hash=node.content_hash,
        depth=node.depth,
        order_index=node.order_index,
        hierarchical_path=node.hierarchical_path,
        page_number=node.page_number,
        bbox_json=node.bbox_json,
        table_data=node.table_data,
        change_status=node.change_status,
        similarity_score=node.similarity_score,
        change_summary=node.change_summary,
        created_at=node.created_at,
        updated_at=node.updated_at,
        children=children_dto,
        diff_summary=diff_summary,
    )

    return response_data
