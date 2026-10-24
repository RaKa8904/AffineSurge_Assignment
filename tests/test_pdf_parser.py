"""Unit tests for PDF document ingestion, hierarchical tree parsing, and edge cases.
"""

from pathlib import Path
import pytest
from app.services.pdf_parser import parse_pdf_to_tree, compute_body_hash

V1_PDF = Path("ct200_manual.pdf")
V2_PDF = Path("ct200_manual_v2.pdf")


@pytest.fixture(scope="module")
def parsed_v1_tree():
    """Parses CT-200 v1 PDF once for the test module."""
    assert V1_PDF.exists(), f"Missing test manual: {V1_PDF}"
    return parse_pdf_to_tree(V1_PDF, document_name="CardioTrack CT-200")


@pytest.fixture(scope="module")
def parsed_v2_tree():
    """Parses CT-200 v2 PDF once for the test module."""
    assert V2_PDF.exists(), f"Missing test manual: {V2_PDF}"
    return parse_pdf_to_tree(V2_PDF, document_name="CardioTrack CT-200 v2")


def test_edge_case_irregular_hierarchy(parsed_v1_tree):
    """EDGE CASE 1: Irregular hierarchy.
    Verify that '2.1.1.1 Battery Life Under Typical Use' correctly attaches directly
    to '2.1 General Specifications', handling skipped intermediate levels (e.g. 2.1.1).
    """
    node_2_1 = parsed_v1_tree.get_node("2.1")
    assert node_2_1 is not None, "Section 2.1 General Specifications should exist"
    assert node_2_1.title == "General Specifications"

    node_2_1_1_1 = parsed_v1_tree.get_node("2.1.1.1")
    assert node_2_1_1_1 is not None, "Section 2.1.1.1 Battery Life should exist"
    assert "Battery Life" in node_2_1_1_1.title
    assert node_2_1_1_1.level == 4

    # Verify parent relationship jumps intermediate level and connects to 2.1
    assert node_2_1_1_1.parent is not None
    assert node_2_1_1_1.parent.section_number == "2.1"
    assert node_2_1_1_1.parent == node_2_1
    assert node_2_1_1_1 in node_2_1.children

    # Verify 2.1 connects to top-level section 2
    node_2 = parsed_v1_tree.get_node("2")
    assert node_2_1.parent == node_2
    assert node_2.parent == parsed_v1_tree.root


def test_edge_case_out_of_order_sections(parsed_v1_tree):
    """EDGE CASE 2: Out-of-order section numbering.
    Verify that '3.4 Auto Shutoff' (appearing physically before '3.3 Result Display')
    and '3.3 Result Display' both correctly link to their common parent '3. Device Operation'.
    """
    node_3 = parsed_v1_tree.get_node("3")
    assert node_3 is not None, "Section 3 Device Operation must exist"

    node_3_4 = parsed_v1_tree.get_node("3.4")
    node_3_3 = parsed_v1_tree.get_node("3.3")

    assert node_3_4 is not None, "Section 3.4 Auto Shutoff must exist"
    assert node_3_3 is not None, "Section 3.3 Result Display must exist"

    # Both must resolve to parent section 3
    assert node_3_4.parent == node_3, "Section 3.4 parent must be Section 3"
    assert node_3_3.parent == node_3, "Section 3.3 parent must be Section 3"

    # Verify children list of Section 3 contains both
    child_sections = [c.section_number for c in node_3.children]
    assert "3.4" in child_sections
    assert "3.3" in child_sections

    # Document appearance order: 3.4 appears physically before 3.3 in CT-200
    idx_3_4 = child_sections.index("3.4")
    idx_3_3 = child_sections.index("3.3")
    assert idx_3_4 < idx_3_3, "Section 3.4 physically precedes Section 3.3 in document flow"


def test_edge_case_multi_column_table_extraction(parsed_v1_tree, parsed_v2_tree):
    """EDGE CASE 3: Multi-column table extraction.
    Verify that multi-column tables in section 2.1 (General Specifications)
    and section 4.2 (Error Codes) are extracted accurately with structure and content hashes.
    """
    # 1. Section 2.1 Table Check (2 columns: Parameter, Value)
    node_2_1 = parsed_v1_tree.get_node("2.1")
    assert len(node_2_1.tables) >= 1, "Section 2.1 must contain at least 1 table"
    table_2_1 = node_2_1.tables[0]
    assert len(table_2_1[0]) == 2, f"Expected 2 columns in Section 2.1 table, got {len(table_2_1[0])}"
    
    # Check headers and row contents
    headers_2_1 = [c.strip() if c else "" for c in table_2_1[0]]
    assert headers_2_1 == ["Parameter", "Value"]
    
    rows_text_2_1 = " ".join(" ".join(str(c) for c in r) for r in table_2_1)
    assert "Oscillometric" in rows_text_2_1
    assert "Pressure range" in rows_text_2_1
    assert len(node_2_1.content_hash) == 64

    # 2. Section 4.2 Table Check (3 columns: Code, Meaning, Device Behavior)
    node_4_2_v1 = parsed_v1_tree.get_node("4.2")
    assert len(node_4_2_v1.tables) >= 1, "Section 4.2 must contain error code table"
    table_4_2_v1 = node_4_2_v1.tables[0]
    assert len(table_4_2_v1[0]) == 3, f"Expected 3 columns in Section 4.2 table, got {len(table_4_2_v1[0])}"

    headers_4_2 = [c.strip() if c else "" for c in table_4_2_v1[0]]
    assert headers_4_2 == ["Code", "Meaning", "Device Behavior"]

    error_codes_v1 = [r[0].strip() for r in table_4_2_v1[1:] if r and r[0]]
    assert "E1" in error_codes_v1
    assert "E2" in error_codes_v1
    assert "E3" in error_codes_v1
    assert "E4" in error_codes_v1
    assert len(table_4_2_v1) == 6  # Header + E1, E2, E3, E4, E5

    # 3. Verify v2 table modification updates the content hash
    node_4_2_v2 = parsed_v2_tree.get_node("4.2")
    table_4_2_v2 = node_4_2_v2.tables[0]
    assert len(table_4_2_v2) == 7  # Header + E1..E6 (added E6 Bluetooth timeout)
    error_codes_v2 = [r[0].strip() for r in table_4_2_v2[1:] if r and r[0]]
    assert "E6" in error_codes_v2

    # Content hash in v2 must reflect table changes
    assert node_4_2_v1.content_hash != node_4_2_v2.content_hash


def test_body_text_content_hashing():
    """Verify compute_body_hash normalizes whitespace and is strictly deterministic."""
    sample_text_1 = "The CT-200 is   an oscillometric   blood pressure monitor.\n\n"
    sample_text_2 = "The CT-200 is an oscillometric blood pressure monitor."
    sample_text_3 = "The CT-200 is an oscillometric blood pressure monitor with bluetooth."

    hash_1 = compute_body_hash(sample_text_1)
    hash_2 = compute_body_hash(sample_text_2)
    hash_3 = compute_body_hash(sample_text_3)

    assert hash_1 == hash_2, "Whitespace differences must produce identical canonical hashes"
    assert hash_1 != hash_3, "Different content must produce distinct hashes"
    assert len(hash_1) == 64
    assert all(c in "0123456789abcdef" for c in hash_1)
