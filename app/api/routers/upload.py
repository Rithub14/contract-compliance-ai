import base64
import io
import uuid

import fitz  # PyMuPDF
from fastapi import APIRouter, HTTPException, UploadFile, File
from openai import AsyncOpenAI
import pypdf

from app.api.job_store import job_store
from app.api.models import UploadResponse
from app.config.settings import settings
from app.services.blob_service import BlobService
from app.services.custom_rules_service import parse_compliance_doc

router = APIRouter()
_blob = BlobService()

_ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB
_MIN_TEXT_CHARS = 200  # below this, assume scanned PDF and use vision OCR
_MAX_OCR_PAGES = 20


async def _ocr_pdf_with_vision(content: bytes) -> str:
    doc = fitz.open(stream=content, filetype="pdf")
    image_parts: list[dict] = []
    for i, page in enumerate(doc):
        if i >= _MAX_OCR_PAGES:
            break
        pix = page.get_pixmap(dpi=150)
        b64 = base64.b64encode(pix.tobytes("png")).decode()
        image_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "auto"},
        })

    client = AsyncOpenAI(api_key=settings.openai_api_key, max_retries=6)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Extract all text from these contract pages verbatim. "
                        "Preserve paragraph breaks and section headings. "
                        "Output only the extracted text, nothing else."
                    ),
                },
                *image_parts,
            ],
        }],
        max_tokens=8192,
    )
    return response.choices[0].message.content or ""


async def _extract_text(content: bytes, content_type: str) -> str:
    if content_type == "application/pdf":
        reader = pypdf.PdfReader(io.BytesIO(content))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        if len(text.strip()) < _MIN_TEXT_CHARS:
            text = await _ocr_pdf_with_vision(content)
        return text
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
    raw_text = await _extract_text(content, file.content_type or "")

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
