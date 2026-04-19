# EU Contract Compliance Checker

Upload an employment or vendor contract and get a clause-by-clause compliance report against major EU directives — streamed live as each rule is checked.

Built as a GenAI/MLOps portfolio project. Everything runs locally with mocks; swapping in real Azure services only requires setting the env vars.

---

## What it does

- Detects contract type automatically (vendor, white-collar employment, blue-collar employment)
- Checks against the relevant EU directives — 22 rules covering GDPR, Working Time, NIS2, AI Act, CSDDD, and more
- Streams results in real time as each rule finishes (SSE)
- Optionally upload your own compliance rules file (PDF or YAML) — the app uses semantic search to match clauses instead of the default EU ruleset
- Each finding is evaluated by an LLM-as-a-judge layer that scores accuracy, completeness, and false-positive risk
- Full trace logged to Langfuse (stub by default, live with keys)

---

## Stack

| Layer | Technology |
|---|---|
| Agent pipeline | LangGraph 0.2 (StateGraph + Send API for parallel fan-out) |
| API | FastAPI + sse-starlette (SSE streaming) |
| UI | Streamlit |
| Semantic matching | sentence-transformers `all-MiniLM-L6-v2` |
| Document extraction | pypdf (mock Azure Document Intelligence) |
| Observability | Langfuse tracing + Azure App Insights (stubs) |
| Infra (planned) | Azure Container Apps, ACR, Key Vault via Terraform |

---

## Deployment

The app is deployed on **Render** (live demo via `render.yaml`). Both the API and UI are separate web services that Render builds from the Dockerfiles and redeploys automatically on every push to `main`.

For production-grade deployment, the `infra/` directory contains full **Terraform** configs that provision the same setup on **Azure Container Apps** — ACR, Storage Account, Key Vault, Log Analytics, and both container apps. The GitHub Actions workflow at `.github/workflows/cd.yml` handles building, pushing to ACR, and deploying to Container Apps. That pipeline is set to manual trigger since Render handles the live demo, but it's ready to run against a real Azure subscription.

---

## Running locally

**Requirements:** Python 3.11, Docker (optional)

```bash
git clone https://github.com/Rithub14/contract-compliance-ai.git
cd contract-compliance-ai

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # leave USE_MOCKS=true for local dev
```

Start the API:
```bash
uvicorn app.api.main:app --reload --port 8000
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

Instead of the built-in EU ruleset, you can upload your own compliance file (PDF or TXT). Supported formats:

- **YAML with a `rules:` block** — each key becomes a named rule (see `samples/` for an example structure)
- **Free text** — the app splits on Article/Section/numbered headings, or falls back to paragraphs

Clause matching uses `all-MiniLM-L6-v2` embeddings and cosine similarity. The model downloads once (~90 MB) on first use.

---

## Project structure

```
app/
  agents/          # LangGraph nodes (classifier, extractor, rule_checker, scorer, report_writer)
  api/             # FastAPI app, routers, job store
  config/          # Pydantic settings, rules.yaml
  observability/   # Langfuse tracer, App Insights stub
  services/        # Mock services (blob, doc intel, openai, judge, custom rules)
  ui/              # Streamlit frontend
infra/             # Terraform modules (WIP)
docker/            # Dockerfiles for API and UI
tests/
```

---

## EU directives covered

**Employment (white & blue collar):** Transparent & Predictable Working Conditions (2019/1152), Working Time (2003/88/EC), GDPR employee data, Equal Treatment (2000/78/EC), Minimum Wage (2022/2041), Collective Redundancy (98/59/EC), Posted Workers, Work-Life Balance (2019/1158), Whistleblower Protection (2019/1937), Race Equality (2000/43/EC), Fixed-Term Work (1999/70/EC)

**Vendor:** Late Payment (2011/7/EU), GDPR DPA (Article 28), NIS2 (2022/2555), Product Liability, CSDDD supply chain due diligence (2024/1760), EU AI Act (2024/1689), Cyber Resilience Act, Data Act (2023/2854), Digital Services Act, Commercial Agents Directive

