"""Incident Diagnosis Agent - FastAPI Application"""

from fastapi import FastAPI
from app.api.router import router as api_router

app = FastAPI(
    title="Incident Diagnosis Agent",
    description="Root cause analysis agent for Spring Boot microservices",
    version="0.1.0"
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
