"""Step 2 of the pipeline: compare an extracted document against its PO.

How it works:
  - rules.yaml says which checks to run for each document type.
  - Each check below is a small, generic function: (doc, po, params, ctx) -> list of problems.
    An empty list means the check passed.
  - validate() runs the checks, collects the problems ("findings") and decides
    APPROVED / NEEDS_REVIEW / REJECTED.

This file never contains business numbers (like "2% tolerance"); those live in rules.yaml.
"""
import re
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

from backend.extractor import ExtractedDoc

RULES_PATH = Path(__file__).resolve().parent / "rules.yaml"


def load_rules(path: Path = RULES_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------- helpers
def _norm(text: Optional[str]) -> str:
    """'Oceanic Freight Ltd.' and 'oceanic freight ltd' compare as equal."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _tokens(text: Optional[str]) -> set:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}


def _similarity(a: Optional[str], b: Optional[str]) -> float:
    """How alike two item descriptions are (0 to 1). Tolerates word order and plurals."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _parse_date(value: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


# ----------------------------------------------------------------- checks
def has_po_reference(doc, po, params, ctx):
    return [] if doc.po_reference else ["No PO reference on this document"]


def po_exists(doc, po, params, ctx):
    if doc.po_reference and po is None:
        return [f"PO {doc.po_reference} has not been uploaded yet, so nothing to compare against"]
    return []


def duplicate_document(doc, po, params, ctx):
    if ctx.get("is_duplicate"):
        return [f"{doc.doc_number} was already processed earlier (duplicate)"]
    return []


def vendor_matches(doc, po, params, ctx):
    if po is None or not po.vendor:
        return []
    if not doc.vendor:
        return ["Vendor/shipper is missing from this document"]
    if _norm(doc.vendor) != _norm(po.vendor):
        return [f"Vendor mismatch: PO has '{po.vendor}', document has '{doc.vendor}'"]
    return []


def buyer_matches(doc, po, params, ctx):
    if po is None or not po.buyer:
        return []
    if not doc.buyer:
        return ["Buyer/consignee is missing from this document"]
    if _norm(doc.buyer) != _norm(po.buyer):
        return [f"Buyer mismatch: PO has '{po.buyer}', document has '{doc.buyer}'"]
    return []


def total_within_tolerance(doc, po, params, ctx):
    if po is None or po.total is None:
        return []
    if doc.total is None:
        return ["Total amount is missing from this document"]
    tolerance = float(params.get("tolerance_percent", 0))
    diff = doc.total - po.total
    pct = abs(diff) / po.total * 100 if po.total else 0.0
    if pct > tolerance:
        direction = "above" if diff > 0 else "below"
        return [
            f"Total {doc.total:,.2f} is {abs(diff):,.2f} ({pct:.1f}%) {direction} "
            f"the PO total {po.total:,.2f} (allowed: {tolerance:g}%)"
        ]
    return []


def line_items_match(doc, po, params, ctx):
    if po is None:
        return []
    if not po.items:
        return []
    if not doc.items:
        return ["No line items were extracted from this document, so quantities cannot be verified"]

    check_prices = bool(params.get("check_prices", False))
    problems = []
    unused = list(doc.items)

    for po_item in po.items:
        best, best_score = None, 0.0
        for cand in unused:
            score = _similarity(po_item.description, cand.description)
            if score > best_score:
                best, best_score = cand, score
        if best is None or best_score < 0.6:
            problems.append(f"PO item '{po_item.description}' is not in this document")
            continue
        unused.remove(best)

        if po_item.quantity is not None and best.quantity is not None \
                and abs(po_item.quantity - best.quantity) > 1e-6:
            problems.append(
                f"Quantity mismatch for '{po_item.description}': "
                f"PO {po_item.quantity:g}, document {best.quantity:g}"
            )
        if check_prices and po_item.unit_price is not None and best.unit_price is not None \
                and abs(po_item.unit_price - best.unit_price) > 0.005:
            problems.append(
                f"Unit price mismatch for '{po_item.description}': "
                f"PO {po_item.unit_price:.2f}, document {best.unit_price:.2f}"
            )

    for extra in unused:
        detail = []
        if extra.quantity is not None:
            detail.append(f"qty {extra.quantity:g}")
        if extra.unit_price is not None:
            detail.append(f"price {extra.unit_price:.2f}")
        suffix = f" ({', '.join(detail)})" if detail else ""
        problems.append(f"Item not on the PO: '{extra.description}'{suffix}")

    return problems


def not_dated_before_po(doc, po, params, ctx):
    if po is None:
        return []
    d, p = _parse_date(doc.date), _parse_date(po.date)
    if d and p and d < p:
        return [f"Document date {d} is earlier than the PO date {p}"]
    return []


# Name used in rules.yaml -> function above
CHECKS = {
    "has_po_reference": has_po_reference,
    "po_exists": po_exists,
    "duplicate_document": duplicate_document,
    "vendor_matches": vendor_matches,
    "buyer_matches": buyer_matches,
    "total_within_tolerance": total_within_tolerance,
    "line_items_match": line_items_match,
    "not_dated_before_po": not_dated_before_po,
}


# --------------------------------------------------------------- the engine
def validate(
    doc: ExtractedDoc,
    po: Optional[ExtractedDoc],
    rules: dict,
    is_duplicate: bool = False,
) -> dict:
    """Returns {"status": ..., "findings": [{"check", "severity", "message"}, ...]}"""
    if doc.doc_type == "purchase_order":
        return {"status": "PO_RECORDED", "findings": []}

    rule_list = rules.get(doc.doc_type)
    if rule_list is None:
        return {
            "status": "NEEDS_REVIEW",
            "findings": [{
                "check": "document_type",
                "severity": "review",
                "message": "Could not identify the document type",
            }],
        }

    ctx = {"is_duplicate": is_duplicate}
    findings = []
    for rule in rule_list:
        name = rule["check"]
        fn = CHECKS.get(name)
        if fn is None:
            raise ValueError(f"rules.yaml uses an unknown check: '{name}'")
        params = {k: v for k, v in rule.items() if k not in ("check", "severity")}
        for message in fn(doc, po, params, ctx):
            findings.append({
                "check": name,
                "severity": rule.get("severity", "review"),
                "message": message,
            })

    if any(f["severity"] == "reject" for f in findings):
        status = "REJECTED"
    elif findings:
        status = "NEEDS_REVIEW"
    else:
        status = "APPROVED"
    return {"status": status, "findings": findings}
