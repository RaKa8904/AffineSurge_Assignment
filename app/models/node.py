"""SQLAlchemy model for Hierarchical Document Tree Nodes.
"""

from enum import Enum
import hashlib
import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    DateTime,
    JSON,
    ForeignKey,
    func,
)
from sqlalchemy.orm import relationship
from app.database import Base


class NodeType(str, Enum):
    """Semantic type of a node in the document hierarchy."""
    DOCUMENT_ROOT = "DOCUMENT_ROOT"
    SECTION = "SECTION"
    HEADING_1 = "HEADING_1"
    HEADING_2 = "HEADING_2"
    HEADING_3 = "HEADING_3"
    PARAGRAPH = "PARAGRAPH"
    TABLE = "TABLE"
    LIST_ITEM = "LIST_ITEM"
    WARNING = "WARNING"
    NOTE = "NOTE"


class ChangeStatus(str, Enum):
    """Versioning diff status relative to previous version."""
    UNCHANGED = "UNCHANGED"   # Exact or semantically identical node
    MODIFIED = "MODIFIED"     # Node exists in both versions but text/specs changed
    ADDED = "ADDED"           # Brand-new node introduced in this version
    REMOVED = "REMOVED"       # Existed in previous version, deprecated/deleted


class Node(Base):
    """Represents a discrete structural unit (heading, section, paragraph, table)
    in the document's hierarchical tree.
    """
    __tablename__ = "nodes"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
        doc="Unique UUID for this node"
    )
    version_id = Column(
        String(36),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent document version this node belongs to"
    )
    parent_id = Column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        doc="Parent node in the hierarchy (null for root/top-level)"
    )
    linked_node_id = Column(
        String(36),
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Pointer to corresponding node in previous document version"
    )

    # Classification & Identifiers
    node_type = Column(
        String(50),
        nullable=False,
        default=NodeType.PARAGRAPH.value,
        index=True,
        doc="Structural semantic type"
    )
    title = Column(
        String(512),
        nullable=True,
        doc="Heading text, table caption, or section title"
    )
    section_number = Column(
        String(50),
        nullable=True,
        index=True,
        doc="Hierarchical section numbering (e.g. '1.1', '2.3.1')"
    )

    # Content & Integrity
    content = Column(
        Text,
        nullable=False,
        doc="Textual content, markdown representation, or table data"
    )
    content_hash = Column(
        String(64),
        nullable=False,
        index=True,
        doc="SHA-256 hash of canonicalized content and metadata"
    )

    # Hierarchy & Ordering
    depth = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Depth level in the hierarchy (0=root, 1=H1, 2=H2, etc.)"
    )
    order_index = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Sibling order index within the parent"
    )
    hierarchical_path = Column(
        String(512),
        nullable=True,
        index=True,
        doc="Materialized path (e.g. '/root/1/1.1') for fast subtree queries"
    )

    # Document Geometry & Source Provenance
    page_number = Column(
        Integer,
        nullable=True,
        doc="Page number in original PDF manual (1-indexed)"
    )
    bbox_json = Column(
        JSON,
        nullable=True,
        doc="Bounding box coordinates [x0, y0, x1, y1] on the PDF page"
    )
    table_data = Column(
        JSON,
        nullable=True,
        doc="Structured matrix/rows if node_type is TABLE"
    )

    # Versioning & Change Tracking
    change_status = Column(
        String(50),
        nullable=False,
        default=ChangeStatus.UNCHANGED.value,
        index=True,
        doc="Diff status relative to preceding version"
    )
    similarity_score = Column(
        Float,
        nullable=True,
        doc="Semantic or lexical similarity score with linked_node (0.0 - 1.0)"
    )
    change_summary = Column(
        Text,
        nullable=True,
        doc="Human or LLM generated summary of differences between versions"
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    version = relationship(
        "DocumentVersion",
        back_populates="nodes",
        foreign_keys=[version_id]
    )
    parent = relationship(
        "Node",
        remote_side=[id],
        back_populates="children",
        foreign_keys=[parent_id]
    )
    children = relationship(
        "Node",
        back_populates="parent",
        cascade="all, delete-orphan",
        foreign_keys=[parent_id],
        order_by="Node.order_index"
    )
    linked_node = relationship(
        "Node",
        remote_side=[id],
        foreign_keys=[linked_node_id],
        post_update=True
    )
    selection_items = relationship(
        "SelectionNode",
        back_populates="node",
        cascade="all, delete-orphan",
        foreign_keys="SelectionNode.node_id"
    )
    test_cases = relationship(
        "TestCase",
        back_populates="node",
        cascade="all, delete-orphan",
        foreign_keys="TestCase.node_id"
    )

    @staticmethod
    def calculate_content_hash(
        content: str,
        title: str | None = None,
        node_type: str | None = None,
        section_number: str | None = None
    ) -> str:
        """Compute canonical SHA-256 hash for node content.
        Normalizes whitespace and standardizes components to ensure stable hashing.
        """
        normalized_content = " ".join((content or "").split())
        normalized_title = " ".join((title or "").split()) if title else ""
        normalized_type = (node_type or "").strip().upper()
        normalized_section = (section_number or "").strip()

        payload = f"{normalized_section}|{normalized_type}|{normalized_title}|{normalized_content}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def update_hash(self) -> str:
        """Recompute and assign the content_hash based on current fields."""
        self.content_hash = self.calculate_content_hash(
            content=self.content,
            title=self.title,
            node_type=self.node_type,
            section_number=self.section_number
        )
        return self.content_hash

    def __repr__(self) -> str:
        return (
            f"<Node(id={self.id}, type='{self.node_type}', "
            f"section='{self.section_number}', title='{self.title[:30] if self.title else ''}', "
            f"status='{self.change_status}')>"
        )
