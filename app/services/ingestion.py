"""Database Ingestion & Cross-Version Diff Service.

Persists parsed document trees into SQLAlchemy database models (DocumentVersion, Node)
preserving parent-child relationships, sibling order indices, and executing path-based
cross-version matching to link and flag modified, added, and unchanged nodes.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import uuid
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.version import DocumentVersion, VersionStatus
from app.models.node import Node, NodeType, ChangeStatus
from app.services.pdf_parser import parse_pdf_to_tree, ParsedNode, ParsedTree


def determine_node_type(parsed_node: ParsedNode) -> str:
    """Classifies the semantic node type based on level and content."""
    if parsed_node.level == 0:
        return NodeType.DOCUMENT_ROOT.value
    elif parsed_node.level == 1:
        return NodeType.HEADING_1.value
    elif parsed_node.level == 2:
        return NodeType.HEADING_2.value
    elif parsed_node.level >= 3:
        return NodeType.HEADING_3.value
    return NodeType.SECTION.value


def ingest_document_version(
    db: Session,
    pdf_path: str | Path,
    document_name: str,
    version_tag: str,
    prior_version_tag: Optional[str] = None,
    reingest: bool = False,
) -> DocumentVersion:
    """Ingests a PDF manual into the database as a versioned document tree.

    Args:
        db: Active SQLAlchemy database session.
        pdf_path: Path to the manual PDF file.
        document_name: Identifier for the medical device (e.g. 'CT-200').
        version_tag: Version tag for this manual release (e.g. 'v1.0', 'v2.0').
        prior_version_tag: Optional tag of the baseline version to compare against.
                           If None and this is not v1, defaults to latest parsed version.
        reingest: If True, replaces existing version records if already present.

    Returns:
        The ingested and committed DocumentVersion database record.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    # Check for existing version record
    existing_version = (
        db.query(DocumentVersion)
        .filter_by(document_name=document_name, version_tag=version_tag)
        .first()
    )
    if existing_version:
        if reingest:
            db.delete(existing_version)
            db.commit()
        else:
            return existing_version

    # Parse the PDF into memory tree
    parsed_tree: ParsedTree = parse_pdf_to_tree(path, document_name=document_name)

    # Resolve prior version for cross-version linking
    prior_version: Optional[DocumentVersion] = None
    if prior_version_tag:
        prior_version = (
            db.query(DocumentVersion)
            .filter_by(document_name=document_name, version_tag=prior_version_tag)
            .first()
        )
    elif version_tag.lower() not in ["v1", "v1.0", "1.0", "1"]:
        # Lookup latest parsed version for this document
        prior_version = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_name == document_name,
                DocumentVersion.version_tag != version_tag,
                DocumentVersion.status == VersionStatus.PARSED.value
            )
            .order_by(DocumentVersion.created_at.desc())
            .first()
        )

    # Index prior version nodes by section_number and title for fast matching
    prior_by_section: Dict[str, Node] = {}
    prior_by_title: Dict[str, Node] = {}
    if prior_version:
        for p_node in prior_version.nodes:
            if p_node.section_number:
                prior_by_section[p_node.section_number] = p_node
            if p_node.title:
                prior_by_title[p_node.title.strip().lower()] = p_node

    # Create DocumentVersion header record
    doc_version = DocumentVersion(
        id=str(uuid.uuid4()),
        document_name=document_name,
        version_tag=version_tag,
        file_name=path.name,
        file_hash=parsed_tree.file_hash,
        status=VersionStatus.PARSING.value,
        total_pages=parsed_tree.total_pages,
        total_nodes=len(parsed_tree.all_nodes),
        metadata_json={
            "pdf_path": str(path),
            "prior_version_tag": prior_version.version_tag if prior_version else None,
        }
    )
    db.add(doc_version)
    db.flush()

    # Walk parsed tree breadth-first or depth-first and construct DB Node models
    parsed_to_db: Dict[ParsedNode, Node] = {}
    sibling_counters: Dict[Optional[ParsedNode], int] = {}
    created_db_nodes: List[Node] = []

    # Queue of (parsed_node, parent_parsed_node)
    queue: List[tuple[ParsedNode, Optional[ParsedNode]]] = [(parsed_tree.root, None)]

    while queue:
        current_parsed, parent_parsed = queue.pop(0)

        # Sibling order tracking
        sibling_idx = sibling_counters.get(parent_parsed, 0)
        sibling_counters[parent_parsed] = sibling_idx + 1

        # Parent DB ID and path
        parent_db_node = parsed_to_db.get(parent_parsed) if parent_parsed else None
        parent_id = parent_db_node.id if parent_db_node else None

        if parent_db_node:
            sec_part = current_parsed.section_number or current_parsed.title[:20].replace(" ", "_")
            hierarchical_path = f"{parent_db_node.hierarchical_path}/{sec_part}"
        else:
            hierarchical_path = f"/{current_parsed.section_number or 'root'}"

        # Cross-version matching and diff evaluation
        linked_node_id: Optional[str] = None
        change_status: str = ChangeStatus.UNCHANGED.value
        similarity_score: Optional[float] = None
        change_summary: Optional[str] = None

        if not prior_version:
            # Baseline v1 ingest: all nodes are UNCHANGED baseline
            change_status = ChangeStatus.UNCHANGED.value
            similarity_score = 1.0
        else:
            # Path-based candidate lookup: primary key is section_number
            candidate: Optional[Node] = None
            if current_parsed.section_number:
                candidate = prior_by_section.get(current_parsed.section_number)
            if not candidate and current_parsed.title:
                candidate = prior_by_title.get(current_parsed.title.strip().lower())

            if candidate:
                linked_node_id = candidate.id
                # Compare canonical content hashes
                if current_parsed.content_hash == candidate.content_hash:
                    change_status = ChangeStatus.UNCHANGED.value
                    similarity_score = 1.0
                else:
                    change_status = ChangeStatus.MODIFIED.value
                    # Compute lexical similarity with prior version
                    sim = fuzz.token_sort_ratio(
                        candidate.content or "",
                        current_parsed.body_text or ""
                    )
                    similarity_score = round(sim / 100.0, 3)
                    change_summary = (
                        f"Modified from {prior_version.version_tag}: "
                        f"similarity={similarity_score:.1%}"
                    )
            else:
                # Brand new section introduced in this version
                change_status = ChangeStatus.ADDED.value
                similarity_score = None
                change_summary = f"New section added in {version_tag}."

        node_content = current_parsed.body_text if current_parsed.body_text else (current_parsed.title or "")

        db_node = Node(
            id=str(uuid.uuid4()),
            version_id=doc_version.id,
            parent_id=parent_id,
            linked_node_id=linked_node_id,
            node_type=determine_node_type(current_parsed),
            title=current_parsed.title,
            section_number=current_parsed.section_number,
            content=node_content,
            content_hash=current_parsed.content_hash,
            depth=current_parsed.level,
            order_index=sibling_idx,
            hierarchical_path=hierarchical_path,
            page_number=current_parsed.page_number,
            table_data=current_parsed.tables if current_parsed.tables else None,
            change_status=change_status,
            similarity_score=similarity_score,
            change_summary=change_summary,
        )

        db.add(db_node)
        db.flush()

        parsed_to_db[current_parsed] = db_node
        created_db_nodes.append(db_node)

        # Enqueue children in document encounter order
        for child in current_parsed.children:
            queue.append((child, current_parsed))

    # Mark document version as PARSED and commit
    doc_version.status = VersionStatus.PARSED.value
    doc_version.total_nodes = len(created_db_nodes)
    db.commit()
    db.refresh(doc_version)

    return doc_version


def get_version_diff_summary(db: Session, version_id: str) -> Dict[str, Any]:
    """Generates a summary of unchanged, modified, and added nodes for a document version."""
    version = db.query(DocumentVersion).filter_by(id=version_id).first()
    if not version:
        raise ValueError(f"DocumentVersion {version_id} not found")

    unchanged = [n for n in version.nodes if n.change_status == ChangeStatus.UNCHANGED.value]
    modified = [n for n in version.nodes if n.change_status == ChangeStatus.MODIFIED.value]
    added = [n for n in version.nodes if n.change_status == ChangeStatus.ADDED.value]

    return {
        "version_tag": version.version_tag,
        "total_nodes": len(version.nodes),
        "unchanged_count": len(unchanged),
        "modified_count": len(modified),
        "added_count": len(added),
        "modified_sections": [
            {
                "section": n.section_number,
                "title": n.title,
                "similarity": n.similarity_score,
                "summary": n.change_summary
            }
            for n in modified
        ],
        "added_sections": [
            {
                "section": n.section_number,
                "title": n.title,
                "summary": n.change_summary
            }
            for n in added
        ]
    }
