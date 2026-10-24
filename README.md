# AffineSurge: Medical Device Manual Parser & QA Generation Engine

A backend API built with **FastAPI**, **Pydantic**, and **SQLAlchemy** to parse technical medical device manuals (such as the CardioTrack CT-200) into versioned, structured hierarchical trees, track semantic changes across document iterations, manage version-pinned node selections, and generate automated QA test cases.

---

## 🏛️ System Architecture & Data Models

### 1. Versioning (`DocumentVersion`)
- Tracks separate manual releases (e.g. `v1.0` and `v2.0` of CT-200) without overwriting historical baselines.
- Preserves raw file hashes (SHA-256), page counts, parsing status, and metadata.
- Enforces uniqueness per `(document_name, version_tag)`.

### 2. Hierarchical Document Tree (`Node`)
- Implements an adjacency list pattern with `parent_id` (foreign key with `CASCADE` delete).
- Structural types: `DOCUMENT_ROOT`, `SECTION`, `HEADING_1`, `HEADING_2`, `HEADING_3`, `PARAGRAPH`, `TABLE`, `LIST_ITEM`, `WARNING`, `NOTE`.
- **Content Hashing**: Deterministic canonical SHA-256 hash (`content_hash`) calculated over normalized content, title, section numbers, and node types.
- **Cross-Version Linking**: Nodes in `v2.0` link to their predecessor via `linked_node_id`, accompanied by `change_status` (`UNCHANGED`, `MODIFIED`, `ADDED`, `REMOVED`), similarity scores, and change summaries.

### 3. Version-Pinned Selections (`Selection` & `SelectionNode`)
- Allows QA engineers to select subsets of tree nodes for test planning or auditing.
- Pins node references to an exact version (`pinned_version_id`) and snapshots the `pinned_content_hash` at the time of selection.
- Enforces node uniqueness per selection via `UniqueConstraint('selection_id', 'node_id')`.

### 4. QA Test Cases & Staleness Detection (`TestCase`)
- Links generated test cases directly to specific nodes and versions.
- Records `source_content_hash` at generation time.
- Enables retrieval queries to flag staleness (`is_stale=True`) if the underlying document text has evolved in subsequent versions.

---

## 📁 Project Structure

```text
AffineSurge/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application & lifecycle
│   ├── config.py            # Environment-aware settings
│   ├── database.py          # SQLAlchemy SQLite engine, pragmas, sessionmaker
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── version.py       # DocumentVersion model & VersionStatus
│   │   ├── node.py          # Hierarchical Node model, hashing, cross-version links
│   │   ├── selection.py     # Selection & SelectionNode models (version pinning)
│   │   └── test_case.py     # TestCase model & staleness tracking
│   ├── schemas/             # Pydantic validation & response DTOs
│   │   ├── __init__.py
│   │   ├── version.py
│   │   ├── node.py          # Flat & recursive NodeTreeNode schemas
│   │   ├── selection.py
│   │   └── test_case.py
│   ├── api/                 # REST API endpoints
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── router.py
│   │       ├── versions.py
│   │       ├── nodes.py
│   │       └── selections.py
│   └── services/            # Parsing, linking, & LLM generation services
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # In-memory SQLite fixture with foreign key pragmas
│   ├── test_models.py       # Model hierarchy, cascade, hashing, & constraint tests
│   └── test_api_init.py     # FastAPI startup & health check tests
├── ct200_manual.pdf         # CT-200 v1 baseline manual
├── ct200_manual_v2.pdf      # CT-200 v2 updated manual
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 🚀 Getting Started

### 1. Requirements
- Python 3.10+
- SQLite (built into Python)

### 2. Run the API Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive OpenAPI documentation will be available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### 3. Run the Test Suite
```bash
pytest -v
```
