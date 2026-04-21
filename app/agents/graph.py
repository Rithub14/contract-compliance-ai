import asyncio
import operator
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from app.agents.classifier import classifier_node
from app.agents.extractor import extractor_node
from app.agents.metadata_extractor import metadata_extractor_node
from app.agents.rule_checker import rule_checker_node
from app.agents.scorer import scorer_node
from app.agents.report_writer import report_writer_node
from app.observability.langfuse_tracer import tracer


class ReviewState(TypedDict):
    job_id: str
    contract_type: str
    collar_type: str
    raw_text: str
    clauses: list[dict]
    custom_rules: list[dict]
    active_rules: list[dict]
    contract_metadata: dict
    rule_results: Annotated[list[dict], operator.add]
    overall_score: float
    risk_level: str
    report: dict


def _route_rule_checkers(state: ReviewState) -> list[Send]:
    return [
        Send(
            "check_rule",
            {
                "job_id": state["job_id"],
                "rule": rule,
                "clauses": state["clauses"],
                "contract_metadata": state.get("contract_metadata", {}),
            },
        )
        for rule in state["active_rules"]
    ]


def _build_graph() -> StateGraph:
    graph = StateGraph(ReviewState)

    graph.add_node("classifier", classifier_node)
    graph.add_node("extractor", extractor_node)
    graph.add_node("metadata_extractor", metadata_extractor_node)
    graph.add_node("check_rule", rule_checker_node)
    graph.add_node("scorer", scorer_node)
    graph.add_node("report_writer", report_writer_node)

    graph.add_edge(START, "classifier")
    graph.add_edge("classifier", "extractor")
    graph.add_edge("extractor", "metadata_extractor")
    graph.add_conditional_edges("metadata_extractor", _route_rule_checkers, ["check_rule"])
    graph.add_edge("check_rule", "scorer")
    graph.add_edge("scorer", "report_writer")
    graph.add_edge("report_writer", END)

    return graph.compile()


compiled_graph = _build_graph()


async def run_graph(job_id: str, raw_text: str, queue: asyncio.Queue, custom_rules: list[dict] | None = None) -> None:
    """Execute the full review pipeline, pushing SSE events into *queue* as rules complete."""
    initial_state: ReviewState = {
        "job_id": job_id,
        "contract_type": "",
        "collar_type": "",
        "raw_text": raw_text,
        "clauses": [],
        "custom_rules": custom_rules or [],
        "active_rules": [],
        "contract_metadata": {},
        "rule_results": [],
        "overall_score": 0.0,
        "risk_level": "",
        "report": {},
    }

    trace_id = tracer.trace(
        name="contract_compliance_review",
        input_data={"job_id": job_id, "text_length": len(raw_text)},
    )
    config = {"configurable": {"queue": queue, "trace_id": trace_id}}

    try:
        final_state = await compiled_graph.ainvoke(initial_state, config=config)

        tracer.score(trace_id, "overall_compliance_score", final_state["overall_score"] / 100)
        risk_numeric = {"Low": 0.9, "Medium": 0.6, "High": 0.3, "Critical": 0.1}.get(
            final_state["risk_level"], 0.5
        )
        tracer.score(trace_id, "risk_level_numeric", risk_numeric)
        tracer.flush()

        await queue.put(
            {
                "type": "final",
                "data": {
                    "overall_score": final_state["overall_score"],
                    "risk_level": final_state["risk_level"],
                    "contract_type": final_state["contract_type"],
                    "collar_type": final_state["collar_type"],
                    "report": final_state["report"],
                },
            }
        )
    except Exception as exc:
        await queue.put({"type": "error", "data": {"message": str(exc)}})
    finally:
        await queue.put({"type": "done", "data": {}})
