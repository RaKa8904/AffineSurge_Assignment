"""Unit tests for LLM Test Case Generation, Retry Strategy, and Retrieval with Staleness Detection.
"""

from pathlib import Path
import pytest
from app.models.node import Node
from app.models.selection import Selection, SelectionNode
from app.services.llm_generator import (
    generate_test_cases_with_retry,
    MockLangChainLLM,
    STALENESS_LIMITATION_NOTE,
    get_json_store_dir,
)
from app.schemas.test_case import QATestCase, QATestCaseSuite


def test_llm_retry_strategy_recovers_from_malformed_output(db_session, seeded_db):
    """Verify that generate_test_cases_with_retry retries up to 3 times on malformed output
    and recovers gracefully when valid output is returned on attempt 3.
    """
    v1 = seeded_db["v1"]
    n1 = db_session.query(Node).filter(Node.version_id == v1.id, Node.section_number == "4.1").first()
    assert n1 is not None

    selection = Selection(
        version_id=v1.id,
        title="Overpressure Safety Suite",
    )
    db_session.add(selection)
    db_session.flush()

    item = SelectionNode(
        selection_id=selection.id,
        node_id=n1.id,
        pinned_version_id=v1.id,
        pinned_content_hash=n1.content_hash,
    )
    db_session.add(item)
    db_session.commit()

    # 1. Attempt 1: Malformed broken JSON string
    # 2. Attempt 2: Schema validation failure (missing steps and expected_result)
    # 3. Attempt 3: Valid 3 test cases
    mock_responses = [
        "THIS IS NOT VALID JSON {broken",
        {"test_cases": [{"title": "Missing fields"}]},
        {
            "test_cases": [
                {
                    "title": "TC-01: Rapid Pressure Surge",
                    "steps": ["Step 1: Surge above 300 mmHg"],
                    "expected_result": "Deflates within 2 seconds"
                },
                {
                    "title": "TC-02: Sensor Fault Disconnect",
                    "steps": ["Step 1: Disconnect sensor line"],
                    "expected_result": "Displays E1 error"
                },
                {
                    "title": "TC-03: Steady Inflation Limits",
                    "steps": ["Step 1: Run steady inflation"],
                    "expected_result": "Reaches target systolic pressure safely"
                }
            ]
        }
    ]

    mock_llm = MockLangChainLLM(responses=mock_responses)
    suite, retries_used = generate_test_cases_with_retry(
        selection=selection,
        llm_callable=mock_llm,
        max_retries=3
    )

    assert suite is not None
    assert len(suite.test_cases) == 3
    assert suite.test_cases[0].title == "TC-01: Rapid Pressure Surge"
    assert retries_used == 2  # Failed attempt 1 & 2, succeeded on attempt 3


def test_llm_retry_strategy_fails_gracefully_after_exhaustion(db_session, seeded_db):
    """Verify that when all 3 attempts fail with malformed output,
    generate_test_cases_with_retry fails gracefully with a descriptive RuntimeError.
    """
    v1 = seeded_db["v1"]
    n1 = db_session.query(Node).filter(Node.version_id == v1.id, Node.section_number == "1.1").first()

    selection = Selection(version_id=v1.id, title="Intended Use Suite")
    db_session.add(selection)
    db_session.flush()

    item = SelectionNode(
        selection_id=selection.id,
        node_id=n1.id,
        pinned_version_id=v1.id,
        pinned_content_hash=n1.content_hash,
    )
    db_session.add(item)
    db_session.commit()

    # Persistent malformed responses
    mock_llm = MockLangChainLLM(responses=["Broken JSON 1", "Broken JSON 2", "Broken JSON 3"])

    with pytest.raises(RuntimeError) as exc_info:
        generate_test_cases_with_retry(selection=selection, llm_callable=mock_llm, max_retries=3)

    assert "Failed to generate valid QA test cases after 3 attempts" in str(exc_info.value)


def test_api_generate_and_duplicate_cache_policy(client, seeded_db):
    """Verify POST /api/v1/selections/{selection_id}/generate:
    1. Generates 3-5 QA test cases and saves to JSON store.
    2. Second call returns cached result immediately (from_cache=True) saving LLM costs.
    3. Call with force_regenerate=true bypasses cache.
    """
    db = seeded_db["session"]
    v1 = seeded_db["v1"]

    n1 = db.query(Node).filter(Node.version_id == v1.id, Node.section_number == "3.1").first()
    assert n1 is not None

    sel_res = client.post("/api/v1/selections", json={
        "version_id": v1.id,
        "title": "Device Operation Powering On Suite",
        "node_ids": [n1.id]
    })
    assert sel_res.status_code == 201
    selection_id = sel_res.json()["id"]

    # 1. Initial generation
    gen_res = client.post(f"/api/v1/selections/{selection_id}/generate")
    assert gen_res.status_code == 200
    gen_data = gen_res.json()

    assert gen_data["selection_id"] == selection_id
    assert 3 <= gen_data["test_case_count"] <= 5
    assert not gen_data["from_cache"]

    # Verify each test case has title, steps, expected_result
    for tc in gen_data["test_cases"]:
        assert "title" in tc and len(tc["title"]) > 0
        assert "steps" in tc and len(tc["steps"]) > 0
        assert "expected_result" in tc and len(tc["expected_result"]) > 0

    # Verify file saved to local JSON store
    store_file = get_json_store_dir() / f"{selection_id}.json"
    assert store_file.exists(), f"JSON store file should exist at: {store_file}"

    # 2. Duplicate Policy: Subsequent call returns cached data
    dup_res = client.post(f"/api/v1/selections/{selection_id}/generate")
    assert dup_res.status_code == 200
    dup_data = dup_res.json()
    assert dup_data["from_cache"] is True
    assert dup_data["test_case_count"] == gen_data["test_case_count"]

    # 3. Force regeneration
    force_res = client.post(f"/api/v1/selections/{selection_id}/generate?force_regenerate=true")
    assert force_res.status_code == 200
    force_data = force_res.json()
    assert force_data["from_cache"] is False


def test_api_staleness_detection_on_modified_node(client, seeded_db):
    """Verify GET /api/v1/test-cases/{selection_id} detects staleness:
    1. Create selection on v1 node 4.2 (Error Codes) where v2 modified content (added E6).
    2. Generate test cases against v1 baseline.
    3. Retrieve test cases: asserts is_stale == True and limitation note is documented.
    """
    db = seeded_db["session"]
    v1 = seeded_db["v1"]

    node_v1_4_2 = db.query(Node).filter(Node.version_id == v1.id, Node.section_number == "4.2").first()
    assert node_v1_4_2 is not None

    # Create selection on v1 node 4.2
    sel_res = client.post("/api/v1/selections", json={
        "version_id": v1.id,
        "title": "Error Handling Safety Suite",
        "node_ids": [node_v1_4_2.id]
    })
    selection_id = sel_res.json()["id"]

    # Generate test cases against v1
    client.post(f"/api/v1/selections/{selection_id}/generate")

    # Retrieval API with Staleness Check
    retrieval_res = client.get(f"/api/v1/test-cases/{selection_id}")
    assert retrieval_res.status_code == 200
    report = retrieval_res.json()

    assert report["selection_id"] == selection_id
    assert report["selection_version_tag"] == "v1.0"
    assert report["latest_version_tag"] == "v2.0"

    # REQUIREMENT ASSERTION: Must flag is_stale == True
    assert report["is_stale"] is True, "Section 4.2 changed in v2; test cases must be flagged as STALE"
    assert report["staleness_reason"] is not None
    assert "modified" in report["staleness_reason"].lower()

    # Per-node staleness audit
    node_staleness = report["node_staleness"][0]
    assert node_staleness["section_number"] == "4.2"
    assert node_staleness["is_stale"] is True
    assert node_staleness["pinned_content_hash"] != node_staleness["latest_content_hash"]

    # REQUIREMENT ASSERTION: Explicitly documents staleness limit
    assert "A 1-word typo fix triggers the exact same staleness flag as a critical threshold change" in report["limitation_note"]


def test_api_staleness_detection_on_unchanged_node(client, seeded_db):
    """Verify that an unchanged node (e.g. Section 1.1 Intended Use) is flagged as is_stale == False."""
    db = seeded_db["session"]
    v1 = seeded_db["v1"]

    node_v1_1_1 = db.query(Node).filter(Node.version_id == v1.id, Node.section_number == "1.1").first()
    assert node_v1_1_1 is not None

    sel_res = client.post("/api/v1/selections", json={
        "version_id": v1.id,
        "title": "Intended Use Baseline",
        "node_ids": [node_v1_1_1.id]
    })
    selection_id = sel_res.json()["id"]

    client.post(f"/api/v1/selections/{selection_id}/generate")

    retrieval_res = client.get(f"/api/v1/test-cases/{selection_id}")
    assert retrieval_res.status_code == 200
    report = retrieval_res.json()

    # REQUIREMENT ASSERTION: Unchanged node should NOT be stale
    assert report["is_stale"] is False
    assert report["node_staleness"][0]["is_stale"] is False
    assert report["node_staleness"][0]["pinned_content_hash"] == report["node_staleness"][0]["latest_content_hash"]
