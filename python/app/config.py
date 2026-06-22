"""Application configuration and settings"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Java Platform
    platform_url: str = "http://localhost:8080"

    # Elasticsearch (Runbook RAG)
    elasticsearch_url: str = "http://localhost:9200"
    runbook_index: str = "runbooks"

    # LLM (placeholder - configure based on your provider)
    llm_api_key: str = ""
    llm_model: str = "gpt-4"
    llm_base_url: str = ""

    # Budget limits
    max_tool_calls: int = 10
    max_verification_rounds: int = 3
    max_tokens: int = 50000

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
