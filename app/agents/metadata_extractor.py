import asyncio
import json
import random
import re

from openai import AsyncOpenAI, RateLimitError

from app.config.settings import settings

_MAX_RETRIES = 6
_BASE_BACKOFF = 1.0

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key, max_retries=0)
    return _client


_SYSTEM_PROMPT = """You are a German contract analyst. Extract structured metadata from the contract text.
Be precise and conservative. If a piece of information is not clearly present, use null or false.
Do not guess or infer beyond what is written."""

_USER_PROMPT = """Extract metadata from this contract text.

Contract text:
{contract_text}

Respond with this exact JSON and nothing else:
{{
  "contract_subtype": "permanent | fixed-term | student | apprenticeship | part-time | unknown",
  "has_cross_border_element": true or false,
  "tarifvertrag_referenced": true or false,
  "collective_agreement_name": "name as string, or null",
  "salary_stated": true or false,
  "salary_value": "e.g. 3200 EUR/month, or null",
  "salary_excerpt": "verbatim quote from contract stating the salary, or null",
  "working_hours_stated": true or false,
  "working_hours_value": "e.g. 40h/week, or null",
  "working_hours_excerpt": "verbatim quote from contract stating working hours, or null",
  "vacation_days_stated": true or false,
  "vacation_days_value": "e.g. 30 days/year, or null",
  "vacation_days_excerpt": "verbatim quote from contract stating annual leave, or null",
  "probation_period_stated": true or false,
  "probation_value": "e.g. 6 months, or null",
  "probation_excerpt": "verbatim quote from contract stating probation, or null",
  "data_protection_clause_present": true or false,
  "data_protection_excerpt": "verbatim quote of the data protection / Datenschutz clause, or null",
  "org_size_hint": "small (<50 employees) | large (>=50 employees) | unknown",
  "involves_personal_data_processing": true or false,
  "involves_it_services": true or false,
  "involves_physical_products": true or false,
  "involves_ai_systems": true or false,
  "involves_supply_chain": true or false,
  "involves_commercial_agent": true or false,
  "involves_digital_products": true or false,
  "involves_online_platform": true or false
}}"""

# Maps CONDITIONAL rule IDs to a function that reads metadata and returns True = keep rule
# Default False means: only include if metadata explicitly confirms it applies
# Default True means: include unless metadata explicitly rules it out (common/safe default)
_APPLICABILITY_CONDITIONS: dict[str, any] = {
    # Employment
    "posted_workers":    lambda m: m.get("has_cross_border_element", False),
    "fixed_term":        lambda m: m.get("contract_subtype") == "fixed-term",
    "whistleblower":     lambda m: m.get("org_size_hint") == "large",
    # Vendor — default True for high-prevalence rules, False for narrow ones
    "gdpr_vendor":       lambda m: m.get("involves_personal_data_processing", True),
    "nis2":              lambda m: m.get("involves_it_services", True),
    "product_liability": lambda m: m.get("involves_physical_products", True),
    "csddd":             lambda m: m.get("involves_supply_chain", True),
    "ai_act":            lambda m: m.get("involves_ai_systems", False),
    "cyber_resilience":  lambda m: m.get("involves_digital_products", False),
    "data_act":          lambda m: m.get("involves_digital_products", False),
    "dsa":               lambda m: m.get("involves_online_platform", False),
    "commercial_agents": lambda m: m.get("involves_commercial_agent", False),
}


def _parse_json(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    return json.loads(cleaned)


_FALLBACK_METADATA: dict = {
    # _extraction_succeeded=False signals to downstream code that this is
    # unreliable fallback data — no metadata context will be injected into prompts
    "_extraction_succeeded": False,
    "contract_subtype": "unknown",
    "has_cross_border_element": False,
    "tarifvertrag_referenced": False,
    "collective_agreement_name": None,
    "salary_stated": False,
    "salary_value": None,
    "salary_excerpt": None,
    "working_hours_stated": False,
    "working_hours_value": None,
    "working_hours_excerpt": None,
    "vacation_days_stated": False,
    "vacation_days_value": None,
    "vacation_days_excerpt": None,
    "probation_period_stated": False,
    "probation_value": None,
    "probation_excerpt": None,
    "data_protection_clause_present": False,
    "data_protection_excerpt": None,
    "org_size_hint": "unknown",
    "involves_personal_data_processing": True,
    "involves_it_services": True,
    "involves_physical_products": True,
    "involves_ai_systems": False,
    "involves_supply_chain": True,
    "involves_commercial_agent": False,
    "involves_digital_products": False,
    "involves_online_platform": False,
}


async def _extract_metadata(contract_text: str) -> dict:
    for attempt in range(_MAX_RETRIES):
        try:
            response = await _get_client().chat.completions.create(
                model=settings.openai_model,
                response_format={"type": "json_object"},
                temperature=0.0,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _USER_PROMPT.format(
                        contract_text=contract_text[:12000],
                    )},
                ],
            )
            result = _parse_json(response.choices[0].message.content)
            result["_extraction_succeeded"] = True
            return result
        except RateLimitError:
            if attempt == _MAX_RETRIES - 1:
                return _FALLBACK_METADATA.copy()
            delay = _BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(delay)
        except Exception:
            return _FALLBACK_METADATA.copy()
    return _FALLBACK_METADATA.copy()


def _filter_rules(active_rules: list[dict], metadata: dict) -> list[dict]:
    """Remove CONDITIONAL rules that metadata confirms do not apply."""
    filtered = []
    for rule in active_rules:
        if rule.get("category") != "CONDITIONAL":
            filtered.append(rule)
            continue
        condition = _APPLICABILITY_CONDITIONS.get(rule["id"])
        if condition is None or condition(metadata):
            filtered.append(rule)
        # else: rule is silently dropped — no NOT_APPLICABLE card needed
    return filtered


async def metadata_extractor_node(state: dict) -> dict:
    raw_text: str = state.get("raw_text", "")
    active_rules: list[dict] = state.get("active_rules", [])

    metadata = await _extract_metadata(raw_text)
    filtered_rules = _filter_rules(active_rules, metadata)

    return {
        "contract_metadata": metadata,
        "active_rules": filtered_rules,
    }
