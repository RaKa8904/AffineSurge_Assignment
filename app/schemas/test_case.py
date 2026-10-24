"""Pydantic schemas for LLM Test Case Generation and Staleness Verification.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from app.models.test_case import TestCaseType


class QATestCase(BaseModel):
    """A single QA test case idea with verification steps and expected result."""
    __test__ = False
    title: str = Field(..., description="Action-oriented title of the test case")
    steps: List[str] = Field(..., min_length=1, description="Sequential steps to perform the test")
    expected_result: str = Field(..., description="Expected observable behavior or verification outcome")


class QATestCaseSuite(BaseModel):
    """Collection of 3-5 QA test cases produced by structured LLM generation."""
    __test__ = False
    test_cases: List[QATestCase] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="List of 3 to 5 structured QA test case ideas"
    )


class TestCaseNodeStaleness(BaseModel):
    """Per-node staleness evaluation comparing pinned hash against latest version."""
    __test__ = False
    node_id: str
    section_number: Optional[str] = None
    title: Optional[str] = None
    pinned_version_tag: str
    pinned_content_hash: str
    latest_version_tag: str
    latest_content_hash: Optional[str] = None
    is_stale: bool
    staleness_reason: Optional[str] = None


class TestCaseRetrievalResponse(BaseModel):
    """Full retrieval response containing generated test cases and staleness audit."""
    __test__ = False
    selection_id: str
    selection_title: str
    selection_version_tag: str
    latest_version_tag: str
    is_stale: bool
    staleness_reason: Optional[str] = None
    limitation_note: str = Field(
        default=(
            "Limitation of cryptographic hash staleness detection: A 1-word typo fix "
            "triggers the exact same staleness flag as a critical threshold change."
        ),
        description="Documented boundary of hash-based staleness checking"
    )
    node_staleness: List[TestCaseNodeStaleness] = Field(default_factory=list)
    test_cases: List[QATestCase] = Field(default_factory=list)
    generated_at: datetime
    from_cache: bool = False
    storage_path: Optional[str] = None


class GenerationResponse(BaseModel):
    """Response returned upon successful or cached test case generation."""
    __test__ = False
    selection_id: str
    version_id: str
    version_tag: str
    test_case_count: int
    test_cases: List[QATestCase]
    generated_at: datetime
    from_cache: bool
    storage_path: str
    retry_count: int = 0
