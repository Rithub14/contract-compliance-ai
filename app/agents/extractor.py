from app.services.doc_intel_service import MockDocIntelService

_doc_intel = MockDocIntelService()


async def extractor_node(state: dict) -> dict:
    """Calls Document Intelligence (mock) to extract structured clauses."""
    raw_text = state.get("raw_text", "")
    clauses = await _doc_intel.extract_clauses(raw_text.encode())
    return {"clauses": clauses}
