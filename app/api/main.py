from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import review, report, upload

app = FastAPI(
    title="German Contract Compliance Checker",
    description="Multi-agent AI pipeline for real-time German regulatory compliance review.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(review.router)
app.include_router(report.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
