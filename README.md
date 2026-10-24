# AffineSurge: Medical Device Manual Parser & QA Generation Engine

A production-grade backend API built with **FastAPI**, **Pydantic**, and **SQLAlchemy** to parse technical medical device manuals (such as the CardioTrack CT-200) into versioned, structured hierarchical trees, track semantic changes across document iterations, manage version-pinned node selections, and generate automated QA test cases using LLMs with staleness detection.

---

## 📄 Approach Document: CT-200 Medical Device QA API

### 1. Architecture & Data Model
The system is built on **FastAPI** and **SQLAlchemy** with a local SQLite database for the structural tree, and a **local JSON store** for LLM outputs. 

#### Tree Parsing Decisions:
I utilized `pdfplumber` for ingestion because it handles tabular data significantly better than PyMuPDF. 
*   **Irregular Hierarchy:** Solved using a "longest ancestor prefix matching" algorithm. When parsing `2.1.1.1`, the algorithm attempts to find `2.1.1`, then `2.1`, attaching it cleanly to the correct parent.
*   **Out-of-Order Sections:** Solved by ensuring prefix resolution doesn't rely on linear vertical document flow. Both `3.4` and `3.3` resolve to parent `3` while preserving the authentic document layout sequence in `parent.children`.
*   **Multi-Column Tables:** Solved by stripping nested sub-bounding boxes and formatting tables as structured 2D matrices embedded as standard Markdown tables in the `node.body_text`.

#### Versioning Strategy:
I implemented a **path-based matching strategy** using `section_number` as the primary key and `title.lower()` as a fallback. 
*   **Known Failure Mode:** If a major manual revision entirely renumbers the sections (e.g., Section 4 becomes Section 5) *and* heavily edits the titles, the path-based matcher will fail to link them and will incorrectly flag the old section as "REMOVED" and the new one as "ADDED".

#### LLM Generation & Retry Strategy:
I utilized **LangChain** and Pydantic (`with_structured_output`) to strictly enforce the JSON schema for QA test cases. 
*   **Retry Strategy:** If the LLM output is malformed, the system catches the Pydantic validation error and retries up to 3 times before failing gracefully.
*   **Storage:** Raw LLM outputs are saved to `data/llm_outputs/{selection_id}.json`. This ensures regulatory compliance (easy export to a Document Management System), keeps the SQLite database lightweight, and allows artifacts to be archived independently.

---

### 2. Decision Log (Required)

**1. What's the one part of this system most likely to silently give wrong results without erroring? How would you catch it?**
The cryptographic content hashing for staleness detection. Because it relies on a strict SHA-256 hash of normalized whitespace, a minor formatting change, an OCR artifact, or a single-word typo fix in the PDF will silently flag a critical test case as "stale." I would catch this by implementing a semantic similarity threshold (e.g., using an embedding model or RapidFuzz) to separate minor text drifts from critical medical threshold changes.

**2. Where did you choose simplicity over correctness because of time, and what would break first if this went to production as-is?**
I chose simplicity in the duplicate selection policy. Currently, if a user submits the exact same node IDs for the same version, I return the existing `selection_id`. In a production environment, different QA engineers might need to create different selections from the same nodes for entirely different testing scopes (e.g., one for hardware QA, one for software QA). Returning the identical selection ID breaks their ability to track separate testing goals. 

**3. Name one input (to your parser, your versioning matcher, or your LLM call) that you did not handle, and what your system does when it sees it.**
I did not handle non-numbered conversational headings or standalone images without captions. If the parser encounters a bolded heading without a numbered prefix (e.g., "Note to Clinicians" instead of "1.3 Note"), it will treat it as standard body text and append it to the `body_lines` of the most recent numbered parent node, rather than creating a new structural section in the database.

---

### 3. What I would do differently with more time
*   Implement vector embeddings to detect semantic changes across versions, rather than relying solely on exact cryptographic hashes.
*   Implement a frontend UI to allow users to visually drag and select sections of the manual to generate test cases.
*   Implement an LLM-driven "Staleness Impact Rater" that automatically reads a detected document change and scores whether the existing test case is still valid (e.g., differentiating a typo from a change in battery voltage).

---

## 🏛️ System Architecture & Data Models

### 1. Versioning (`DocumentVersion`)
- Tracks distinct document releases (`v1.0` and `v2.0` of CT-200) without overwriting baselines.
- Calculates canonical SHA-256 file hashes, total page counts, and parsing lifecycle status.
- Enforces composite uniqueness per `(document_name, version_tag)`.

### 2. Hierarchical Document Tree (`Node`)
- Implements an adjacency list pattern with `parent_id` (foreign key with `CASCADE` delete).
- Structural types: `DOCUMENT_ROOT`, `SECTION`, `HEADING_1`, `HEADING_2`, `HEADING_3`, `PARAGRAPH`, `TABLE`, `LIST_ITEM`, `WARNING`, `NOTE`.
- **Content Hashing**: SHA-256 `content_hash` over canonicalized body text, section numbers, and titles.
- **Cross-Version Linking**: Nodes in `v2.0` link to their predecessor via `linked_node_id`, recording `change_status` (`UNCHANGED`, `MODIFIED`, `ADDED`, `REMOVED`), similarity scores, and change summaries.

### 3. Version-Pinned Selections (`Selection` & `SelectionNode`)
- Allows QA engineers to select subsets of tree nodes for test planning or auditing.
- Pins node references to an exact version (`pinned_version_id`) and snapshots the `pinned_content_hash` at the time of selection.
- Enforces node uniqueness per selection via `UniqueConstraint('selection_id', 'node_id')`.

### 4. LLM Generation & Local JSON Store
- LangChain integration with Pydantic structured output (`with_structured_output`) guarantees 3–5 actionable QA test cases (`title`, `steps`, `expected_result`).
- Implements 3-attempt automated retry on malformed outputs before failing gracefully.
- Raw outputs persisted in `data/llm_outputs/{selection_id}.json` with duplicate-caching logic (`force_regenerate=false`).

### 5. Staleness Detection (`GET /api/v1/test-cases/{selection_id}`)
- Compares `pinned_content_hash` of each selected node against the `content_hash` of the corresponding node in the *latest* available manual version.
- Automatically flags `is_stale: true` when underlying specifications change across versions.

---

## 🔌 API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service health status and database connectivity probe |
| `GET` | `/api/v1/versions` | List all ingested manual versions (`v1.0`, `v2.0`) |
| `GET` | `/api/v1/versions/{version_id}` | Retrieve specific version metadata and node statistics |
| `GET` | `/api/v1/versions/{version_id}/diff` | Full cross-version diff summary (`MODIFIED`, `ADDED`, `UNCHANGED`) |
| `GET` | `/api/v1/nodes` | Browse hierarchical tree (defaults to latest version root nodes) |
| `GET` | `/api/v1/nodes/{node_id}` | Retrieve full node details, children, and diff summary |
| `GET` | `/api/v1/nodes/search` | Search manual headings and body content with snippets |
| `POST` | `/api/v1/selections` | Create version-pinned selection with snapshot hashes |
| `GET` | `/api/v1/selections` | List created selections |
| `GET` | `/api/v1/selections/{selection_id}` | Retrieve selection details and pinned nodes |
| `POST` | `/api/v1/selections/{selection_id}/generate` | Generate 3-5 QA test cases via LLM with 3x retry & cache |
| `GET` | `/api/v1/test-cases/{selection_id}` | Retrieve test cases and execute cryptographic staleness check |

---

## 📁 Project Structure

```text
AffineSurge/
├── app/
│   ├── main.py              # FastAPI application & startup lifecycle
│   ├── config.py            # Environment-aware settings
│   ├── database.py          # SQLAlchemy SQLite engine with PRAGMA foreign_keys=ON
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── version.py       # DocumentVersion model & VersionStatus
│   │   ├── node.py          # Hierarchical Node model, hashing, cross-version links
│   │   ├── selection.py     # Selection & SelectionNode models (version pinning)
│   │   └── test_case.py     # TestCase model & staleness tracking
│   ├── schemas/             # Pydantic validation & response DTOs
│   │   ├── version.py
│   │   ├── node.py          # Flat & recursive NodeTreeNode schemas
│   │   ├── selection.py
│   │   └── test_case.py     # QATestCase, Suite, Staleness, and Generation DTOs
│   ├── api/v1/              # REST API route handlers
│   │   ├── router.py        # Centralized v1 router
│   │   ├── versions.py      # Version browsing and diff endpoints
│   │   ├── nodes.py         # Tree navigation and search endpoints
│   │   ├── selections.py    # Selection creation and LLM generation endpoints
│   │   └── test_cases.py    # Test case retrieval and staleness detection
│   └── services/            # Core business logic
│       ├── pdf_parser.py    # pdfplumber extraction & hierarchical tree parser
│       ├── ingestion.py     # DB ingestion service & cross-version diff linker
│       ├── llm_generator.py # LangChain generation, retries, and local JSON store
│       └── pdf_runtime.py   # Runtime compatibility shims for ARM64/Windows
├── tests/
│   ├── conftest.py          # In-memory SQLite fixture with StaticPool
│   ├── test_models.py       # Model hierarchy, cascade, hashing, & constraint tests
│   ├── test_pdf_parser.py   # Edge case parser tests (irregular, out-of-order, tables)
│   ├── test_ingestion_and_versioning.py # Ingestion & cross-version linking tests
│   ├── test_api_browse_and_selections.py # Browse & selection API endpoint tests
│   ├── test_llm_and_staleness.py # LLM retry strategy & staleness detection tests
│   └── test_api_init.py     # FastAPI startup & health check tests
├── data/
│   └── llm_outputs/         # Local JSON store for raw LLM outputs
├── ct200_manual.pdf         # CT-200 v1 baseline manual
├── ct200_manual_v2.pdf      # CT-200 v2 updated manual
├── APPROACH.md              # Standalone Approach Document & Decision Log
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 🚀 Getting Started

### 1. Requirements
- Python 3.10+
- SQLite3

### 2. Run the API Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive OpenAPI documentation will be available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### 3. Run the Full Test Suite
```bash
pytest -v
```
All **27 unit tests** covering edge cases, ingestion, version linking, selection pinning, LLM retry mechanisms, and staleness detection pass with 100% success.
