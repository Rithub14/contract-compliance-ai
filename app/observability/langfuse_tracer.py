import logging
import uuid

logger = logging.getLogger(__name__)


class LangfuseTracer:
    """
    Stub that mirrors the Langfuse Python SDK interface.

    To go live: install langfuse, set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY /
    LANGFUSE_HOST, then replace each method body with the real SDK call.

    Real SDK reference:
        client = langfuse.Langfuse()
        trace  = client.trace(name=..., input=..., metadata=...)
        span   = trace.span(name=..., input=..., output=..., metadata=...)
        client.score(trace_id=..., name=..., value=..., comment=...)
    """

    def trace(self, name: str, input_data: dict, metadata: dict | None = None) -> str:  # noqa: ARG002
        """Creates a top-level pipeline trace. Returns trace_id."""
        trace_id = f"mock-{uuid.uuid4().hex[:10]}"
        logger.debug("[Langfuse] TRACE  %s  name=%s", trace_id, name)
        return trace_id

    def span(
        self,
        trace_id: str,
        name: str,
        input_data: dict,        # noqa: ARG002
        output: dict,            # noqa: ARG002
        latency_ms: float = 0.0,
        tokens: dict | None = None,
    ) -> str:
        """Creates a child span on an existing trace. Returns span_id."""
        span_id = f"mock-{uuid.uuid4().hex[:10]}"
        logger.debug(
            "[Langfuse] SPAN   %s/%s  name=%-40s  latency=%.0fms  tokens=%s",
            trace_id, span_id, name, latency_ms, tokens,
        )
        return span_id

    def generation(
        self,
        trace_id: str,
        name: str,
        model: str,
        input_text: str,          # noqa: ARG002
        output_text: str,         # noqa: ARG002
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> str:
        """Records an LLM generation (input/output/token counts) on a trace."""
        gen_id = f"mock-{uuid.uuid4().hex[:10]}"
        total_tokens = prompt_tokens + completion_tokens
        logger.debug(
            "[Langfuse] GEN    %s/%s  name=%s  model=%s  tokens=%d",
            trace_id, gen_id, name, model, total_tokens,
        )
        return gen_id

    def score(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: str | None = None,
    ) -> None:
        """Logs a named numeric evaluation score on a trace (0.0–1.0 convention)."""
        logger.debug(
            "[Langfuse] SCORE  %s  %-40s = %.3f  %s",
            trace_id, name, value, comment or "",
        )

    def flush(self) -> None:
        """Flushes buffered events to Langfuse (no-op for stub)."""
        pass


tracer = LangfuseTracer()
