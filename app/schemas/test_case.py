"""Pydantic schemas for LLM Test Case Generation and Staleness Verification.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from app.models.test_case import TestCaseType


class TestCaseBase(BaseModel):
    __test__ = False
    test_title: str
    test_description: str
    test_type: TestCaseType = TestCaseType.FUNCTIONAL
    preconditions: Optional[str] = None
    steps: List[str] = Field(default_factory=list)
    expected_result: str


class TestCaseResponse(TestCaseBase):
    __test__ = False
    id: str
    node_id: str
    version_id: str
    selection_id: Optional[str] = None
    source_content_hash: str
    is_stale: bool
    staleness_reason: Optional[str] = None
    raw_llm_output: Optional[Dict[str, Any]] = None
    generation_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestCaseGenerateRequest(BaseModel):
    __test__ = False
    node_id: str = Field(..., description="ID of the node to generate QA test cases for")
    prompt_customization: Optional[str] = None
    test_count: int = Field(default=3, ge=1, le=10, description="Number of test case ideas (3-5)")


class StalenessCheckResult(BaseModel):
    test_case_id: str
    node_id: str
    is_stale: bool
    source_content_hash: str
    current_content_hash: Optional[str] = None
    staleness_reason: Optional[str] = None
