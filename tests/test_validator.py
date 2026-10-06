"""Run from the project root:  pytest -v

The sample documents are written here as already-extracted data, so these tests
never call an LLM (no API quota used, and results are always the same).
"""
import pytest
from fastapi.testclient import TestClient

from backend.extractor import ExtractedDoc, LineItem
from backend.validator import load_rules, validate

BUYER = "Sunrise Traders Pvt Ltd"


def item(desc, qty, price=None):
    return LineItem(description=desc, quantity=qty, unit_price=price)


# ---------------- the 3 purchase orders ----------------
PO_1001 = ExtractedDoc(doc_type="purchase_order", doc_number="PO-1001", date="2026-08-01",
                       vendor="Oceanic Freight Ltd", buyer=BUYER, total=6000, currency="USD",
                       incoterm="FOB", items=[item("Cotton fabric rolls", 500, 12.0)])
PO_1002 = ExtractedDoc(doc_type="purchase_order", doc_number="PO-1002", date="2026-08-05",
                       vendor="Delta Packaging Co", buyer=BUYER, total=2300, currency="USD",
                       incoterm="CIF", items=[item("Cartons", 2000, 0.85), item("Pallets", 40, 15.0)])
PO_1003 = ExtractedDoc(doc_type="purchase_order", doc_number="PO-1003", date="2026-08-10",
                       vendor="Apex Electronics Components", buyer=BUYER, total=5000, currency="USD",
                       incoterm="FOB", items=[item("Capacitors", 10000, 0.30), item("Resistors", 20000, 0.10)])

# ---------------- invoices ----------------
INV_5001 = ExtractedDoc(doc_type="invoice", doc_number="INV-5001", date="2026-08-20", po_reference="PO-1001",
                        vendor="Oceanic Freight Ltd", buyer=BUYER, total=6000, currency="USD",
                        items=[item("Cotton fabric rolls", 500, 12.0)])
INV_5002 = ExtractedDoc(doc_type="invoice", doc_number="INV-5002", date="2026-08-22", po_reference="PO-1002",
                        vendor="Delta Packaging Co", buyer=BUYER, total=2650, currency="USD",
                        items=[item("Cartons", 2000, 0.85), item("Pallets", 40, 15.0),
                               item("Handling charge", 1, 350.0)])
INV_5003 = ExtractedDoc(doc_type="invoice", doc_number="INV-5003", date="2026-08-25", po_reference="PO-1003",
                        vendor="Apex Electronics Components", buyer=BUYER, total=4500, currency="USD",
                        items=[item("Capacitors", 10000, 0.30), item("Resistors", 15000, 0.10)])

# ---------------- bills of lading ----------------
BL_9001 = ExtractedDoc(doc_type="bill_of_lading", doc_number="BL-9001", date="2026-08-15", po_reference="PO-1001",
                       vendor="Oceanic Freight Ltd", buyer=BUYER, port_of_loading="Chennai",
                       port_of_discharge="Rotterdam", vessel="MV Blue Horizon", container_no="MSKU1234567",
                       gross_weight_kg=4200, items=[item("rolls cotton fabric", 500)])
BL_9002 = ExtractedDoc(doc_type="bill_of_lading", doc_number="BL-9002", date="2026-08-18", po_reference="PO-1002",
                       vendor="Delta Packaging Co", buyer=BUYER, port_of_loading="Mumbai",
                       port_of_discharge="Hamburg", vessel="MV Eastern Star", container_no="TGHU7654321",
                       gross_weight_kg=3100, items=[item("cartons", 2000), item("pallets", 38)])

RULES = load_rules()


def check(doc, po, **kw):
    return validate(doc, po, RULES, **kw)


def messages(result):
    return " | ".join(f["message"] for f in result["findings"])


# ======================= expected.json answers =======================
def test_inv_5001_approved():
    assert check(INV_5001, PO_1001)["status"] == "APPROVED"


def test_inv_5002_extra_charge_needs_review():
    r = check(INV_5002, PO_1002)
    assert r["status"] == "NEEDS_REVIEW"
    assert "Handling charge" in messages(r)
    assert "Total" in messages(r)


def test_inv_5003_short_quantity_needs_review():
    r = check(INV_5003, PO_1003)
    assert r["status"] == "NEEDS_REVIEW"
    assert "Resistors" in messages(r) and "15000" in messages(r)


def test_bl_9001_approved():
    assert check(BL_9001, PO_1001)["status"] == "APPROVED"


def test_bl_9002_short_pallets_needs_review():
    r = check(BL_9002, PO_1002)
    assert r["status"] == "NEEDS_REVIEW"
    assert "Pallets" in messages(r) and "38" in messages(r)


# ======================= edge cases =======================
def test_po_itself_is_just_recorded():
    assert check(PO_1001, None)["status"] == "PO_RECORDED"


def test_missing_po_reference_is_rejected():
    doc = INV_5001.model_copy(update={"po_reference": None})
    assert check(doc, None)["status"] == "REJECTED"


def test_unknown_po_goes_to_review_not_reject():
    r = check(INV_5001, None)       # references PO-1001 but it was never uploaded
    assert r["status"] == "NEEDS_REVIEW"
    assert "not been uploaded" in messages(r)


def test_duplicate_is_rejected():
    assert check(INV_5001, PO_1001, is_duplicate=True)["status"] == "REJECTED"


def test_total_inside_tolerance_is_approved():
    doc = INV_5001.model_copy(update={"total": 6100})       # +1.7%, allowed 2%
    assert check(doc, PO_1001)["status"] == "APPROVED"


def test_total_outside_tolerance_needs_review():
    doc = INV_5001.model_copy(update={"total": 6200})       # +3.3%
    assert check(doc, PO_1001)["status"] == "NEEDS_REVIEW"


def test_vendor_name_formatting_is_ignored():
    doc = INV_5001.model_copy(update={"vendor": "OCEANIC FREIGHT LTD."})
    assert check(doc, PO_1001)["status"] == "APPROVED"


def test_wrong_vendor_needs_review():
    doc = INV_5001.model_copy(update={"vendor": "Some Other Vendor"})
    assert "Vendor mismatch" in messages(check(doc, PO_1001))


def test_invoice_dated_before_po_needs_review():
    doc = INV_5001.model_copy(update={"date": "2026-07-01"})
    assert "earlier than the PO date" in messages(check(doc, PO_1001))


def test_unit_price_mismatch_needs_review():
    doc = INV_5001.model_copy(update={"items": [item("Cotton fabric rolls", 500, 13.0)]})
    assert "Unit price mismatch" in messages(check(doc, PO_1001))


def test_unknown_check_in_rules_raises():
    with pytest.raises(ValueError):
        validate(INV_5001, PO_1001, {"invoice": [{"check": "does_not_exist"}]})


# ======================= full API flow (LLM stubbed) =======================
DOCS_BY_FILE = {
    "PO-1001.pdf": PO_1001, "PO-1002.pdf": PO_1002, "PO-1003.pdf": PO_1003,
    "INV-5001.pdf": INV_5001, "INV-5002.pdf": INV_5002, "INV-5003.pdf": INV_5003,
    "BL-9001.pdf": BL_9001, "BL-9002.pdf": BL_9002,
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import backend.main as m
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(m, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(m, "extract_document", lambda path: DOCS_BY_FILE[path.replace("\\", "/").split("/")[-1]])
    m.init_db()
    return TestClient(m.app)


def upload(client, name):
    return client.post("/documents/upload", files={"file": (name, b"%PDF-fake", "application/pdf")}).json()


def test_api_full_flow(client):
    for po in ("PO-1001.pdf", "PO-1002.pdf", "PO-1003.pdf"):
        assert upload(client, po)["validation"]["status"] == "PO_RECORDED"

    expected = {
        "INV-5001.pdf": "APPROVED", "INV-5002.pdf": "NEEDS_REVIEW", "INV-5003.pdf": "NEEDS_REVIEW",
        "BL-9001.pdf": "APPROVED", "BL-9002.pdf": "NEEDS_REVIEW",
    }
    for name, status in expected.items():
        assert upload(client, name)["validation"]["status"] == status, name

    listing = client.get("/documents").json()
    assert len(listing) == 8

    # uploading the same invoice again is caught as a duplicate
    assert upload(client, "INV-5001.pdf")["validation"]["status"] == "REJECTED"


def test_api_invoice_before_po_then_revalidate(client):
    first = upload(client, "INV-5001.pdf")
    assert first["validation"]["status"] == "NEEDS_REVIEW"          # PO not uploaded yet
    upload(client, "PO-1001.pdf")
    again = client.post(f"/documents/{first['id']}/validate").json()
    assert again["validation"]["status"] == "APPROVED"
    detail = client.get(f"/documents/{first['id']}").json()
    assert detail["validation"]["status"] == "APPROVED"
