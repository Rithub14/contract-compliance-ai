import io
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File
import pypdf

from app.api.job_store import job_store
from app.api.models import UploadResponse
from app.services.blob_service import MockBlobService
from app.services.custom_rules_service import parse_compliance_doc

router = APIRouter()
_blob = MockBlobService()

_ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


def _extract_text(content: bytes, content_type: str) -> str:
    if content_type == "application/pdf":
        reader = pypdf.PdfReader(io.BytesIO(content))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return content.decode(errors="replace")


@router.post("/upload", response_model=UploadResponse)
async def upload_contract(
    file: UploadFile = File(...),
    compliance_file: UploadFile = File(None),
):
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and TXT files are accepted.")

    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit.")

    custom_rules: list[dict] = []
    if compliance_file:
        compliance_content = await compliance_file.read()
        custom_rules = parse_compliance_doc(compliance_content, compliance_file.content_type or "text/plain")

    job_id = str(uuid.uuid4())
    blob_url = await _blob.upload(job_id, file.filename or "contract", content)
    raw_text = _extract_text(content, file.content_type or "")

    job_store[job_id] = {
        "job_id": job_id,
        "filename": file.filename,
        "blob_url": blob_url,
        "raw_text": raw_text,
        "custom_rules": custom_rules,
        "status": "queued",
        "result": None,
    }

    return UploadResponse(
        job_id=job_id,
        status="queued",
        filename=file.filename or "",
        custom_rule_count=len(custom_rules),
    )
