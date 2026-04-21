import asyncio
import time

from langchain_core.runnables import RunnableConfig

from app.services.openai_service import OpenAIService
from app.services.judge_service import evaluate as judge_evaluate
from app.observability.langfuse_tracer import tracer

_openai = OpenAIService()


_STATUTORY_CATEGORIES = {"STATUTORY", "ORGANISATIONAL"}


def _enforce_evidence_rule(result: dict, rule: dict) -> dict:
    if result.get("is_system_error"):
        return result

    excerpt = result.get("excerpt", "N/A").strip()
    no_excerpt = excerpt in ("N/A", "", "n/a")
    status = result.get("status")
    category = (rule.get("category") or "").upper()
    justification = (result.get("justification_type") or "").lower()

    if no_excerpt and status == "FAIL":
        result["status"] = "UNCERTAIN"
        result["severity"] = "Low"
        result["finding"] = (
            "[Downgraded from FAIL — no supporting excerpt found] " + result.get("finding", "")
        )
        result["recommendation"] = (
            "Manual review recommended: no specific contract text was identified to support this finding. "
            + result.get("recommendation", "")
        )
        result["justification_type"] = "none"
        return result

    if no_excerpt and status == "PASS" and category not in _STATUTORY_CATEGORIES and justification != "statutory":
        result["status"] = "UNCERTAIN"
        result["severity"] = "Low"
        result["finding"] = (
            "[Downgraded from PASS — no supporting excerpt and rule is not statutory] "
            + result.get("finding", "")
        )
        result["recommendation"] = (
            "Manual review recommended: PASS was claimed without a verbatim excerpt or statutory justification. "
            + result.get("recommendation", "")
        )
        result["justification_type"] = "none"

    return result


async def rule_checker_node(state: dict, config: RunnableConfig) -> dict:
    rule: dict = state["rule"]
    clauses: list[dict] = state.get("clauses", [])
    cfg = config.get("configurable", {})

    metadata: dict = state.get("contract_metadata", {})

    t0 = time.monotonic()
    result = await _openai.check_rule(rule, clauses, metadata=metadata)
    result = _enforce_evidence_rule(result, rule)
    latency_ms = (time.monotonic() - t0) * 1000

    if result.get("is_system_error"):
        queue: asyncio.Queue | None = cfg.get("queue")
        if queue is not None:
            await queue.put({"type": "rule_result", "data": result})
        return {"rule_results": [result]}

    evaluation = await judge_evaluate(rule, result)
    result["evaluation"] = evaluation

    trace_id: str = cfg.get("trace_id", state.get("job_id", "unknown"))
    tracer.span(
        trace_id,
        name=f"rule_checker.{rule['id']}",
        input_data={"rule_id": rule["id"], "clause_count": len(clauses)},
        output={"status": result["status"], "severity": result.get("severity")},
        latency_ms=latency_ms,
        tokens={
            "prompt": result.pop("prompt_tokens", 0),
            "completion": result.pop("completion_tokens", 0),
        },
    )
    tracer.score(trace_id, f"accuracy.{rule['id']}", evaluation["accuracy_score"])
    tracer.score(trace_id, f"completeness.{rule['id']}", evaluation["completeness_score"])

    queue = cfg.get("queue")
    if queue is not None:
        await queue.put({"type": "rule_result", "data": result})

    return {"rule_results": [result]}
