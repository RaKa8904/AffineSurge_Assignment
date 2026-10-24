"""SQLAlchemy model for Document Versions.
"""

from enum import Enum
import uuid
from sqlalchemy import Column, String, Integer, DateTime, JSON, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.database import Base


class VersionStatus(str, Enum):
    """Lifecycle status of a document version."""
    PENDING = "PENDING"
    PARSING = "PARSING"
    PARSED = "PARSED"
    FAILED = "FAILED"


class DocumentVersion(Base):
    """Represents an ingested version of a technical/medical device manual (e.g., CT-200 v1, v2).
    """
    __tablename__ = "document_versions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
        doc="Unique UUID for this version record"
    )
    document_name = Column(
        String(255),
        nullable=False,
        index=True,
        doc="Name/identifier of the medical device (e.g. 'CT-200')"
    )
    version_tag = Column(
        String(50),
        nullable=False,
        index=True,
        doc="Version label (e.g. 'v1.0', 'v2.0')"
    )
    file_name = Column(
        String(255),
        nullable=True,
        doc="Original uploaded PDF filename"
    )
    file_hash = Column(
        String(64),
        nullable=True,
        index=True,
        doc="SHA-256 hash of the uploaded source file"
    )
    status = Column(
        String(30),
        nullable=False,
        default=VersionStatus.PENDING.value,
        index=True,
        doc="Ingestion status"
    )
    total_pages = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Total page count extracted from the manual"
    )
    total_nodes = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Total structured tree nodes parsed"
    )
    metadata_json = Column(
        JSON,
        nullable=True,
        doc="Arbitrary ingestion metadata, parsing stats, or OCR settings"
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Creation timestamp"
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Last updated timestamp"
    )

    # Relationships
    nodes = relationship(
        "Node",
        back_populates="version",
        cascade="all, delete-orphan",
        foreign_keys="Node.version_id",
        order_by="Node.order_index"
    )
    selections = relationship(
        "Selection",
        back_populates="version",
        cascade="all, delete-orphan",
        foreign_keys="Selection.version_id"
    )
    test_cases = relationship(
        "TestCase",
        back_populates="version",
        cascade="all, delete-orphan",
        foreign_keys="TestCase.version_id"
    )

    __table_args__ = (
        UniqueConstraint("document_name", "version_tag", name="uq_doc_version_tag"),
    )

    def __repr__(self) -> str:
        return f"<DocumentVersion(id={self.id}, name='{self.document_name}', version='{self.version_tag}', status='{self.status}')>"
