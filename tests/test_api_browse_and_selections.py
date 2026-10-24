"""Unit tests for Browse API (Versions, Nodes, Search) and Selection API (Pinning, Deduplication).
"""

import pytest
from app.models.node import Node, ChangeStatus


def test_api_list_versions(client, seeded_db):
    """Verify GET /api/v1/versions lists all ingested document versions."""
    response = client.get("/api/v1/versions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2

    version_tags = [v["version_tag"] for v in data]
    assert "v1.0" in version_tags
    assert "v2.0" in version_tags

    v1_entry = next(v for v in data if v["version_tag"] == "v1.0")
    assert v1_entry["document_name"] == "CT-200"
    assert v1_entry["total_nodes"] == 28
    assert v1_entry["total_pages"] == 6


def test_api_browse_top_level_nodes(client, seeded_db):
    """Verify GET /api/v1/nodes defaults to latest version and returns top-level sections with children."""
    # 1. Default (latest version: v2.0)
    response_default = client.get("/api/v1/nodes")
    assert response_default.status_code == 200
    roots_v2 = response_default.json()
    assert len(roots_v2) >= 1
    root_node_v2 = roots_v2[0]
    assert root_node_v2["level"] == 0
    assert "CT-200" in root_node_v2["title"]
    # Check top-level children under root (Sections 1..8)
    assert len(root_node_v2["children"]) == 8
    child_sec_numbers = [c["section_number"] for c in root_node_v2["children"]]
    assert "1" in child_sec_numbers
    assert "2" in child_sec_numbers
    assert "8" in child_sec_numbers

    # 2. Filter by explicit version tag v1.0
    response_v1 = client.get("/api/v1/nodes?version=v1.0")
    assert response_v1.status_code == 200
    roots_v1 = response_v1.json()
    assert len(roots_v1) >= 1
    root_node_v1 = roots_v1[0]
    assert root_node_v1["version_id"] == seeded_db["v1"].id


def test_api_get_node_details_and_diff_summary(client, seeded_db):
    """Verify GET /api/v1/nodes/{node_id} returns full text, children, hash,
    and lightweight diff summary for linked nodes.
    """
    db = seeded_db["session"]
    v2_id = seeded_db["v2"].id

    # 1. Test MODIFIED node: Section 4.2 Error Codes in v2
    node_4_2 = db.query(Node).filter(Node.version_id == v2_id, Node.section_number == "4.2").first()
    assert node_4_2 is not None

    res_4_2 = client.get(f"/api/v1/nodes/{node_4_2.id}")
    assert res_4_2.status_code == 200
    data_4_2 = res_4_2.json()

    assert data_4_2["id"] == node_4_2.id
    assert data_4_2["section_number"] == "4.2"
    assert "Code" in data_4_2["content"]  # Full text includes table
    assert len(data_4_2["content_hash"]) == 64
    assert data_4_2["change_status"] == "MODIFIED"

    # Diff summary assertions
    assert data_4_2["diff_summary"] is not None
    assert data_4_2["diff_summary"]["change_status"] == "MODIFIED"
    assert data_4_2["diff_summary"]["linked_node_id"] == node_4_2.linked_node_id
    assert data_4_2["diff_summary"]["similarity_score"] is not None
    assert "similarity" in data_4_2["diff_summary"]["change_summary"].lower()

    # 2. Test ADDED node: Section 5.3 Data Export in v2
    node_5_3 = db.query(Node).filter(Node.version_id == v2_id, Node.section_number == "5.3").first()
    assert node_5_3 is not None

    res_5_3 = client.get(f"/api/v1/nodes/{node_5_3.id}")
    assert res_5_3.status_code == 200
    data_5_3 = res_5_3.json()

    assert data_5_3["section_number"] == "5.3"
    assert data_5_3["change_status"] == "ADDED"
    assert data_5_3["diff_summary"]["change_status"] == "ADDED"
    assert data_5_3["diff_summary"]["linked_node_id"] is None


def test_api_search_nodes(client, seeded_db):
    """Verify GET /api/v1/nodes/search finds matching headings and body text with snippets."""
    # Search for battery life across all manuals
    res = client.get("/api/v1/nodes/search?q=battery")
    assert res.status_code == 200
    results = res.json()
    assert len(results) > 0

    # Ensure search result contains snippet, title, and content_hash
    first = results[0]
    assert "id" in first
    assert "snippet" in first
    assert "battery" in first["snippet"].lower() or "battery" in (first["title"] or "").lower()
    assert len(first["content_hash"]) == 64

    # Filter search by version tag
    res_v1_only = client.get("/api/v1/nodes/search?q=export&version=v1.0")
    assert res_v1_only.status_code == 200
    assert len(res_v1_only.json()) == 0  # Data Export does not exist in v1

    res_v2_only = client.get("/api/v1/nodes/search?q=export&version=v2.0")
    assert res_v2_only.status_code == 200
    assert len(res_v2_only.json()) > 0
    assert any("export" in (r["title"] or "").lower() for r in res_v2_only.json())


def test_api_create_selection_and_version_pinning(client, seeded_db):
    """Verify POST /api/v1/selections pins node IDs with exact snapshot content hash."""
    db = seeded_db["session"]
    v1 = seeded_db["v1"]

    # Select two nodes from v1: 1.1 Intended Use and 2.1 General Specifications
    n1 = db.query(Node).filter(Node.version_id == v1.id, Node.section_number == "1.1").first()
    n2 = db.query(Node).filter(Node.version_id == v1.id, Node.section_number == "2.1").first()
    assert n1 and n2

    payload = {
        "version_id": v1.id,
        "title": "Clinical Intended Use & Power Baseline",
        "description": "Baseline QA verification for 1.1 and 2.1",
        "node_ids": [n1.id, n2.id]
    }

    response = client.post("/api/v1/selections", json=payload)
    assert response.status_code == 201
    selection_data = response.json()

    assert selection_data["id"] is not None
    assert selection_data["version_id"] == v1.id
    assert selection_data["title"] == "Clinical Intended Use & Power Baseline"
    assert selection_data["total_nodes"] == 2
    assert len(selection_data["items"]) == 2

    # Verify version-pinned snapshot content hashes match the node's exact hash
    item_1 = next(item for item in selection_data["items"] if item["node_id"] == n1.id)
    assert item_1["pinned_content_hash"] == n1.content_hash
    assert item_1["pinned_version_id"] == v1.id

    item_2 = next(item for item in selection_data["items"] if item["node_id"] == n2.id)
    assert item_2["pinned_content_hash"] == n2.content_hash
    assert item_2["pinned_version_id"] == v1.id


def test_api_selection_duplication_policy(client, seeded_db):
    """Verify Selection deduplication policy:
    Submitting the exact same set of node_ids for the same version_id returns the existing selection.
    """
    db = seeded_db["session"]
    v2 = seeded_db["v2"]

    n_4_2 = db.query(Node).filter(Node.version_id == v2.id, Node.section_number == "4.2").first()
    n_5_3 = db.query(Node).filter(Node.version_id == v2.id, Node.section_number == "5.3").first()
    assert n_4_2 and n_5_3

    payload_initial = {
        "version_id": "v2.0",  # Accept tag as well as UUID
        "title": "Safety & Export Suite",
        "node_ids": [n_4_2.id, n_5_3.id]
    }

    # 1. First submission creates selection (201 Created)
    res_1 = client.post("/api/v1/selections", json=payload_initial)
    assert res_1.status_code == 201
    sel_1 = res_1.json()
    sel_id_1 = sel_1["id"]

    # 2. Second submission with identical node_ids (even in different order!)
    payload_duplicate = {
        "version_id": "v2.0",
        "title": "Redundant Attempt With Permuted Order",
        "node_ids": [n_5_3.id, n_4_2.id]
    }

    res_2 = client.post("/api/v1/selections", json=payload_duplicate)
    # Deduplication policy returns existing selection (200 OK or 201 with same ID)
    assert res_2.status_code in [200, 201]
    sel_2 = res_2.json()
    assert sel_2["id"] == sel_id_1, "Duplicate node set must return existing selection_id"

    # 3. Verify total selections in DB for v2 has not duplicated
    res_list = client.get(f"/api/v1/selections?version_id={v2.id}")
    assert res_list.status_code == 200
    v2_selections = [s for s in res_list.json() if s["id"] == sel_id_1]
    assert len(v2_selections) == 1


def test_api_selection_validation_errors(client, seeded_db):
    """Verify 404 for unknown version and 400 for invalid/mismatched node IDs."""
    v1 = seeded_db["v1"]

    # Unknown version ID
    res_bad_ver = client.post("/api/v1/selections", json={
        "version_id": "non-existent-version-uuid",
        "node_ids": ["some-uuid"]
    })
    assert res_bad_ver.status_code == 404

    # Unknown node UUID
    res_bad_node = client.post("/api/v1/selections", json={
        "version_id": v1.id,
        "node_ids": ["00000000-0000-0000-0000-000000000000"]
    })
    assert res_bad_node.status_code == 400
    assert "do not exist in document version" in res_bad_node.json()["detail"]
