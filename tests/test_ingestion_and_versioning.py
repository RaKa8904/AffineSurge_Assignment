"""Unit tests for Database Ingestion and Cross-Version Linking (v1 vs v2).
"""

from pathlib import Path
import pytest
from app.models.version import DocumentVersion, VersionStatus
from app.models.node import Node, ChangeStatus
from app.services.ingestion import ingest_document_version, get_version_diff_summary

V1_PDF = Path("ct200_manual.pdf")
V2_PDF = Path("ct200_manual_v2.pdf")


def test_full_document_ingestion_and_cross_version_linking(db_session):
    """Test full ingestion of CT-200 v1 and v2 into test database.
    Asserts:
    1. v1 is ingested as baseline with all nodes linked to hierarchy.
    2. v2 is ingested and compared against v1.
    3. Section 4.2 (Error Codes) is flagged as MODIFIED with linked_node pointing to v1.
    4. Section 5.3 (Data Export) is flagged as ADDED with linked_node as None.
    5. Section 2.1.1.1 (Battery Life) is flagged as MODIFIED.
    6. Section 1.1 (Intended Use) is flagged as UNCHANGED.
    7. Database parent-child relationships and order indices are preserved.
    """
    assert V1_PDF.exists(), f"v1 PDF not found: {V1_PDF}"
    assert V2_PDF.exists(), f"v2 PDF not found: {V2_PDF}"

    # 1. Ingest v1 manual (baseline)
    v1_doc = ingest_document_version(
        db=db_session,
        pdf_path=V1_PDF,
        document_name="CT-200",
        version_tag="v1.0"
    )

    assert v1_doc is not None
    assert v1_doc.version_tag == "v1.0"
    assert v1_doc.status == VersionStatus.PARSED.value
    assert v1_doc.total_pages == 6
    assert v1_doc.total_nodes == 28

    # Query v1 nodes from DB
    v1_nodes = db_session.query(Node).filter_by(version_id=v1_doc.id).all()
    assert len(v1_nodes) == 28
    v1_by_sec = {n.section_number: n for n in v1_nodes if n.section_number}

    # Verify v1 baseline statuses
    for n in v1_nodes:
        assert n.change_status == ChangeStatus.UNCHANGED.value
        assert n.linked_node_id is None

    # Verify hierarchy in DB for v1
    node_v1_4_2 = v1_by_sec["4.2"]
    assert node_v1_4_2.title == "Error Codes"
    assert node_v1_4_2.parent.section_number == "4"

    # 2. Ingest v2 manual with comparison against v1
    v2_doc = ingest_document_version(
        db=db_session,
        pdf_path=V2_PDF,
        document_name="CT-200",
        version_tag="v2.0",
        prior_version_tag="v1.0"
    )

    assert v2_doc is not None
    assert v2_doc.version_tag == "v2.0"
    assert v2_doc.status == VersionStatus.PARSED.value
    assert v2_doc.total_pages == 7
    assert v2_doc.total_nodes == 29

    # Query v2 nodes from DB
    v2_nodes = db_session.query(Node).filter_by(version_id=v2_doc.id).all()
    assert len(v2_nodes) == 29
    v2_by_sec = {n.section_number: n for n in v2_nodes if n.section_number}

    # 3. REQUIREMENT ASSERTION: Section 4.2 is flagged as MODIFIED
    node_v2_4_2 = v2_by_sec.get("4.2")
    assert node_v2_4_2 is not None, "Section 4.2 must exist in v2"
    assert node_v2_4_2.change_status == ChangeStatus.MODIFIED.value, (
        f"Section 4.2 should be MODIFIED, got {node_v2_4_2.change_status}"
    )
    assert node_v2_4_2.linked_node_id == node_v1_4_2.id, (
        "Section 4.2 in v2 must link to Section 4.2 in v1"
    )
    assert node_v2_4_2.content_hash != node_v1_4_2.content_hash, (
        "Content hash of 4.2 must differ between v1 (6 error codes) and v2 (7 error codes)"
    )
    assert node_v2_4_2.similarity_score is not None
    assert 0.0 < node_v2_4_2.similarity_score < 1.0

    # 4. REQUIREMENT ASSERTION: Section 5.3 is flagged as ADDED
    node_v2_5_3 = v2_by_sec.get("5.3")
    assert node_v2_5_3 is not None, "Section 5.3 must exist in v2"
    assert node_v2_5_3.change_status == ChangeStatus.ADDED.value, (
        f"Section 5.3 should be ADDED, got {node_v2_5_3.change_status}"
    )
    assert node_v2_5_3.linked_node_id is None, (
        "Newly ADDED Section 5.3 should have no linked prior node"
    )
    assert node_v2_5_3.parent.section_number == "5", (
        "Section 5.3 must be attached under Section 5 Data Management"
    )

    # 5. Additional check: Section 2.1.1.1 (Battery life changed) is MODIFIED
    node_v1_2_1_1_1 = v1_by_sec["2.1.1.1"]
    node_v2_2_1_1_1 = v2_by_sec["2.1.1.1"]
    assert node_v2_2_1_1_1.change_status == ChangeStatus.MODIFIED.value
    assert node_v2_2_1_1_1.linked_node_id == node_v1_2_1_1_1.id

    # 6. Additional check: Section 1.1 (Intended Use) is UNCHANGED
    node_v1_1_1 = v1_by_sec["1.1"]
    node_v2_1_1 = v2_by_sec["1.1"]
    assert node_v2_1_1.change_status == ChangeStatus.UNCHANGED.value
    assert node_v2_1_1.linked_node_id == node_v1_1_1.id
    assert node_v2_1_1.content_hash == node_v1_1_1.content_hash
    assert node_v2_1_1.similarity_score == 1.0

    # 7. Check sibling order indices and parent-child preservation
    parent_v2_sec_3 = v2_by_sec["3"]
    children_v2_sec_3 = [c for c in parent_v2_sec_3.children]
    assert len(children_v2_sec_3) == 4  # 3.1, 3.2, 3.4, 3.3
    # Check sequential order_index
    order_indices = [c.order_index for c in children_v2_sec_3]
    assert sorted(order_indices) == list(range(len(children_v2_sec_3)))

    # 8. Check diff summary service
    diff_summary = get_version_diff_summary(db=db_session, version_id=v2_doc.id)
    assert diff_summary["version_tag"] == "v2.0"
    assert diff_summary["total_nodes"] == 29
    assert diff_summary["added_count"] == 1
    assert diff_summary["modified_count"] >= 4
    assert any(m["section"] == "4.2" for m in diff_summary["modified_sections"])
    assert any(a["section"] == "5.3" for a in diff_summary["added_sections"])
