"""Incident Diagnosis Agent - FastAPI Application"""

import os

from fastapi import FastAPI
from app.api.router import router as api_router
from app.config import settings

app = FastAPI(
    title="Incident Diagnosis Agent",
    description="Root cause analysis agent for Spring Boot microservices",
    version="0.1.0"
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/health/config")
def config_health_check():
    return {
        "status": "healthy",
        "agent_mode": settings.agent_mode,
        "metrics_provider": settings.metrics_provider,
        "log_provider": settings.log_provider,
        "llm_configured": bool(settings.llm_api_key),
        "llm_model": settings.llm_model,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("APP_PORT", "8000")))
