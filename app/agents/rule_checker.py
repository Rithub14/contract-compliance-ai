import asyncio
import time

from langchain_core.runnables import RunnableConfig

from app.services.openai_service import MockOpenAIService
from app.services.judge_service import MockJudgeService
from app.observability.langfuse_tracer import tracer

_openai = MockOpenAIService()
_judge = MockJudgeService()


async def rule_checker_node(state: dict, config: RunnableConfig) -> dict:
    """Checks one EU rule against extracted clauses and streams the result to the SSE queue."""
    rule: dict = state["rule"]
    clauses: list[dict] = state.get("clauses", [])
    cfg = config.get("configurable", {})

    t0 = time.monotonic()
    result = await _openai.check_rule(rule, clauses)
    latency_ms = (time.monotonic() - t0) * 1000

    evaluation = await _judge.evaluate(rule, clauses, result)
    result["evaluation"] = evaluation

    trace_id: str = cfg.get("trace_id", state.get("job_id", "unknown"))
    tracer.span(
        trace_id,
        name=f"rule_checker.{rule['id']}",
        input_data={"rule_id": rule["id"], "clause_count": len(clauses)},
        output={"status": result["status"], "severity": result.get("severity")},
        latency_ms=latency_ms,
    )
    tracer.score(trace_id, f"accuracy.{rule['id']}", evaluation["accuracy_score"])
    tracer.score(trace_id, f"completeness.{rule['id']}", evaluation["completeness_score"])

    queue: asyncio.Queue | None = cfg.get("queue")
    if queue is not None:
        await queue.put({"type": "rule_result", "data": result})

    return {"rule_results": [result]}
