from pydantic import BaseModel


class UploadResponse(BaseModel):
    job_id: str
    status: str
    filename: str
    custom_rule_count: int = 0


class StatusResponse(BaseModel):
    job_id: str
    status: str


class ReportResponse(BaseModel):
    job_id: str
    contract_type: str
    collar_type: str
    overall_score: float
    risk_level: str
    report: dict
