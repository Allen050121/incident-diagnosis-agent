"""API router for diagnosis endpoints"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class DiagnosisRequest(BaseModel):
    incident_id: str
    service: str
    endpoint: str | None = None
    alert_type: str
    value: float
    threshold: float
    started_at: str


class DiagnosisResponse(BaseModel):
    task_id: str
    status: str
    message: str


@router.post("/diagnose", response_model=DiagnosisResponse)
async def start_diagnosis(request: DiagnosisRequest):
    """Start a new diagnosis task"""
    # TODO: Implement task creation and Redis Streams publishing
    return DiagnosisResponse(
        task_id=f"TASK-{request.incident_id}",
        status="QUEUED",
        message="Diagnosis task created"
    )


@router.get("/diagnosis/{task_id}")
async def get_diagnosis_status(task_id: str):
    """Get diagnosis task status"""
    # TODO: Implement status retrieval
    return {"task_id": task_id, "status": "INVESTIGATING"}
