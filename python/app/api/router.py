"""API router for diagnosis endpoints"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent.service import create_agent_with_fake_tools, parse_incident
from app.domain.incident import DiagnosisReport

router = APIRouter()


class DiagnosisRequest(BaseModel):
    incident_id: str
    service: str
    endpoint: str | None = None
    alert_type: str
    value: float
    threshold: float
    started_at: str


class HypothesisResponse(BaseModel):
    rank: int
    cause_code: str
    confidence: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    reasoning_summary: str


class DiagnosisResponse(BaseModel):
    incident_id: str
    status: str
    top_causes: list[HypothesisResponse]
    recommended_actions: list[str]
    missing_evidence: list[str]
    tool_failures: list[str]
    evidence_ids: list[str]
    investigation_steps: int
    total_tool_calls: int


@router.post("/diagnose", response_model=DiagnosisResponse)
async def start_diagnosis(request: DiagnosisRequest):
    """Start a synchronous diagnosis - runs the full agent pipeline"""
    incident = parse_incident(request.model_dump())
    agent = create_agent_with_fake_tools()  # Use fake tools for MVP
    report = await agent.diagnose(incident)

    return DiagnosisResponse(
        incident_id=report.incident_id,
        status=report.status,
        top_causes=[
            HypothesisResponse(
                rank=h.rank,
                cause_code=h.cause_code,
                confidence=h.confidence.value,
                supporting_evidence=h.supporting_evidence,
                contradicting_evidence=h.contradicting_evidence,
                reasoning_summary=h.reasoning_summary,
            )
            for h in report.top_causes
        ],
        recommended_actions=report.recommended_actions,
        missing_evidence=report.missing_evidence,
        tool_failures=report.tool_failures,
        evidence_ids=report.evidence_ids,
        investigation_steps=report.investigation_steps,
        total_tool_calls=report.total_tool_calls,
    )


@router.get("/diagnosis/{task_id}")
async def get_diagnosis_status(task_id: str):
    """Get diagnosis task status (placeholder for async support in Phase 5)"""
    return {"task_id": task_id, "status": "INVESTIGATING"}
