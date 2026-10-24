"""API routes for QA Test Cases and Staleness Retrieval.
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.selection import Selection
from app.models.version import DocumentVersion, VersionStatus
from app.models.node import Node
from app.schemas.test_case import (
    TestCaseRetrievalResponse,
    TestCaseNodeStaleness,
    QATestCase,
)
from app.services.llm_generator import (
    load_llm_output_from_store,
    get_json_store_dir,
    STALENESS_LIMITATION_NOTE,
)

router = APIRouter(prefix="/test-cases", tags=["Test Cases"])


@router.get("/{selection_id}", response_model=TestCaseRetrievalResponse)
def get_test_cases_with_staleness_check(
    selection_id: str,
    db: Session = Depends(get_db)
):
    """Retrieves generated test cases from the JSON store and audits them for staleness.

    Staleness Check Logic:
    Compares the pinned_content_hash of each node in the selection against the
    content_hash of the exact corresponding node in the latest ingested version.
    If the hashes differ (e.g. text or specs changed between v1 and v2), the test
    case is flagged as is_stale=True.

    Documented Limitation:
    Cryptographic content hashing is binary. A 1-word typo fix triggers the exact
    same staleness flag as a critical threshold change.
    """
    selection = db.query(Selection).filter(Selection.id == selection_id).first()
    if not selection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Selection '{selection_id}' not found"
        )

    # Load from local JSON store
    stored_data = load_llm_output_from_store(selection_id)
    if not stored_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No test cases have been generated yet for selection '{selection_id}'. "
                f"Call POST /api/v1/selections/{selection_id}/generate first."
            )
        )

    # Resolve latest available version of this document
    all_versions = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_name == selection.version.document_name,
            DocumentVersion.status == VersionStatus.PARSED.value
        )
        .all()
    )
    if all_versions:
        latest_version = max(
            all_versions,
            key=lambda v: (v.version_tag or "", v.created_at.isoformat() if v.created_at else "")
        )
    else:
        latest_version = selection.version

    # Index latest version nodes by section_number and by linked_node_id
    latest_by_sec = {n.section_number: n for n in latest_version.nodes if n.section_number}
    latest_by_linked = {n.linked_node_id: n for n in latest_version.nodes if n.linked_node_id}

    node_staleness_list: List[TestCaseNodeStaleness] = []
    has_any_stale_node = False
    stale_reasons: List[str] = []

    for item in selection.items:
        pinned_hash = item.pinned_content_hash
        node = item.node

        # Find corresponding node in the latest document version
        latest_node: Optional[Node] = None
        if node:
            if latest_version.id == selection.version_id:
                # Same version: latest is current
                latest_node = node
            else:
                # Look up via linked_node_id or section_number
                if node.id in latest_by_linked:
                    latest_node = latest_by_linked[node.id]
                elif node.section_number in latest_by_sec:
                    latest_node = latest_by_sec[node.section_number]

        is_stale = False
        staleness_reason = None

        if latest_node is None:
            # Node was removed or not found in latest version
            is_stale = True
            staleness_reason = (
                f"Section '{node.section_number if node else item.node_id}' is no longer present "
                f"in latest manual version {latest_version.version_tag}."
            )
        elif latest_node.content_hash != pinned_hash:
            # Content changed between pinned version and latest version
            is_stale = True
            staleness_reason = (
                f"Underlying content of Section '{latest_node.section_number}' was modified "
                f"between {selection.version.version_tag} and {latest_version.version_tag} "
                f"(hash diverged from {pinned_hash[:8]}... to {latest_node.content_hash[:8]}...)."
            )

        if is_stale:
            has_any_stale_node = True
            if staleness_reason:
                stale_reasons.append(staleness_reason)

        node_staleness_list.append(
            TestCaseNodeStaleness(
                node_id=item.node_id,
                section_number=node.section_number if node else None,
                title=node.title if node else None,
                pinned_version_tag=selection.version.version_tag,
                pinned_content_hash=pinned_hash,
                latest_version_tag=latest_version.version_tag,
                latest_content_hash=latest_node.content_hash if latest_node else None,
                is_stale=is_stale,
                staleness_reason=staleness_reason,
            )
        )

    # Format test cases from JSON store
    raw_cases = stored_data.get("test_cases", [])
    parsed_cases = [QATestCase.model_validate(tc) for tc in raw_cases]

    gen_time = (
        datetime.fromisoformat(stored_data["generated_at"])
        if "generated_at" in stored_data
        else datetime.now(timezone.utc)
    )

    summary_reason = "; ".join(stale_reasons) if stale_reasons else None

    return TestCaseRetrievalResponse(
        selection_id=selection.id,
        selection_title=selection.title,
        selection_version_tag=selection.version.version_tag,
        latest_version_tag=latest_version.version_tag,
        is_stale=has_any_stale_node,
        staleness_reason=summary_reason,
        limitation_note=STALENESS_LIMITATION_NOTE,
        node_staleness=node_staleness_list,
        test_cases=parsed_cases,
        generated_at=gen_time,
        from_cache=True,
        storage_path=str(get_json_store_dir() / f"{selection_id}.json"),
    )
