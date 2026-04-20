import json
import re

from openai import AsyncOpenAI

from app.config.settings import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


_SYSTEM_PROMPT = """You are a compliance quality auditor reviewing AI-generated contract findings.
Evaluate whether the finding is well-supported, correctly calibrated, and grounded in evidence.
Respond with valid JSON only."""

_USER_PROMPT = """Rule: {rule_name} ({directive})
Status: {status} | Severity: {severity}
Finding: {finding}
Excerpt: {excerpt}

Evaluate this finding and respond with this exact JSON:
{{
  "accuracy_score": <0.0 to 1.0 — is the finding supported by the excerpt?>,
  "completeness_score": <0.0 to 1.0 — does it cite specific articles or directives?>,
  "severity_calibration": "correct or miscalibrated",
  "false_positive_risk": "low or medium or high",
  "judge_note": "brief note on finding quality"
}}"""


def _parse_json(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    return json.loads(cleaned)


async def evaluate(rule: dict, finding: dict) -> dict:
    try:
        response = await _get_client().chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            temperature=0.1,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _USER_PROMPT.format(
                    rule_name=finding.get("rule_name", rule.get("name", "")),
                    directive=finding.get("directive", rule.get("directive", "")),
                    status=finding.get("status", ""),
                    severity=finding.get("severity", ""),
                    finding=finding.get("finding", ""),
                    excerpt=finding.get("excerpt", "N/A"),
                )},
            ],
        )
        result = _parse_json(response.choices[0].message.content)
        result.setdefault("accuracy_score", 0.5)
        result.setdefault("completeness_score", 0.5)
        result.setdefault("severity_calibration", "correct")
        result.setdefault("false_positive_risk", "medium")
        result.setdefault("judge_note", "")
        return result
    except Exception:
        return {
            "accuracy_score": 0.5,
            "completeness_score": 0.5,
            "severity_calibration": "correct",
            "false_positive_risk": "medium",
            "judge_note": "Evaluation unavailable.",
        }
