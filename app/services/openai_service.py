import json
import re

import numpy as np
from fastembed import TextEmbedding
from openai import AsyncOpenAI

from app.config.settings import settings

# ── OpenAI client ──────────────────────────────────────────────────────────────

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


# ── Prompts ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a specialist EU and German employment and vendor contract compliance analyst.

Assessment rules:
- Do NOT fail a rule simply because it is absent from the contract text. Many obligations are satisfied by:
    - Mandatory statutory law (e.g. German ArbZG, BUrlG, MuSchG, BDSG, AGG, KSchG)
    - Collective bargaining agreements (Tarifvertrag) referenced in the contract
    - Works agreements (Betriebsvereinbarungen)
    - Separate policy documents or annexes referenced by the contract
    - EU directives that are directly applicable without needing an explicit contract clause
- Use FAIL only when a clause actively violates a requirement, or when a critical obligation has no possible statutory fallback and is entirely absent
- Use WARNING when coverage is partial, relies on an external reference that should be verified, or language is ambiguous
- Use PASS when explicitly compliant, or when statutory or collective agreement coverage applies
- Recognise both English and German legal terms (Probezeit, Kündigung, Tarifvertrag, DSGVO, Datenschutz, etc.)
- Always quote an exact excerpt from the contract as evidence. If no relevant text exists, set excerpt to N/A
- Severity must match status: FAIL → High or Critical, WARNING → Medium, PASS → Low
- Be concise, grounded, and avoid hallucinating legal failures"""

_USER_PROMPT = """Directive: {directive}
Rule: {rule_name}
Requirement: {rule_prompt}

Contract text:
{contract_text}

Respond with this exact JSON and nothing else:
{{
  "status": "PASS or WARNING or FAIL",
  "severity": "Low or Medium or High or Critical",
  "finding": "concise explanation of the compliance status with legal reasoning",
  "excerpt": "exact verbatim quote from the contract above, or N/A",
  "recommendation": "specific action needed, or No action required"
}}"""


def _parse_json_response(text: str) -> dict:
    """Parse GPT response, stripping markdown fences if present."""
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    return json.loads(cleaned)


async def _call_gpt(rule: dict, contract_text: str) -> tuple[dict, int, int]:
    response = await _get_client().chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        temperature=0.1,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_PROMPT.format(
                directive=rule.get("directive", ""),
                rule_name=rule.get("name", ""),
                rule_prompt=rule.get("prompt", ""),
                contract_text=contract_text[:6000],
            )},
        ],
    )
    result = _parse_json_response(response.choices[0].message.content)
    usage = response.usage
    return result, usage.prompt_tokens, usage.completion_tokens


# ── Fastembed semantic checker (custom rules only) ─────────────────────────────
# Custom rules use ONNX-based embeddings (fastembed) rather than GPT calls
# since the rules are free-form text with no pre-defined directive structure.

_embedding_model: TextEmbedding | None = None


def _get_embedding_model() -> TextEmbedding:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _embedding_model


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def _check_with_embeddings(rule: dict, clauses: list[dict]) -> dict:
    if not clauses:
        return {
            "status": "FAIL", "severity": "High",
            "finding": "No clauses could be extracted from the contract.",
            "excerpt": "N/A",
            "recommendation": "Ensure the contract file is readable and contains text.",
        }

    model = _get_embedding_model()
    rule_text = rule.get("prompt", rule.get("name", ""))
    clause_texts = [c.get("text", "") for c in clauses]

    all_embeddings = list(model.embed([rule_text] + clause_texts))
    rule_emb = all_embeddings[0]
    clause_embs = all_embeddings[1:]

    scores = [_cosine_sim(rule_emb, ce) for ce in clause_embs]
    best_idx = int(max(range(len(scores)), key=lambda i: scores[i]))
    best_score = scores[best_idx]
    best_clause = clauses[best_idx]
    excerpt = best_clause.get("text", "")[:300].strip() or "N/A"
    matched_title = best_clause.get("title", best_clause.get("clause_id", ""))

    if best_score >= 0.45:
        return {
            "status": "PASS", "severity": "Low",
            "finding": f"Contract addresses this requirement — matched clause: '{matched_title}' (similarity: {best_score:.2f}).",
            "excerpt": excerpt,
            "recommendation": "No action required.",
        }

    if best_score >= 0.25:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": f"Partial coverage found (similarity: {best_score:.2f}). Closest clause: '{matched_title}'. The requirement may not be fully addressed.",
            "excerpt": excerpt,
            "recommendation": "Review the identified clause for completeness against this custom requirement.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": f"No semantically relevant clause found for this requirement (similarity: {best_score:.2f}).",
        "excerpt": "N/A",
        "recommendation": "Add explicit contractual provisions addressing this custom compliance requirement.",
    }


# ── Service ────────────────────────────────────────────────────────────────────

class OpenAIService:

    async def check_rule(self, rule: dict, clauses: list[dict]) -> dict:
        if rule.get("_custom"):
            result = _check_with_embeddings(rule, clauses)
            return {
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "directive": rule["directive"],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                **result,
            }

        contract_text = "\n\n".join(c.get("text", "") for c in clauses)
        try:
            result, prompt_tokens, completion_tokens = await _call_gpt(rule, contract_text)
            result.setdefault("status", "WARNING")
            result.setdefault("severity", "Medium")
            result.setdefault("finding", "Unable to assess compliance.")
            result.setdefault("excerpt", "N/A")
            result.setdefault("recommendation", "Manual review required.")
        except Exception as exc:
            result = {
                "status": "WARNING",
                "severity": "Medium",
                "finding": f"Compliance check could not be completed: {exc}",
                "excerpt": "N/A",
                "recommendation": "Review this rule manually.",
            }
            prompt_tokens, completion_tokens = 0, 0

        return {
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "directive": rule["directive"],
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            **result,
        }
