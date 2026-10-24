"""Unit tests for SQLAlchemy database models: Version, Node, Selection, TestCase.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from app.models.version import DocumentVersion, VersionStatus
from app.models.node import Node, NodeType, ChangeStatus
from app.models.selection import Selection, SelectionNode
from app.models.test_case import TestCase, TestCaseType


def test_document_version_creation(db_session):
    """Verify DocumentVersion can be created with default values and queried."""
    version = DocumentVersion(
        document_name="CT-200",
        version_tag="v1.0",
        file_name="ct200_manual.pdf",
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        status=VersionStatus.PARSED.value,
        total_pages=6,
        total_nodes=42,
        metadata_json={"extractor": "pdf_text_parser", "ocr_enabled": False}
    )
    db_session.add(version)
    db_session.commit()

    retrieved = db_session.query(DocumentVersion).filter_by(version_tag="v1.0").first()
    assert retrieved is not None
    assert retrieved.id is not None
    assert retrieved.document_name == "CT-200"
    assert retrieved.total_pages == 6
    assert retrieved.metadata_json["extractor"] == "pdf_text_parser"


def test_document_version_unique_constraint(db_session):
    """Verify (document_name, version_tag) unique constraint prevents duplicate versions."""
    v1 = DocumentVersion(document_name="CT-200", version_tag="v1.0")
    db_session.add(v1)
    db_session.commit()

    v1_dup = DocumentVersion(document_name="CT-200", version_tag="v1.0")
    db_session.add(v1_dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_node_tree_hierarchy_and_cascade(db_session):
    """Verify hierarchical parent-child relationships and cascade delete on nodes."""
    version = DocumentVersion(document_name="CT-200", version_tag="v1.0")
    db_session.add(version)
    db_session.flush()

    # Root section
    root = Node(
        version_id=version.id,
        node_type=NodeType.DOCUMENT_ROOT.value,
        title="CardioTrack CT-200 Manual",
        content="Document root container",
        depth=0,
        order_index=0
    )
    root.update_hash()
    db_session.add(root)
    db_session.flush()

    # Section 1 Heading
    h1 = Node(
        version_id=version.id,
        parent_id=root.id,
        node_type=NodeType.HEADING_1.value,
        section_number="1.0",
        title="1. Device Overview",
        content="1. Device Overview",
        depth=1,
        order_index=0
    )
    h1.update_hash()
    db_session.add(h1)
    db_session.flush()

    # Paragraph under Section 1
    p1 = Node(
        version_id=version.id,
        parent_id=h1.id,
        node_type=NodeType.PARAGRAPH.value,
        content="The CardioTrack CT-200 is an oscillometric, upper-arm blood pressure monitor.",
        depth=2,
        order_index=0,
        page_number=1
    )
    p1.update_hash()
    db_session.add(p1)
    db_session.commit()

    # Test relationships
    assert len(root.children) == 1
    assert root.children[0].title == "1. Device Overview"
    assert len(h1.children) == 1
    assert "oscillometric" in h1.children[0].content

    # Test cascade delete: deleting root should delete h1 and p1
    db_session.delete(root)
    db_session.commit()

    remaining_nodes = db_session.query(Node).all()
    assert len(remaining_nodes) == 0


def test_node_content_hash_determinism():
    """Verify that calculate_content_hash normalizes whitespace and produces deterministic SHA-256."""
    text_a = "  The CT-200 measures systolic \n  and diastolic pressure.  "
    text_b = "The CT-200 measures systolic and diastolic pressure."

    hash_a = Node.calculate_content_hash(
        content=text_a,
        title="Overview",
        node_type=NodeType.PARAGRAPH.value,
        section_number="1.0"
    )
    hash_b = Node.calculate_content_hash(
        content=text_b,
        title="Overview",
        node_type=NodeType.PARAGRAPH.value,
        section_number="1.0"
    )
    assert hash_a == hash_b
    assert len(hash_a) == 64  # Valid SHA-256 hex string


def test_version_linking_and_change_status(db_session):
    """Verify cross-version node linking from v2 to v1 with change_status."""
    v1 = DocumentVersion(document_name="CT-200", version_tag="v1.0")
    v2 = DocumentVersion(document_name="CT-200", version_tag="v2.0")
    db_session.add_all([v1, v2])
    db_session.flush()

    # v1 node
    node_v1 = Node(
        version_id=v1.id,
        node_type=NodeType.PARAGRAPH.value,
        section_number="1.1",
        title="Intended Use",
        content="Arm circumference 22-42 cm.",
        change_status=ChangeStatus.UNCHANGED.value
    )
    node_v1.update_hash()
    db_session.add(node_v1)
    db_session.flush()

    # v2 node modified
    node_v2 = Node(
        version_id=v2.id,
        linked_node_id=node_v1.id,  # Link to v1
        node_type=NodeType.PARAGRAPH.value,
        section_number="1.1",
        title="Intended Use",
        content="Arm circumference 22-45 cm (extended range).",  # Modified specification
        change_status=ChangeStatus.MODIFIED.value,
        similarity_score=0.88,
        change_summary="Arm circumference specification extended from 42 cm to 45 cm."
    )
    node_v2.update_hash()
    db_session.add(node_v2)
    db_session.commit()

    # Verify link
    queried_v2 = db_session.query(Node).filter_by(id=node_v2.id).first()
    assert queried_v2.linked_node_id == node_v1.id
    assert queried_v2.linked_node.content == "Arm circumference 22-42 cm."
    assert queried_v2.change_status == ChangeStatus.MODIFIED.value
    assert queried_v2.content_hash != node_v1.content_hash


def test_selection_and_version_pinning(db_session):
    """Verify Selection model pins specific node IDs with snapshot content hashes."""
    v1 = DocumentVersion(document_name="CT-200", version_tag="v1.0")
    db_session.add(v1)
    db_session.flush()

    node = Node(
        version_id=v1.id,
        node_type=NodeType.WARNING.value,
        section_number="2.1",
        title="Contraindications",
        content="Do not use on neonates or pregnant patients.",
    )
    node.update_hash()
    db_session.add(node)
    db_session.flush()

    # Create selection
    selection = Selection(
        version_id=v1.id,
        title="Safety & Contraindications QA Suite",
        description="Verify all safety warnings generate compliant test cases",
        created_by="lead_qa"
    )
    db_session.add(selection)
    db_session.flush()

    # Pin node to selection
    selection_item = SelectionNode(
        selection_id=selection.id,
        node_id=node.id,
        pinned_version_id=v1.id,
        pinned_content_hash=node.content_hash,
        notes="High severity safety audit requirement"
    )
    db_session.add(selection_item)
    db_session.commit()

    # Verify retrieval and pinning
    saved_selection = db_session.query(Selection).filter_by(id=selection.id).first()
    assert len(saved_selection.items) == 1
    assert saved_selection.items[0].node_id == node.id
    assert saved_selection.items[0].pinned_content_hash == node.content_hash
    assert saved_selection.items[0].pinned_version_id == v1.id


def test_selection_duplicate_node_prevention(db_session):
    """Verify unique constraint prevents pinning the same node twice in a single selection."""
    v1 = DocumentVersion(document_name="CT-200", version_tag="v1.0")
    db_session.add(v1)
    db_session.flush()

    node = Node(
        version_id=v1.id,
        node_type=NodeType.PARAGRAPH.value,
        content="Battery life test specification."
    )
    node.update_hash()
    db_session.add(node)
    db_session.flush()

    selection = Selection(version_id=v1.id, title="Battery Suite")
    db_session.add(selection)
    db_session.flush()

    item1 = SelectionNode(
        selection_id=selection.id,
        node_id=node.id,
        pinned_version_id=v1.id,
        pinned_content_hash=node.content_hash
    )
    db_session.add(item1)
    db_session.commit()

    item2 = SelectionNode(
        selection_id=selection.id,
        node_id=node.id,
        pinned_version_id=v1.id,
        pinned_content_hash=node.content_hash
    )
    db_session.add(item2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_test_case_model_and_staleness_tracking(db_session):
    """Verify TestCase model links to node and tracks source content hash for staleness."""
    v1 = DocumentVersion(document_name="CT-200", version_tag="v1.0")
    db_session.add(v1)
    db_session.flush()

    node = Node(
        version_id=v1.id,
        node_type=NodeType.PARAGRAPH.value,
        section_number="3.2",
        title="Battery Indicator",
        content="Low battery icon flashes when voltage drops below 4.2V."
    )
    node.update_hash()
    db_session.add(node)
    db_session.flush()

    # Generate test case
    tc = TestCase(
        node_id=node.id,
        version_id=v1.id,
        test_title="Verify Low Battery Warning at 4.2V",
        test_description="Check that battery indicator icon flashes when power supply is set to 4.19V",
        test_type=TestCaseType.SAFETY.value,
        preconditions="Connected to programmable DC power supply",
        steps_json=["Set DC voltage to 4.5V (normal)", "Decrease voltage to 4.19V", "Observe LCD display"],
        expected_result="Low battery indicator flashes within 1.0s",
        source_content_hash=node.content_hash,
        is_stale=False
    )
    db_session.add(tc)
    db_session.commit()

    retrieved_tc = db_session.query(TestCase).filter_by(node_id=node.id).first()
    assert retrieved_tc is not None
    assert retrieved_tc.source_content_hash == node.content_hash
    assert not retrieved_tc.is_stale
