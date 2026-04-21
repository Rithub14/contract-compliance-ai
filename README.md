# German Contract Compliance Checker

Upload an employment or vendor contract and get a clause-by-clause compliance report against German law — streamed live as each rule is checked.

---

## What it does

- Detects contract type automatically (vendor, white-collar employment, blue-collar employment)
- Extracts contract metadata (salary, working hours, vacation days, data protection clauses) to ground rule evaluations in actual contract facts
- Checks against German statutory requirements — 22 rules covering NachwG, ArbZG, MiLoG, KSchG, BDSG, HinSchG, NIS2, AI Act, and more
- Streams results in real time as each rule finishes (SSE)
- Each finding includes a verbatim excerpt, a justification type, and a severity rating
- An LLM-as-a-judge layer evaluates each finding for accuracy, completeness, and false-positive risk
- Optionally upload your own compliance rules file (PDF, TXT, or YAML) — matched via semantic embeddings instead of the default German ruleset

---

## Stack

| Layer | Technology |
|---|---|
| Agent pipeline | LangGraph 0.2 (StateGraph + Send API for parallel fan-out) |
| LLM | OpenAI gpt-4o-mini |
| API | FastAPI + sse-starlette (SSE streaming) |
| UI | Streamlit |
| OCR | pypdfium2 (digital PDFs) → Apple Vision/ocrmac on macOS, RapidOCR on Linux (scanned PDFs) |
| Document parsing | Regex clause splitter (§-based + paragraph fallback) |
| Semantic matching | fastembed BAAI/bge-small-en-v1.5 (custom rules only) |
| Deployment | Render (render.yaml) |

---

## Running locally

**Requirements:** Python 3.11+, Docker (optional). Apple Vision OCR (macOS) gives the best results for German scanned PDFs; RapidOCR is used automatically on Linux.

```bash
git clone https://github.com/Rithub14/contract-compliance-ai.git
cd contract-compliance-ai

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # add your OPENAI_API_KEY
```

Start the API:
```bash
uvicorn app.api.main:app --reload --reload-dir app --port 8000
```

Start the UI (separate terminal):
```bash
streamlit run app/ui/streamlit_app.py
```

Or with Docker:
```bash
docker-compose up --build
```

Then open `http://localhost:8501`.

---

## Custom compliance rules

Instead of the built-in EU ruleset, upload your own compliance file (PDF or TXT). Supported formats:

- **YAML with a `rules:` block** — each key becomes a named rule
- **Free text** — split on Article/Section/numbered headings, or paragraphs as fallback

Clause matching uses fastembed `BAAI/bge-small-en-v1.5` embeddings and cosine similarity. The model downloads once (~130 MB) on first use.

---

## Project structure

```
app/
  agents/          # LangGraph nodes: classifier, extractor, metadata_extractor,
                   #   rule_checker, scorer, report_writer
  api/             # FastAPI app, routers, in-memory job store
  config/          # Pydantic settings, rules.yaml
  services/        # OpenAI service, judge service, doc intel, custom rules parser
  ui/              # Streamlit frontend
docker/            # Dockerfiles for API and UI
tests/
```

---

## Rules covered

**Employment (white & blue collar):** Nachweisgesetz (NachwG), Arbeitszeitgesetz + BUrlG, DSGVO + BDSG, AGG, Mindestlohngesetz (MiLoG), KSchG + BGB §622, Arbeitnehmer-Entsendegesetz (AEntG), BEEG + MuSchG, Hinweisgeberschutzgesetz (HinSchG), AGG §§1,7,11, Teilzeit- und Befristungsgesetz (TzBfG)

**Vendor:** BGB §§286–288 (late payment), DSGVO Art. 28 (DPA), BSI-Gesetz / IT-SiG 2.0 (NIS2), Produkthaftungsgesetz, Lieferkettensorgfaltspflichtengesetz (LkSG), EU AI Act (2024/1689), Cyber Resilience Act, EU Data Act (2023/2854), DDG + NetzDG (DSA), HGB §§84–92c (commercial agents)
