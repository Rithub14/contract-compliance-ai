import asyncio
import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.job_store import job_store
from app.agents.graph import run_graph

router = APIRouter()


@router.get("/review/stream/{job_id}")
async def stream_review(job_id: str):
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    job = job_store[job_id]
    job["status"] = "running"
    queue: asyncio.Queue = asyncio.Queue()

    async def event_generator():
        task = asyncio.create_task(
            run_graph(job_id, job["raw_text"], queue, custom_rules=job.get("custom_rules"))
        )

        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=60.0)

                if event["type"] == "done":
                    job["status"] = "done"
                    yield {"event": "done", "data": "{}"}
                    break

                if event["type"] == "error":
                    job["status"] = "failed"
                    yield {"event": "error", "data": json.dumps(event["data"])}
                    break

                if event["type"] == "rule_result":
                    yield {"event": "rule_result", "data": json.dumps(event["data"])}

                if event["type"] == "final":
                    job["result"] = event["data"]
                    yield {"event": "final", "data": json.dumps(event["data"])}

        except asyncio.TimeoutError:
            job["status"] = "failed"
            yield {"event": "error", "data": json.dumps({"message": "Pipeline timed out."})}
        finally:
            task.cancel()

    return EventSourceResponse(event_generator())


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return {"job_id": job_id, "status": job_store[job_id]["status"]}
