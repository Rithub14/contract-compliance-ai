import logging
import uuid

logger = logging.getLogger(__name__)


class LangfuseTracer:
    def trace(self, name: str, input_data: dict, metadata: dict | None = None) -> str:
        trace_id = f"trace-{uuid.uuid4().hex[:10]}"
        logger.debug("[Langfuse] TRACE %s name=%s", trace_id, name)
        return trace_id

    def span(
        self,
        trace_id: str,
        name: str,
        input_data: dict,
        output: dict,
        latency_ms: float = 0.0,
        tokens: dict | None = None,
    ) -> str:
        span_id = f"span-{uuid.uuid4().hex[:10]}"
        logger.debug("[Langfuse] SPAN %s/%s name=%s latency=%.0fms tokens=%s", trace_id, span_id, name, latency_ms, tokens)
        return span_id

    def score(self, trace_id: str, name: str, value: float, comment: str | None = None) -> None:
        logger.debug("[Langfuse] SCORE %s %s=%.3f %s", trace_id, name, value, comment or "")

    def flush(self) -> None:
        pass


tracer = LangfuseTracer()
