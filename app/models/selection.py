"""SQLAlchemy models for Selection and Version-Pinned Selection Items.
"""

import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship
from app.database import Base


class Selection(Base):
    """Represents a curated selection of document nodes pinned to a specific version
    for review, audit, or QA test case generation.
    """
    __tablename__ = "selections"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
        doc="Unique UUID for this selection"
    )
    version_id = Column(
        String(36),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Target document version this selection is based upon"
    )
    title = Column(
        String(255),
        nullable=False,
        doc="Human-readable title for the selection (e.g. 'Safety Critical Modules')"
    )
    description = Column(
        Text,
        nullable=True,
        doc="Detailed rationale or scope of this selection"
    )
    created_by = Column(
        String(100),
        nullable=False,
        default="system",
        doc="User or agent identifier who created the selection"
    )
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
        back_populates="selections",
        foreign_keys=[version_id]
    )
    items = relationship(
        "SelectionNode",
        back_populates="selection",
        cascade="all, delete-orphan",
        order_by="SelectionNode.order_index"
    )

    def __repr__(self) -> str:
        return f"<Selection(id={self.id}, title='{self.title}', version_id='{self.version_id}')>"


class SelectionNode(Base):
    """Junction table linking a Selection to a Node, with version pinning
    and snapshot content hash preservation.
    """
    __tablename__ = "selection_nodes"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True
    )
    selection_id = Column(
        String(36),
        ForeignKey("selections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    node_id = Column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    pinned_version_id = Column(
        String(36),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Explicit version ID pinned at the time of selection"
    )
    pinned_content_hash = Column(
        String(64),
        nullable=False,
        doc="Snapshot of the node content_hash at selection time"
    )
    order_index = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Ordering of the node within this selection"
    )
    notes = Column(
        Text,
        nullable=True,
        doc="Specific testing or QA notes for this pinned node"
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    selection = relationship(
        "Selection",
        back_populates="items",
        foreign_keys=[selection_id]
    )
    node = relationship(
        "Node",
        back_populates="selection_items",
        foreign_keys=[node_id]
    )
    pinned_version = relationship(
        "DocumentVersion",
        foreign_keys=[pinned_version_id]
    )

    __table_args__ = (
        UniqueConstraint("selection_id", "node_id", name="uq_selection_node_item"),
    )

    def __repr__(self) -> str:
        return f"<SelectionNode(selection_id={self.selection_id}, node_id={self.node_id})>"
