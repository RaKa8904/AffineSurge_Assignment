"""SQLAlchemy model for Generated QA Test Cases and Staleness Tracking.
"""

from enum import Enum
import uuid
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Text,
    DateTime,
    JSON,
    ForeignKey,
    func,
)
from sqlalchemy.orm import relationship
from app.database import Base


class TestCaseType(str, Enum):
    """Category of generated QA test case."""
    __test__ = False
    FUNCTIONAL = "FUNCTIONAL"
    BOUNDARY = "BOUNDARY"
    SAFETY = "SAFETY"
    NEGATIVE = "NEGATIVE"
    PERFORMANCE = "PERFORMANCE"
    REGULATORY = "REGULATORY"


class TestCase(Base):
    """Represents an LLM-generated QA test case linked to a specific node,
    preserving the source content hash for staleness verification.
    """
    __tablename__ = "test_cases"
    __test__ = False

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
        doc="Unique UUID for this test case"
    )
    node_id = Column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Exact node from which this test case was generated"
    )
    version_id = Column(
        String(36),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Document version at generation time"
    )
    selection_id = Column(
        String(36),
        ForeignKey("selections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Optional selection session that triggered the generation"
    )

    # Test Case Details
    test_title = Column(
        String(255),
        nullable=False,
        doc="Concise title of the QA test case"
    )
    test_description = Column(
        Text,
        nullable=False,
        doc="Objective and scope of the test case"
    )
    test_type = Column(
        String(50),
        nullable=False,
        default=TestCaseType.FUNCTIONAL.value,
        index=True,
        doc="Test category (e.g. SAFETY, FUNCTIONAL, BOUNDARY)"
    )
    preconditions = Column(
        Text,
        nullable=True,
        doc="Setup conditions required before executing the test"
    )
    steps_json = Column(
        JSON,
        nullable=False,
        default=list,
        doc="Ordered list of step-by-step instructions"
    )
    expected_result = Column(
        Text,
        nullable=False,
        doc="Expected pass outcome according to manual specification"
    )

    # Staleness Detection Fields
    source_content_hash = Column(
        String(64),
        nullable=False,
        index=True,
        doc="Snapshot of the node content_hash when this test case was generated"
    )
    is_stale = Column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        doc="Flag indicating whether underlying node text has diverged"
    )
    staleness_reason = Column(
        String(255),
        nullable=True,
        doc="Explanation if flagged as stale (e.g. 'Node content modified in v2.0')"
    )

    # Raw Payload & Diagnostics
    raw_llm_output = Column(
        JSON,
        nullable=True,
        doc="Full raw LLM response payload (for auditing and JSON store sync)"
    )
    generation_metadata = Column(
        JSON,
        nullable=True,
        doc="LLM model, prompt version, token usage, latency"
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
    node = relationship(
        "Node",
        back_populates="test_cases",
        foreign_keys=[node_id]
    )
    version = relationship(
        "DocumentVersion",
        back_populates="test_cases",
        foreign_keys=[version_id]
    )
    selection = relationship(
        "Selection",
        foreign_keys=[selection_id]
    )

    def __repr__(self) -> str:
        return f"<TestCase(id={self.id}, title='{self.test_title[:30]}', stale={self.is_stale})>"
