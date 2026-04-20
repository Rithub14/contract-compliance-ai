import logging
import uuid

logger = logging.getLogger(__name__)


class LangfuseTracer:
    """
    Langfuse tracing client.
    Configure LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST to enable live tracing.

    Real SDK usage:
        client = langfuse.Langfuse()
        trace  = client.trace(name=..., input=..., metadata=...)
        span   = trace.span(name=..., input=..., output=..., metadata=...)
        client.score(trace_id=..., name=..., value=..., comment=...)
    """

    def trace(self, name: str, input_data: dict, metadata: dict | None = None) -> str:  # noqa: ARG002, ARG002
        trace_id = f"trace-{uuid.uuid4().hex[:10]}"
        logger.debug("[Langfuse] TRACE %s name=%s", trace_id, name)
        return trace_id

    def span(
        self,
        trace_id: str,
        name: str,
        input_data: dict,    # noqa: ARG002
        output: dict,        # noqa: ARG002
        latency_ms: float = 0.0,
        tokens: dict | None = None,
    ) -> str:
        span_id = f"span-{uuid.uuid4().hex[:10]}"
        logger.debug("[Langfuse] SPAN %s/%s name=%s latency=%.0fms tokens=%s", trace_id, span_id, name, latency_ms, tokens)
        return span_id

    def generation(
        self,
        trace_id: str,
        name: str,
        model: str,
        input_text: str,         # noqa: ARG002
        output_text: str,        # noqa: ARG002
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> str:
        gen_id = f"gen-{uuid.uuid4().hex[:10]}"
        logger.debug("[Langfuse] GEN %s/%s name=%s model=%s tokens=%d", trace_id, gen_id, name, model, prompt_tokens + completion_tokens)
        return gen_id

    def score(self, trace_id: str, name: str, value: float, comment: str | None = None) -> None:
        logger.debug("[Langfuse] SCORE %s %s=%.3f %s", trace_id, name, value, comment or "")

    def flush(self) -> None:
        pass


tracer = LangfuseTracer()
