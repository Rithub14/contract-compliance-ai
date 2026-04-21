from app.services.doc_intel_service import DocIntelService

_doc_intel = DocIntelService()


async def extractor_node(state: dict) -> dict:
    raw_text = state.get("raw_text", "")
    clauses = await _doc_intel.extract_clauses(raw_text.encode())
    return {"clauses": clauses}
