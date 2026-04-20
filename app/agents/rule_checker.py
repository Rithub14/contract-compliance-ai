import asyncio
import time

from langchain_core.runnables import RunnableConfig

from app.services.openai_service import OpenAIService
from app.services.judge_service import evaluate as judge_evaluate
from app.observability.langfuse_tracer import tracer

_openai = OpenAIService()


async def rule_checker_node(state: dict, config: RunnableConfig) -> dict:
    rule: dict = state["rule"]
    clauses: list[dict] = state.get("clauses", [])
    cfg = config.get("configurable", {})

    t0 = time.monotonic()
    result = await _openai.check_rule(rule, clauses)
    latency_ms = (time.monotonic() - t0) * 1000

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

    queue: asyncio.Queue | None = cfg.get("queue")
    if queue is not None:
        await queue.put({"type": "rule_result", "data": result})

    return {"rule_results": [result]}
