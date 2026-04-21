import asyncio
import json
import random
import re

import numpy as np
from fastembed import TextEmbedding
from openai import AsyncOpenAI, RateLimitError

from app.config.settings import settings

_client: AsyncOpenAI | None = None
_semaphore = asyncio.Semaphore(2)
_MAX_RETRIES = 6
_BASE_BACKOFF = 1.0


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key, max_retries=0)
    return _client



_SYSTEM_PROMPT = """You are a specialist German employment and vendor contract compliance analyst.

## Valid statuses
- PASS       — explicitly compliant, or covered by statute/Tarifvertrag/reference
- WARNING    — partial coverage, ambiguous language, or external reference that should be verified
- FAIL       — contract actively violates a requirement, OR a MUST_BE_EXPLICIT requirement is entirely absent with no statutory fallback
- UNCERTAIN  — the requirement may apply but there is insufficient evidence in the contract text to assess
- NOT_APPLICABLE — the rule does not apply to this contract type or context

## HARD RULES — these override everything else

1. EVIDENCE RULE: If you cannot find a relevant excerpt in the contract text, you MUST set status to
   UNCERTAIN or NOT_APPLICABLE. You are NEVER allowed to return FAIL when excerpt is N/A.
   A missing clause is not proof of non-compliance.

2. STATUTORY RULES: For rules categorised as STATUTORY (AGG, BEEG, MuSchG, KSchG etc.):
   These rights apply by German law regardless of contract wording.
   PASS unless the contract ACTIVELY violates the right with an explicit clause.
   Absence of a mention = PASS, not FAIL.

3. ORGANISATIONAL RULES: For rules categorised as ORGANISATIONAL (e.g. HinSchG whistleblower):
   These are obligations on the employing organisation, not contract clause requirements.
   PASS unless the contract contains a clause that ACTIVELY conflicts with the requirement.

4. CONDITIONAL RULES: For rules categorised as CONDITIONAL (posted_workers, fixed_term, AI Act etc.):
   If the contract contains no evidence that the condition applies (no cross-border posting,
   no AI systems, no fixed end date), return NOT_APPLICABLE.

5. CAN_BE_IMPLICIT RULES: These are satisfied by statute, Tarifvertrag, or a policy reference.
   FAIL only if the contract contains a clause that ACTIVELY violates the requirement.

6. NO HALLUCINATION: Do not invent compliance problems. If you are unsure, use UNCERTAIN.
   Every FAIL must be grounded in a specific excerpt that shows an active violation.

7. JUSTIFICATION: Every result must include justification_type, one of:
   - "excerpt"             — PASS/WARNING/FAIL backed by a verbatim quote from the contract
   - "metadata_reference"  — PASS backed by a pre-extracted fact surfaced in the Contract context block
     (you must still copy the fact's excerpt into the excerpt field verbatim)
   - "statutory"           — PASS for STATUTORY/ORGANISATIONAL rules where the right applies by German law
     regardless of contract wording. The finding MUST explicitly state
     "governed by statutory law — no explicit clause required" (or close paraphrase) and cite the statute.
   - "none"                — only valid with status UNCERTAIN or NOT_APPLICABLE

8. UNCERTAIN findings must name the specific missing fact (e.g. "no annual leave value stated",
   "no salary figure found"), not a generic "insufficient information".

## Grounding
- Recognise both English and German legal terms (Probezeit, Kündigung, Tarifvertrag, DSGVO,
  Datenschutz, Befristung, Elternzeit, Gehalt, Vergütung, Arbeitsstunden, Urlaub, Urlaubstage, etc.)
- excerpt must be a verbatim quote from the contract. If no relevant text exists, set excerpt to N/A
  — and then status MUST be UNCERTAIN or NOT_APPLICABLE, never FAIL.
- If the Contract context block lists an excerpt for a fact you're evaluating, REUSE that excerpt
  verbatim rather than saying the information is missing.
- Severity must match status: FAIL → High or Critical, WARNING → Medium,
  PASS/UNCERTAIN/NOT_APPLICABLE → Low"""

_USER_PROMPT = """Directive: {directive}
Rule: {rule_name}
Rule category: {category}
Requirement: {rule_prompt}

{metadata_section}Contract text:
{contract_text}

Respond with this exact JSON and nothing else:
{{
  "status": "PASS or WARNING or FAIL or UNCERTAIN or NOT_APPLICABLE",
  "severity": "Low or Medium or High or Critical",
  "finding": "concise explanation grounded in the contract text, with legal reasoning",
  "excerpt": "exact verbatim quote from the contract above, or N/A",
  "recommendation": "specific action needed, or No action required",
  "justification_type": "excerpt or metadata_reference or statutory or none"
}}"""


def _build_metadata_section(metadata: dict) -> str:
    if not metadata or not metadata.get("_extraction_succeeded"):
        return ""

    lines = ["Contract context (pre-extracted facts — use these to avoid re-scanning):"]

    subtype = metadata.get("contract_subtype", "unknown")
    if subtype != "unknown":
        lines.append(f"- Contract type: {subtype}")

    if metadata.get("salary_stated"):
        lines.append(f"- Salary stated: {metadata.get('salary_value', 'yes, amount unclear')}")
        if metadata.get("salary_excerpt"):
            lines.append(f"  Excerpt: \"{metadata['salary_excerpt']}\"")
    else:
        lines.append("- Salary: not stated in contract")

    if metadata.get("working_hours_stated"):
        lines.append(f"- Working hours: {metadata.get('working_hours_value', 'yes, value unclear')}")
        if metadata.get("working_hours_excerpt"):
            lines.append(f"  Excerpt: \"{metadata['working_hours_excerpt']}\"")
    else:
        lines.append("- Working hours: not stated in contract")

    if metadata.get("vacation_days_stated"):
        lines.append(f"- Annual leave: {metadata.get('vacation_days_value', 'yes, days unclear')}")
        if metadata.get("vacation_days_excerpt"):
            lines.append(f"  Excerpt: \"{metadata['vacation_days_excerpt']}\"")
    else:
        lines.append("- Annual leave: not stated in contract")

    if metadata.get("probation_period_stated"):
        lines.append(f"- Probation period: {metadata.get('probation_value', 'yes, duration unclear')}")
        if metadata.get("probation_excerpt"):
            lines.append(f"  Excerpt: \"{metadata['probation_excerpt']}\"")
    else:
        lines.append("- Probation period: not stated in contract")

    if metadata.get("data_protection_clause_present"):
        lines.append("- Data protection clause: present")
        if metadata.get("data_protection_excerpt"):
            lines.append(f"  Excerpt: \"{metadata['data_protection_excerpt']}\"")
    else:
        lines.append("- Data protection clause: not detected")

    if metadata.get("tarifvertrag_referenced"):
        name = metadata.get("collective_agreement_name")
        lines.append(f"- Tarifvertrag referenced: {name or 'yes'}")
    else:
        lines.append("- Tarifvertrag: not referenced")

    if metadata.get("has_cross_border_element"):
        lines.append("- Cross-border / posting element: yes")

    return "\n".join(lines) + "\n\n"


def _parse_json_response(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    return json.loads(cleaned)


async def _call_gpt(rule: dict, contract_text: str, metadata: dict) -> tuple[dict, int, int]:
    async with _semaphore:
        return await _call_gpt_with_retry(rule, contract_text, metadata)


async def _call_gpt_with_retry(rule: dict, contract_text: str, metadata: dict) -> tuple[dict, int, int]:
    for attempt in range(_MAX_RETRIES):
        try:
            return await _call_gpt_inner(rule, contract_text, metadata)
        except RateLimitError:
            if attempt == _MAX_RETRIES - 1:
                raise
            delay = _BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(delay)


async def _call_gpt_inner(rule: dict, contract_text: str, metadata: dict) -> tuple[dict, int, int]:
    response = await _get_client().chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        temperature=0.1,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_PROMPT.format(
                directive=rule.get("directive", ""),
                rule_name=rule.get("name", ""),
                category=rule.get("category", "MUST_BE_EXPLICIT"),
                rule_prompt=rule.get("prompt", ""),
                metadata_section=_build_metadata_section(metadata),
                contract_text=contract_text[:15000],
            )},
        ],
    )
    result = _parse_json_response(response.choices[0].message.content)
    usage = response.usage
    return result, usage.prompt_tokens, usage.completion_tokens


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
            "justification_type": "excerpt",
        }

    if best_score >= 0.25:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": f"Partial coverage found (similarity: {best_score:.2f}). Closest clause: '{matched_title}'. The requirement may not be fully addressed.",
            "excerpt": excerpt,
            "recommendation": "Review the identified clause for completeness against this custom requirement.",
            "justification_type": "excerpt",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": f"No semantically relevant clause found for this requirement (similarity: {best_score:.2f}).",
        "excerpt": "N/A",
        "recommendation": "Add explicit contractual provisions addressing this custom compliance requirement.",
        "justification_type": "none",
    }


class OpenAIService:

    async def check_rule(self, rule: dict, clauses: list[dict], metadata: dict | None = None) -> dict:
        if rule.get("_custom"):
            result = _check_with_embeddings(rule, clauses)
            return {
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "directive": rule["directive"],
                "category": rule.get("category", "MUST_BE_EXPLICIT"),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                **result,
            }

        contract_text = "\n\n".join(c.get("text", "") for c in clauses)
        try:
            result, prompt_tokens, completion_tokens = await _call_gpt(rule, contract_text, metadata or {})
            result.setdefault("status", "WARNING")
            result.setdefault("severity", "Medium")
            result.setdefault("finding", "Unable to assess compliance.")
            result.setdefault("excerpt", "N/A")
            result.setdefault("recommendation", "Manual review required.")
            result.setdefault("justification_type", "none")
        except Exception as exc:
            return {
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "directive": rule["directive"],
                "category": rule.get("category", ""),
                "status": "ERROR",
                "severity": "Low",
                "finding": "System error — manual review required.",
                "excerpt": "N/A",
                "recommendation": "Re-run the compliance check for this rule.",
                "justification_type": "none",
                "is_system_error": True,
                "_error_detail": str(exc),
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }

        return {
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "directive": rule["directive"],
            "category": rule.get("category", ""),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            **result,
        }
