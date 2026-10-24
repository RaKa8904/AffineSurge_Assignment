# Approach Document: CT-200 Medical Device QA API

## 1. Architecture & Data Model
The system is built on **FastAPI** and **SQLAlchemy** with a local SQLite database for the structural tree, and a **local JSON store** for LLM outputs. 

### Tree Parsing Decisions:
I utilized `pdfplumber` for ingestion because it handles tabular data significantly better than PyMuPDF. 
*   **Irregular Hierarchy:** Solved using a "longest ancestor prefix matching" algorithm. When parsing `2.1.1.1`, the algorithm attempts to find `2.1.1`, then `2.1`, attaching it cleanly to the correct parent.
*   **Out-of-Order Sections:** Solved by ensuring prefix resolution doesn't rely on linear vertical document flow. Both `3.4` and `3.3` resolve to parent `3` while preserving the authentic document layout sequence in `parent.children`.
*   **Multi-Column Tables:** Solved by stripping nested sub-bounding boxes and formatting tables as structured 2D matrices embedded as standard Markdown tables in the `node.body_text`.

### Versioning Strategy:
I implemented a **path-based matching strategy** using `section_number` as the primary key and `title.lower()` as a fallback. 
*   **Known Failure Mode:** If a major manual revision entirely renumbers the sections (e.g., Section 4 becomes Section 5) *and* heavily edits the titles, the path-based matcher will fail to link them and will incorrectly flag the old section as "REMOVED" and the new one as "ADDED".

### LLM Generation & Retry Strategy:
I utilized **LangChain** and Pydantic (`with_structured_output`) to strictly enforce the JSON schema for QA test cases. 
*   **Retry Strategy:** If the LLM output is malformed, the system catches the Pydantic validation error and retries up to 3 times before failing gracefully.
*   **Storage:** Raw LLM outputs are saved to `data/llm_outputs/{selection_id}.json`. This ensures regulatory compliance (easy export to a Document Management System), keeps the SQLite database lightweight, and allows artifacts to be archived independently.

---

## 2. Decision Log (Required)

**1. What's the one part of this system most likely to silently give wrong results without erroring? How would you catch it?**
The cryptographic content hashing for staleness detection. Because it relies on a strict SHA-256 hash of normalized whitespace, a minor formatting change, an OCR artifact, or a single-word typo fix in the PDF will silently flag a critical test case as "stale." I would catch this by implementing a semantic similarity threshold (e.g., using an embedding model or RapidFuzz) to separate minor text drifts from critical medical threshold changes.

**2. Where did you choose simplicity over correctness because of time, and what would break first if this went to production as-is?**
I chose simplicity in the duplicate selection policy. Currently, if a user submits the exact same node IDs for the same version, I return the existing `selection_id`. In a production environment, different QA engineers might need to create different selections from the same nodes for entirely different testing scopes (e.g., one for hardware QA, one for software QA). Returning the identical selection ID breaks their ability to track separate testing goals. 

**3. Name one input (to your parser, your versioning matcher, or your LLM call) that you did not handle, and what your system does when it sees it.**
I did not handle non-numbered conversational headings or standalone images without captions. If the parser encounters a bolded heading without a numbered prefix (e.g., "Note to Clinicians" instead of "1.3 Note"), it will treat it as standard body text and append it to the `body_lines` of the most recent numbered parent node, rather than creating a new structural section in the database.

---

## 3. What I would do differently with more time
*   Implement vector embeddings to detect semantic changes across versions, rather than relying solely on exact cryptographic hashes.
*   Implement a frontend UI to allow users to visually drag and select sections of the manual to generate test cases.
*   Implement an LLM-driven "Staleness Impact Rater" that automatically reads a detected document change and scores whether the existing test case is still valid (e.g., differentiating a typo from a change in battery voltage).
