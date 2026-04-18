from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.api.job_store import job_store

router = APIRouter()


@router.get("/report/{job_id}")
async def get_report(job_id: str):
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    job = job_store[job_id]
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail=f"Job is not complete (status: {job['status']}).")

    return JSONResponse(content={"job_id": job_id, **job["result"]})
