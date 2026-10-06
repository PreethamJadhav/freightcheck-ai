# FreightCheck AI

AI agent that extracts data from logistics documents (purchase orders, invoices,
bills of lading) and validates them against business rules.

**Status: Day 1 - upload -> extract -> store -> list**

## Setup (Windows / Mac / Linux)

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac / Linux

# 2. Install packages
pip install -r requirements.txt

# 3. Add your free Gemini key (get one at https://aistudio.google.com)
copy .env.example .env         # Windows   (Mac/Linux: cp .env.example .env)
# open .env and paste your key

# 4. Generate the 8 sample PDFs
python scripts/generate_samples.py

# 5. Start the API
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000/docs, try **POST /documents/upload** with any PDF
from the `samples/` folder, then **GET /documents**.

## Folder structure

```
freightcheck/
  backend/
    main.py          FastAPI app + SQLite
    extractor.py     PDF text + Gemini -> validated JSON
  scripts/
    generate_samples.py
  samples/           fake PDFs + expected.json (created by the script)
  requirements.txt
  .env.example
```

## Roadmap

- [x] Day 1: upload and extraction
- [ ] Rules file (`rules.yaml`) + validator: invoice vs PO
- [ ] Approve / reject endpoints + audit log table
- [ ] React frontend (upload page, list, detail view)
- [ ] LangGraph pipeline: extract -> validate -> decide -> human review
- [ ] Deploy (Render + Vercel) and demo video

## Notes

- Never commit `.env`. It is already in `.gitignore`.
- If the Gemini model name stops working, check the current name in Google AI Studio
  and update `GEMINI_MODEL` in `.env`.
