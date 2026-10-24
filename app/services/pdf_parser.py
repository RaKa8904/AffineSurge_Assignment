"""PDF hierarchical parsing and tree generation engine using pdfplumber.

Extracts text, multi-column tables, identifies numbered headings via font size/weight
and regex, resolves irregular hierarchies and out-of-order sections, and computes
deterministic body text content hashes.
"""

from __future__ import annotations
import hashlib
from pathlib import Path
import re
from typing import Dict, List, Optional, Any
import uuid

# Ensure ARM64 Windows / pdfminer runtime compatibility
import app.services.pdf_runtime  # noqa: F401
import pdfplumber


HEADING_REGEX = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z].*)$")


def compute_body_hash(body_text: str) -> str:
    """Computes a deterministic SHA-256 hash of the normalized body text.
    Collapses variable whitespace to ensure canonical hashing across formatting differences.
    """
    normalized = " ".join((body_text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_file_sha256(file_path: Path | str) -> str:
    """Computes the SHA-256 checksum of the raw PDF file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def table_to_markdown(table_rows: List[List[Optional[str]]]) -> str:
    """Converts a 2D matrix of table cells into clean GitHub-flavored Markdown."""
    if not table_rows or not table_rows[0]:
        return ""
    
    cleaned_rows: List[List[str]] = []
    for row in table_rows:
        cleaned_rows.append([" ".join((cell or "").split()) for cell in row])
        
    headers = cleaned_rows[0]
    separator = ["---"] * len(headers)
    
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(separator) + " |"
    ]
    for row in cleaned_rows[1:]:
        # Ensure row matches header length
        padded_row = row + [""] * max(0, len(headers) - len(row))
        lines.append("| " + " | ".join(padded_row[:len(headers)]) + " |")
        
    return "\n".join(lines)


def get_clean_tables(page: pdfplumber.page.Page) -> List[Any]:
    """Finds tables on a page and deduplicates nested sub-bounding boxes."""
    found = page.find_tables()
    if not found:
        return []
        
    # Sort largest area first
    sorted_tables = sorted(
        found,
        key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]),
        reverse=True
    )
    
    clean: List[Any] = []
    for t in sorted_tables:
        bbox = t.bbox
        # Check if bbox is contained inside an existing larger table
        is_sub = False
        for c in clean:
            cb = c.bbox
            if (bbox[0] >= cb[0] - 2 and bbox[1] >= cb[1] - 2 and
                    bbox[2] <= cb[2] + 2 and bbox[3] <= cb[3] + 2):
                is_sub = True
                break
        if not is_sub:
            clean.append(t)
            
    # Return tables sorted by vertical 'top' coordinate
    return sorted(clean, key=lambda t: t.bbox[1])


class ParsedNode:
    """A discrete hierarchical tree node representing a document heading or section."""

    def __init__(
        self,
        heading: str,
        level: int,
        section_number: Optional[str] = None,
        title: Optional[str] = None,
        page_number: Optional[int] = None,
        node_id: Optional[str] = None,
    ):
        self.id = node_id or str(uuid.uuid4())
        self.heading = heading
        self.level = level
        self.section_number = section_number
        self.title = title or heading
        self.page_number = page_number
        self.body_lines: List[str] = []
        self.tables: List[List[List[Optional[str]]]] = []
        self.parent: Optional[ParsedNode] = None
        self.children: List[ParsedNode] = []
        self.content_hash: str = ""

    @property
    def body_text(self) -> str:
        """Assembled body text for the node."""
        return "\n".join(self.body_lines).strip()

    def update_hash(self) -> str:
        """Calculates and stores the content hash for this node's body text."""
        self.content_hash = compute_body_hash(self.body_text)
        return self.content_hash

    def find_node_by_section(self, section_number: str) -> Optional[ParsedNode]:
        """Recursively search subtree for a specific section number."""
        if self.section_number == section_number:
            return self
        for child in self.children:
            found = child.find_node_by_section(section_number)
            if found:
                return found
        return None

    def flatten(self) -> List[ParsedNode]:
        """Flatten subtree into a list in depth-first encounter order."""
        result = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result

    def to_dict(self, include_children: bool = True) -> Dict[str, Any]:
        """Serialize node to a dictionary representation."""
        data: Dict[str, Any] = {
            "id": self.id,
            "heading": self.heading,
            "section_number": self.section_number,
            "title": self.title,
            "level": self.level,
            "body_text": self.body_text,
            "content_hash": self.content_hash,
            "page_number": self.page_number,
            "table_count": len(self.tables),
            "tables": self.tables,
            "parent_section": self.parent.section_number if self.parent else None,
        }
        if include_children:
            data["children"] = [child.to_dict(include_children=True) for child in self.children]
        return data

    def __repr__(self) -> str:
        return (
            f"<ParsedNode(section='{self.section_number}', level={self.level}, "
            f"title='{self.title[:30]}', children={len(self.children)})>"
        )


class ParsedTree:
    """Represents a fully ingested and parsed manual hierarchy."""

    def __init__(
        self,
        document_name: str,
        root: ParsedNode,
        nodes_by_section: Dict[str, ParsedNode],
        total_pages: int,
        file_hash: str,
    ):
        self.document_name = document_name
        self.root = root
        self.nodes_by_section = nodes_by_section
        self.total_pages = total_pages
        self.file_hash = file_hash

    @property
    def all_nodes(self) -> List[ParsedNode]:
        """All nodes in tree including root."""
        return self.root.flatten()

    def get_node(self, section_number: str) -> Optional[ParsedNode]:
        """Lookup node by section number."""
        return self.nodes_by_section.get(section_number)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_name": self.document_name,
            "total_pages": self.total_pages,
            "file_hash": self.file_hash,
            "total_nodes": len(self.all_nodes),
            "tree": self.root.to_dict(include_children=True),
        }


def parse_pdf_to_tree(
    pdf_path: str | Path,
    document_name: str = "CardioTrack CT-200"
) -> ParsedTree:
    """Parses a medical device manual PDF into a structured hierarchical tree.
    
    Handles:
    - Numbered headings with arbitrary depth and irregular jumps (e.g. 2.1 -> 2.1.1.1).
    - Out-of-order sections (e.g. 3.4 appearing before 3.3).
    - Multi-column table extraction under respective sections.
    - Deterministic SHA-256 body text hashing.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF manual file not found: {path}")

    file_hash = compute_file_sha256(path)

    root = ParsedNode(
        heading=f"{document_name} Technical Manual",
        level=0,
        section_number="0",
        title=f"{document_name} Technical Manual",
        page_number=1,
    )
    nodes_by_section: Dict[str, ParsedNode] = {"0": root}
    current_node = root

    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)

        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1
            clean_tables = get_clean_tables(page)
            table_bboxes = [t.bbox for t in clean_tables]

            words = page.extract_words(extra_attrs=["fontname", "size"])

            # Cluster words by vertical top line position
            lines: Dict[int, List[Dict[str, Any]]] = {}
            for w in words:
                top_key = round(w["top"] / 3) * 3
                lines.setdefault(top_key, []).append(w)

            # Build unified stream of page elements sorted top-down
            elements: List[tuple] = []
            
            # 1. Add tables as stream elements
            for t in clean_tables:
                elements.append(("table", t.bbox[1], t))

            # 2. Add text lines not inside table boxes
            for top_key, line_words in lines.items():
                mid_y = sum(w["top"] for w in line_words) / len(line_words)
                in_table = any(tb[1] <= mid_y <= tb[3] for tb in table_bboxes)
                if not in_table:
                    line_text = " ".join(w["text"] for w in line_words).strip()
                    is_bold = any(
                        "bold" in (w.get("fontname") or "").lower()
                        for w in line_words
                    )
                    elements.append(("line", top_key, line_text, is_bold))

            # Sort top to bottom
            elements.sort(key=lambda el: el[1])

            # Process elements
            for element in elements:
                if element[0] == "table":
                    table_obj = element[2]
                    table_data = table_obj.extract()
                    if table_data:
                        current_node.tables.append(table_data)
                        md_table = table_to_markdown(table_data)
                        if md_table:
                            current_node.body_lines.append(md_table)
                else:
                    _, _, line_text, is_bold = element
                    if not line_text:
                        continue

                    # Check for numbered heading match with bold formatting
                    match = HEADING_REGEX.match(line_text)
                    if match and is_bold:
                        sec_num, title = match.group(1), match.group(2)
                        level = len(sec_num.split("."))

                        new_node = ParsedNode(
                            heading=line_text,
                            level=level,
                            section_number=sec_num,
                            title=title,
                            page_number=page_num,
                        )

                        # Resolve parent using longest ancestor prefix
                        parts = sec_num.split(".")
                        parent_node = root
                        for k in range(len(parts) - 1, 0, -1):
                            candidate_prefix = ".".join(parts[:k])
                            if candidate_prefix in nodes_by_section:
                                parent_node = nodes_by_section[candidate_prefix]
                                break

                        new_node.parent = parent_node
                        parent_node.children.append(new_node)
                        nodes_by_section[sec_num] = new_node
                        current_node = new_node
                    else:
                        current_node.body_lines.append(line_text)

    # Compute content hashes for all nodes
    for node in nodes_by_section.values():
        node.update_hash()

    return ParsedTree(
        document_name=document_name,
        root=root,
        nodes_by_section=nodes_by_section,
        total_pages=total_pages,
        file_hash=file_hash,
    )
