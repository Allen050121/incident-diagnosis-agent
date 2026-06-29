"""Application configuration and settings"""

from pathlib import Path
from pydantic_settings import BaseSettings

# python/ directory .env file
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file"""

    # Database
    db_host: str = "localhost"
    db_port: int = 3306
    db_username: str = "incident"
    db_password: str = "incident123"
    db_name: str = "incident_db"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Elasticsearch (Runbook RAG)
    elasticsearch_url: str = "http://localhost:9200"
    runbook_index: str = "runbooks"

    # LLM (DeepSeek - configure via .env, never commit real keys)
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-flash"
    llm_base_url: str = "https://api.deepseek.com"

    # Budget limits
    max_tool_calls: int = 10
    max_verification_rounds: int = 3
    max_tokens: int = 50000

    class Config:
        env_file = str(_ENV_FILE)
        case_sensitive = False


settings = Settings()
