"""Step 1 of the pipeline: PDF -> text -> structured JSON.

Two layers:
  1. pdfplumber reads the text out of the PDF.
  2. An LLM (Gemini) turns that text into a strict JSON object, which Pydantic
     then validates. If the LLM returns garbage, Pydantic raises an error
     instead of letting bad data flow downstream.
"""
import json
import os
import time
from typing import List, Literal, Optional

import pdfplumber
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


# ---------- The schema every document must be converted into ----------
class LineItem(BaseModel):
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None


class ExtractedDoc(BaseModel):
    doc_type: Literal["purchase_order", "invoice", "bill_of_lading", "unknown"]
    doc_number: Optional[str] = None
    date: Optional[str] = Field(None, description="YYYY-MM-DD")
    po_reference: Optional[str] = None
    vendor: Optional[str] = None          # vendor / shipper
    buyer: Optional[str] = None           # buyer / consignee / bill-to
    items: List[LineItem] = []
    total: Optional[float] = None
    currency: Optional[str] = None
    incoterm: Optional[str] = None
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    vessel: Optional[str] = None
    container_no: Optional[str] = None
    gross_weight_kg: Optional[float] = None


PROMPT = """You are a logistics document data extractor.
Read the document text below and return ONLY a JSON object (no markdown, no
explanation) with exactly these keys:

doc_type: one of "purchase_order", "invoice", "bill_of_lading", "unknown"
doc_number, date (YYYY-MM-DD), po_reference, vendor (vendor or shipper),
buyer (buyer, consignee or bill-to), items (list of
{{description, quantity, unit_price}}), total (number), currency,
incoterm, port_of_loading, port_of_discharge, vessel, container_no,
gross_weight_kg (number).

Rules:
- If a field is not present in the document, use null. NEVER guess or invent values.
- Numbers must be plain numbers (no commas, no currency symbols).
- For a bill of lading, put each goods line in items with description and quantity (unit_price null). Example: "2000 cartons, 38 pallets" -> [{{"description": "cartons", "quantity": 2000, "unit_price": null}}, {{"description": "pallets", "quantity": 38, "unit_price": null}}]
DOCUMENT TEXT:
{text}
"""


def pdf_to_text(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        pages = [(p.extract_text() or "") for p in pdf.pages]
    text = "\n".join(pages).strip()
    if not text:
        raise ValueError(
            "No text found in PDF. It may be a scanned image - OCR is needed (later phase)."
        )
    return text


def _parse(raw: str) -> ExtractedDoc:
    raw = (raw or "").replace("```json", "").replace("```", "").strip()
    return ExtractedDoc(**json.loads(raw))   # Pydantic validates here


def extract_with_gemini(text: str) -> ExtractedDoc:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=PROMPT.format(text=text),
                config={"response_mime_type": "application/json", "temperature": 0},
            )
            return _parse(response.text)
        except Exception as e:
            msg = str(e)
            if "503" in msg or "UNAVAILABLE" in msg:   # temporary overload: wait, retry
                time.sleep(2 ** (attempt + 1))
                continue
            raise                                       # 429 quota, bad key, etc.: stop now
    raise RuntimeError("Gemini is busy after 3 tries.")


def extract_with_groq(text: str) -> ExtractedDoc:
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing.")

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages=[{"role": "user", "content": PROMPT.format(text=text)}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return _parse(response.choices[0].message.content)


def extract_document(path: str) -> ExtractedDoc:
    text = pdf_to_text(path)
    try:
        return extract_with_gemini(text)
    except Exception as gemini_error:
        if os.getenv("GROQ_API_KEY"):
            print(f"Gemini failed ({gemini_error}); falling back to Groq")
            return extract_with_groq(text)
        raise gemini_error
def extract_document(path: str) -> ExtractedDoc:
    text = pdf_to_text(path)
    try:
        return extract_with_gemini(text)
    except Exception as gemini_error:
        if os.getenv("GROQ_API_KEY"):
            print(f"Gemini failed ({gemini_error}); falling back to Groq")
            return extract_with_groq(text)
        raise gemini_error