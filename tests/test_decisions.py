"""Tests for human decisions and the audit trail. Run: pytest -v  (no LLM used)."""
from tests.test_validator import client, upload  # noqa: F401  (reuses the stubbed-LLM test setup)


def setup_review_doc(client):
    """PO-1002 then BL-9002 (38 pallets vs 40 ordered) -> BL lands in NEEDS_REVIEW."""
    upload(client, "PO-1002.pdf")
    bl = upload(client, "BL-9002.pdf")
    assert bl["validation"]["status"] == "NEEDS_REVIEW"
    return bl["id"]


def decide(client, doc_id, **overrides):
    body = {"action": "approve", "reviewer": "Priya", "comment": "Supplier confirmed 2 pallets follow later"}
    body.update(overrides)
    return client.post(f"/documents/{doc_id}/decision", json=body)


def test_approve_flow_and_audit_trail(client):
    doc_id = setup_review_doc(client)
    r = decide(client, doc_id)
    assert r.status_code == 200
    assert r.json()["status"] == "MANUALLY_APPROVED"

    trail = client.get(f"/documents/{doc_id}/audit").json()
    assert [e["action"] for e in trail] == ["UPLOADED", "VALIDATED", "APPROVED"]
    last = trail[-1]
    assert last["actor"] == "Priya"
    assert "2 pallets" in last["comment"]
    assert (last["from_status"], last["to_status"]) == ("NEEDS_REVIEW", "MANUALLY_APPROVED")
    assert client.get(f"/documents/{doc_id}").json()["status"] == "MANUALLY_APPROVED"


def test_reject_flow(client):
    doc_id = setup_review_doc(client)
    r = decide(client, doc_id, action="reject", comment="Short shipment not acceptable")
    assert r.json()["status"] == "MANUALLY_REJECTED"
    assert client.get(f"/documents/{doc_id}/audit").json()[-1]["action"] == "REJECTED"


def test_comment_is_mandatory(client):
    doc_id = setup_review_doc(client)
    assert decide(client, doc_id, comment="").status_code == 422
    assert decide(client, doc_id, comment="ok").status_code == 422        # too short to be a reason
    assert client.get(f"/documents/{doc_id}").json()["status"] == "NEEDS_REVIEW"


def test_reviewer_name_is_mandatory(client):
    doc_id = setup_review_doc(client)
    assert decide(client, doc_id, reviewer="").status_code == 422


def test_invalid_action_is_refused(client):
    doc_id = setup_review_doc(client)
    assert decide(client, doc_id, action="maybe").status_code == 422


def test_cannot_decide_twice(client):
    doc_id = setup_review_doc(client)
    assert decide(client, doc_id).status_code == 200
    assert decide(client, doc_id, action="reject").status_code == 409


def test_cannot_decide_an_auto_approved_document(client):
    upload(client, "PO-1001.pdf")
    inv = upload(client, "INV-5001.pdf")
    assert inv["validation"]["status"] == "APPROVED"
    assert decide(client, inv["id"]).status_code == 409


def test_cannot_override_an_auto_rejected_duplicate(client):
    upload(client, "PO-1001.pdf")
    upload(client, "INV-5001.pdf")
    dup = upload(client, "INV-5001.pdf")
    assert dup["validation"]["status"] == "REJECTED"
    assert decide(client, dup["id"]).status_code == 409


def test_revalidation_cannot_overwrite_a_human_decision(client):
    doc_id = setup_review_doc(client)
    decide(client, doc_id)
    assert client.post(f"/documents/{doc_id}/validate").status_code == 409
    assert client.get(f"/documents/{doc_id}").json()["status"] == "MANUALLY_APPROVED"


def test_unknown_document_is_404(client):
    assert decide(client, 999).status_code == 404
    assert client.get("/documents/999/audit").status_code == 404


def test_review_queue_filter(client):
    setup_review_doc(client)                       # PO recorded + one NEEDS_REVIEW
    upload(client, "PO-1001.pdf")
    upload(client, "INV-5001.pdf")                 # APPROVED
    queue = client.get("/documents", params={"status": "NEEDS_REVIEW"}).json()
    assert len(queue) == 1 and queue[0]["doc_number"] == "BL-9002"
    assert len(client.get("/documents").json()) == 4


def test_revalidation_is_also_audited(client):
    first = upload(client, "INV-5001.pdf")          # PO missing -> NEEDS_REVIEW
    upload(client, "PO-1001.pdf")
    client.post(f"/documents/{first['id']}/validate")
    trail = client.get(f"/documents/{first['id']}/audit").json()
    assert [e["action"] for e in trail] == ["UPLOADED", "VALIDATED", "VALIDATED"]
    assert trail[-1]["to_status"] == "APPROVED"
