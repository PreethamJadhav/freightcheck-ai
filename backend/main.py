"""FreightCheck AI - backend (Day 3: upload -> extract -> validate -> HUMAN DECISION + AUDIT LOG).

Run from the project root:
    uvicorn backend.main:app --reload
Then open http://127.0.0.1:8000/docs  (FastAPI gives you a free test UI).
"""
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from typing import Literal, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.extractor import ExtractedDoc, extract_document
from backend.validator import load_rules, validate

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = ROOT / "freightcheck.db"

app = FastAPI(title="FreightCheck AI")

# Lets your React app (running on another port) call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS documents (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   filename TEXT NOT NULL,
                   doc_type TEXT,
                   doc_number TEXT,
                   extracted_json TEXT NOT NULL,
                   status TEXT NOT NULL DEFAULT 'EXTRACTED',
                   created_at TEXT NOT NULL
               )"""
        )
        # New in Day 2: every validation run is kept (history for the audit trail later)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS validations (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   document_id INTEGER NOT NULL,
                   status TEXT NOT NULL,
                   findings_json TEXT NOT NULL,
                   created_at TEXT NOT NULL,
                   FOREIGN KEY (document_id) REFERENCES documents (id)
               )"""
        )
        # New in Day 3: an append-only record of everything that happens to a document
        conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   document_id INTEGER NOT NULL,
                   action TEXT NOT NULL,
                   actor TEXT NOT NULL,
                   comment TEXT,
                   from_status TEXT,
                   to_status TEXT,
                   created_at TEXT NOT NULL,
                   FOREIGN KEY (document_id) REFERENCES documents (id)
               )"""
        )


init_db()

HUMAN_DECISION_STATUSES = ("MANUALLY_APPROVED", "MANUALLY_REJECTED")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_audit(conn, doc_id, action, actor, comment=None, from_status=None, to_status=None):
    conn.execute(
        "INSERT INTO audit_log (document_id, action, actor, comment, from_status, to_status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doc_id, action, actor, comment, from_status, to_status, now()),
    )


class DecisionIn(BaseModel):
    action: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1, max_length=100)
    comment: str = Field(min_length=3, max_length=1000)   # a reason is mandatory


def run_validation(conn, doc_id: int) -> dict:
    """Validate one stored document against its PO, save the result, update its status."""
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")

    doc = ExtractedDoc(**json.loads(row["extracted_json"]))

    po = None
    if doc.po_reference:
        po_row = conn.execute(
            "SELECT extracted_json FROM documents "
            "WHERE doc_type = 'purchase_order' AND doc_number = ? ORDER BY id DESC LIMIT 1",
            (doc.po_reference,),
        ).fetchone()
        if po_row:
            po = ExtractedDoc(**json.loads(po_row["extracted_json"]))

    # A duplicate = the same number of the same type was stored EARLIER
    is_duplicate = conn.execute(
        "SELECT 1 FROM documents WHERE doc_type = ? AND doc_number = ? AND id < ? LIMIT 1",
        (row["doc_type"], row["doc_number"], doc_id),
    ).fetchone() is not None

    result = validate(doc, po, load_rules(), is_duplicate=is_duplicate)   # rules.yaml is re-read each time

    conn.execute(
        "INSERT INTO validations (document_id, status, findings_json, created_at) VALUES (?, ?, ?, ?)",
        (doc_id, result["status"], json.dumps(result["findings"]), now()),
    )
    conn.execute("UPDATE documents SET status = ? WHERE id = ?", (result["status"], doc_id))
    n = len(result["findings"])
    log_audit(conn, doc_id, "VALIDATED", "system",
              comment=f"{n} finding(s)" if n else "no findings",
              from_status=row["status"], to_status=result["status"])
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    saved = UPLOAD_DIR / Path(file.filename).name   # .name strips any folder tricks
    with saved.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        extracted = extract_document(str(saved))
    except ValueError as e:                 # e.g. scanned PDF with no text
        raise HTTPException(422, str(e))
    except RuntimeError as e:               # e.g. missing API key
        raise HTTPException(500, str(e))
    except Exception as e:                  # LLM returned bad JSON, API error, etc.
        raise HTTPException(502, f"Extraction failed: {e}")

    with db() as conn:
        cur = conn.execute(
            """INSERT INTO documents (filename, doc_type, doc_number, extracted_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                file.filename,
                extracted.doc_type,
                extracted.doc_number,
                extracted.model_dump_json(),
                now(),
            ),
        )
        doc_id = cur.lastrowid
        log_audit(conn, doc_id, "UPLOADED", "system", comment=file.filename, to_status="EXTRACTED")
        validation = run_validation(conn, doc_id)

    return {"id": doc_id, "extracted": extracted.model_dump(), "validation": validation}


@app.post("/documents/{doc_id}/validate")
def revalidate_document(doc_id: int):
    """Run validation again, e.g. after the matching PO was uploaded or rules.yaml changed."""
    with db() as conn:
        row = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row and row["status"] in HUMAN_DECISION_STATUSES:
            raise HTTPException(409, "A reviewer has already decided this document; it cannot be re-validated.")
        return {"id": doc_id, "validation": run_validation(conn, doc_id)}


@app.post("/documents/{doc_id}/decision")
def decide_document(doc_id: int, decision: DecisionIn):
    """A person approves or rejects a document the system flagged NEEDS_REVIEW."""
    with db() as conn:
        row = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Document not found")
        if row["status"] != "NEEDS_REVIEW":
            raise HTTPException(
                409, f"Only documents in NEEDS_REVIEW can be decided (this one is {row['status']})."
            )
        new_status = "MANUALLY_APPROVED" if decision.action == "approve" else "MANUALLY_REJECTED"
        conn.execute("UPDATE documents SET status = ? WHERE id = ?", (new_status, doc_id))
        action_name = "APPROVED" if decision.action == "approve" else "REJECTED"
        log_audit(conn, doc_id, action_name,
                  decision.reviewer, comment=decision.comment,
                  from_status=row["status"], to_status=new_status)
    return {"id": doc_id, "status": new_status}


@app.get("/documents/{doc_id}/audit")
def get_audit_trail(doc_id: int):
    with db() as conn:
        if not conn.execute("SELECT 1 FROM documents WHERE id = ?", (doc_id,)).fetchone():
            raise HTTPException(404, "Document not found")
        rows = conn.execute(
            "SELECT action, actor, comment, from_status, to_status, created_at "
            "FROM audit_log WHERE document_id = ? ORDER BY id",
            (doc_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/documents")
def list_documents(status: Optional[str] = None):
    """All documents, newest first. Use ?status=NEEDS_REVIEW to get the review queue."""
    query = ("SELECT id, filename, doc_type, doc_number, status, created_at FROM documents")
    params = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    with db() as conn:
        rows = conn.execute(query + " ORDER BY id DESC", params).fetchall()
    return [dict(r) for r in rows]


@app.get("/documents/{doc_id}")
def get_document(doc_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Document not found")
        val = conn.execute(
            "SELECT status, findings_json, created_at FROM validations "
            "WHERE document_id = ? ORDER BY id DESC LIMIT 1",
            (doc_id,),
        ).fetchone()
    data = dict(row)
    data["extracted"] = json.loads(data.pop("extracted_json"))
    data["validation"] = (
        {"status": val["status"], "findings": json.loads(val["findings_json"]), "created_at": val["created_at"]}
        if val else None
    )
    return data
