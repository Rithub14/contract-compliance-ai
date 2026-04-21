# EU Contract Compliance Checker

Upload an employment or vendor contract and get a clause-by-clause compliance report against major EU directives — streamed live as each rule is checked.

---

## What it does

- Detects contract type automatically (vendor, white-collar employment, blue-collar employment)
- Extracts contract metadata (salary, working hours, vacation days, data protection clauses) to ground rule evaluations in actual contract facts
- Checks against the relevant EU directives — 22 rules covering GDPR, Working Time, NIS2, AI Act, CSDDD, and more
- Streams results in real time as each rule finishes (SSE)
- Each finding includes a verbatim excerpt, a justification type, and a severity rating
- An LLM-as-a-judge layer evaluates each finding for accuracy, completeness, and false-positive risk
- Optionally upload your own compliance rules file (PDF, TXT, or YAML) — matched via semantic embeddings instead of the default EU ruleset

---

## Stack

| Layer | Technology |
|---|---|
| Agent pipeline | LangGraph 0.2 (StateGraph + Send API for parallel fan-out) |
| LLM | OpenAI gpt-4o-mini |
| API | FastAPI + sse-starlette (SSE streaming) |
| UI | Streamlit |
| OCR | Apple Vision via ocrmac + PyMuPDF (local, supports German) |
| Document parsing | Regex clause splitter (§-based + paragraph fallback) |
| Semantic matching | fastembed BAAI/bge-small-en-v1.5 (custom rules only) |
| Deployment | Render (render.yaml) |

---

## Running locally

**Requirements:** Python 3.11+, macOS (Apple Vision OCR), Docker (optional)

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

## EU directives covered

**Employment (white & blue collar):** Transparent & Predictable Working Conditions (2019/1152), Working Time (2003/88/EC), GDPR employee data (DSGVO + BDSG), Equal Treatment (AGG / 2000/78/EC), Minimum Wage (MiLoG / 2022/2041), Termination Notice (KSchG + BGB §622), Posted Workers (AEntG), Work-Life Balance (BEEG + MuSchG), Whistleblower Protection (HinSchG / 2019/1937), Race Equality (AGG §§1,7,11), Fixed-Term & Part-Time (TzBfG)

**Vendor:** Late Payment (BGB §§286–288), GDPR DPA (Art. 28), NIS2 / IT-Sicherheitsgesetz 2.0, Product Liability (ProdHaftG), CSDDD supply chain due diligence (LkSG / 2024/1760), EU AI Act (2024/1689), Cyber Resilience Act, Data Act (2023/2854), Digital Services Act (DDG), Commercial Agents (HGB §§84–92c)
