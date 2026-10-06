"""Generates 8 fake logistics PDFs into ../samples/ plus expected.json.
Run from the project root:  python scripts/generate_samples.py
All names and numbers are fictional.
"""
import json
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples"
OUT.mkdir(exist_ok=True)

BUYER = "Sunrise Traders Pvt Ltd"

DOCS = [
    # ---------- Purchase Orders ----------
    {"file": "PO-1001.pdf", "title": "PURCHASE ORDER", "lines": [
        "PO Number: PO-1001", "Date: 2026-08-01", f"Buyer: {BUYER}",
        "Vendor: Oceanic Freight Ltd", "Incoterm: FOB", "Route: Chennai -> Rotterdam", "",
        "Items:", "  Cotton fabric rolls | Qty: 500 | Unit price: 12.00 USD", "",
        "Total: 6000.00 USD"]},
    {"file": "PO-1002.pdf", "title": "PURCHASE ORDER", "lines": [
        "PO Number: PO-1002", "Date: 2026-08-05", f"Buyer: {BUYER}",
        "Vendor: Delta Packaging Co", "Incoterm: CIF", "Route: Mumbai -> Hamburg", "",
        "Items:", "  Cartons | Qty: 2000 | Unit price: 0.85 USD",
        "  Pallets | Qty: 40 | Unit price: 15.00 USD", "",
        "Total: 2300.00 USD"]},
    {"file": "PO-1003.pdf", "title": "PURCHASE ORDER", "lines": [
        "PO Number: PO-1003", "Date: 2026-08-10", f"Buyer: {BUYER}",
        "Vendor: Apex Electronics Components", "Incoterm: FOB",
        "Route: Shenzhen -> Nhava Sheva", "",
        "Items:", "  Capacitors | Qty: 10000 | Unit price: 0.30 USD",
        "  Resistors | Qty: 20000 | Unit price: 0.10 USD", "",
        "Total: 5000.00 USD"]},
    # ---------- Invoices ----------
    {"file": "INV-5001.pdf", "title": "COMMERCIAL INVOICE", "lines": [
        "Invoice Number: INV-5001", "Date: 2026-08-20", "PO Reference: PO-1001",
        "Vendor: Oceanic Freight Ltd", f"Bill To: {BUYER}", "",
        "Items:", "  Cotton fabric rolls | Qty: 500 | Unit price: 12.00 USD", "",
        "Total: 6000.00 USD"]},
    {"file": "INV-5002.pdf", "title": "COMMERCIAL INVOICE", "lines": [
        "Invoice Number: INV-5002", "Date: 2026-08-22", "PO Reference: PO-1002",
        "Vendor: Delta Packaging Co", f"Bill To: {BUYER}", "",
        "Items:", "  Cartons | Qty: 2000 | Unit price: 0.85 USD",
        "  Pallets | Qty: 40 | Unit price: 15.00 USD",
        "  Handling charge | Qty: 1 | Unit price: 350.00 USD", "",
        "Total: 2650.00 USD"]},
    {"file": "INV-5003.pdf", "title": "COMMERCIAL INVOICE", "lines": [
        "Invoice Number: INV-5003", "Date: 2026-08-25", "PO Reference: PO-1003",
        "Vendor: Apex Electronics Components", f"Bill To: {BUYER}", "",
        "Items:", "  Capacitors | Qty: 10000 | Unit price: 0.30 USD",
        "  Resistors | Qty: 15000 | Unit price: 0.10 USD", "",
        "Total: 4500.00 USD"]},
    # ---------- Bills of Lading ----------
    {"file": "BL-9001.pdf", "title": "BILL OF LADING", "lines": [
        "B/L Number: BL-9001", "Date: 2026-08-15", "PO Reference: PO-1001",
        "Shipper: Oceanic Freight Ltd", f"Consignee: {BUYER}",
        "Vessel: MV Blue Horizon | Voyage: 214E", "Container: MSKU1234567",
        "Port of Loading: Chennai", "Port of Discharge: Rotterdam", "",
        "Goods: 500 rolls cotton fabric", "Gross Weight: 4200 kg"]},
    {"file": "BL-9002.pdf", "title": "BILL OF LADING", "lines": [
        "B/L Number: BL-9002", "Date: 2026-08-18", "PO Reference: PO-1002",
        "Shipper: Delta Packaging Co", f"Consignee: {BUYER}",
        "Vessel: MV Eastern Star | Voyage: 087W", "Container: TGHU7654321",
        "Port of Loading: Mumbai", "Port of Discharge: Hamburg", "",
        "Goods: 2000 cartons, 38 pallets", "Gross Weight: 3100 kg"]},
]

# What your validator SHOULD conclude later (use these for testing)
EXPECTED = {
    "INV-5001": "APPROVED - matches PO-1001",
    "INV-5002": "NEEDS_REVIEW - total exceeds PO by 350 USD (extra handling charge)",
    "INV-5003": "NEEDS_REVIEW - resistor qty 15000 vs 20000 ordered; total below PO",
    "BL-9001": "APPROVED - matches PO-1001",
    "BL-9002": "NEEDS_REVIEW - 38 pallets shipped vs 40 ordered",
}


def render(doc):
    c = canvas.Canvas(str(OUT / doc["file"]), pagesize=A4)
    _, h = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 60, doc["title"])
    c.line(50, h - 70, 545, h - 70)
    c.setFont("Helvetica", 11)
    y = h - 100
    for line in doc["lines"]:
        c.drawString(50, y, line)
        y -= 18
    c.save()


if __name__ == "__main__":
    for d in DOCS:
        render(d)
    (OUT / "expected.json").write_text(json.dumps(EXPECTED, indent=2))
    print(f"Created {len(DOCS)} PDFs in {OUT}")
