"""API routes for Version-Pinned Selections.
"""

from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models.selection import Selection, SelectionNode
from app.models.node import Node
from app.models.version import DocumentVersion
from app.schemas.selection import SelectionCreateRequest, SelectionResponse, SelectionNodeResponse
from app.schemas.node import NodeResponse

router = APIRouter(prefix="/selections", tags=["Selections"])


def resolve_version(db: Session, version_identifier: str) -> Optional[DocumentVersion]:
    """Resolves a version from either UUID or tag."""
    return (
        db.query(DocumentVersion)
        .filter(
            or_(
                DocumentVersion.id == version_identifier,
                DocumentVersion.version_tag == version_identifier
            )
        )
        .first()
    )


def format_selection_response(selection: Selection) -> SelectionResponse:
    """Formats a Selection ORM object into SelectionResponse DTO."""
    items_dto: List[SelectionNodeResponse] = []
    for item in sorted(selection.items, key=lambda i: i.order_index):
        node_dto = NodeResponse.model_validate(item.node) if item.node else None
        items_dto.append(
            SelectionNodeResponse(
                id=item.id,
                selection_id=item.selection_id,
                node_id=item.node_id,
                pinned_version_id=item.pinned_version_id,
                pinned_content_hash=item.pinned_content_hash,
                order_index=item.order_index,
                notes=item.notes,
                created_at=item.created_at,
                title=item.node.title if item.node else None,
                section_number=item.node.section_number if item.node else None,
                node=node_dto,
            )
        )

    return SelectionResponse(
        id=selection.id,
        version_id=selection.version_id,
        title=selection.title,
        description=selection.description,
        created_by=selection.created_by,
        created_at=selection.created_at,
        updated_at=selection.updated_at,
        total_nodes=len(items_dto),
        items=items_dto,
    )


@router.post("", response_model=SelectionResponse, status_code=status.HTTP_201_CREATED)
def create_or_get_selection(
    payload: SelectionCreateRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """Create a version-pinned selection of nodes.

    Deduplication Policy:
    If the exact same set of node_ids for the same version_id was already submitted,
    returns the existing selection rather than duplicating records in the database.
    """
    target_version = resolve_version(db, payload.version_id)
    if not target_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document version '{payload.version_id}' not found"
        )

    # Normalize incoming node IDs (preserve order, eliminate duplicates)
    unique_node_ids = list(dict.fromkeys(payload.node_ids))
    target_node_set = set(unique_node_ids)

    # Validate that all nodes exist and belong to target version
    nodes = (
        db.query(Node)
        .filter(
            Node.id.in_(unique_node_ids),
            Node.version_id == target_version.id
        )
        .all()
    )
    nodes_by_id = {n.id: n for n in nodes}

    missing_ids = [nid for nid in unique_node_ids if nid not in nodes_by_id]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Nodes {missing_ids} do not exist in document version '{target_version.version_tag}'"
            )
        )

    # Duplicate check: check existing selections for identical node set
    existing_selections = (
        db.query(Selection)
        .filter(Selection.version_id == target_version.id)
        .all()
    )
    for existing_sel in existing_selections:
        existing_node_set = {item.node_id for item in existing_sel.items}
        if existing_node_set == target_node_set:
            # Match found! Return existing selection with 200 OK
            response.status_code = status.HTTP_200_OK
            return format_selection_response(existing_sel)

    # Create new version-pinned selection
    selection = Selection(
        id=str(uuid.uuid4()),
        version_id=target_version.id,
        title=payload.title or "QA Test Selection",
        description=payload.description,
        created_by=payload.created_by,
    )
    db.add(selection)
    db.flush()

    # Pin each node with its exact snapshot content hash
    for order_idx, node_id in enumerate(unique_node_ids):
        node = nodes_by_id[node_id]
        item = SelectionNode(
            id=str(uuid.uuid4()),
            selection_id=selection.id,
            node_id=node.id,
            pinned_version_id=target_version.id,
            pinned_content_hash=node.content_hash,
            order_index=order_idx,
        )
        db.add(item)

    db.commit()
    db.refresh(selection)

    response.status_code = status.HTTP_201_CREATED
    return format_selection_response(selection)


@router.get("", response_model=List[SelectionResponse])
def list_selections(
    version_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all selections, optionally filtered by version."""
    query = db.query(Selection)
    if version_id:
        target_version = resolve_version(db, version_id)
        if target_version:
            query = query.filter(Selection.version_id == target_version.id)
        else:
            return []
    selections = query.order_by(Selection.created_at.desc()).all()
    return [format_selection_response(s) for s in selections]


@router.get("/{selection_id}", response_model=SelectionResponse)
def get_selection(selection_id: str, db: Session = Depends(get_db)):
    """Retrieve selection details including pinned node items."""
    selection = db.query(Selection).filter(Selection.id == selection_id).first()
    if not selection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Selection '{selection_id}' not found"
        )
    return format_selection_response(selection)
