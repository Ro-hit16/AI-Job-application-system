from __future__ import annotations
from functools import lru_cache
from typing import List, Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "Multi-Agent Job Application System"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Security
    # No default on purpose — must be set via env var / .env. App will fail to
    # start without it rather than silently running with a weak/shared key.
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # PostgreSQL
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "jobapp"
    POSTGRES_PASSWORD: str = "jobapp_password"
    POSTGRES_DB: str = "jobapp_db"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0

    # ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION_JOBS: str = "job_embeddings"
    CHROMA_COLLECTION_RESUMES: str = "resume_embeddings"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "llama3"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    LLM_CONTEXT_LENGTH: int = 8192
    LLM_TEMPERATURE: float = 0.3

    # Agent
    JOB_MATCH_THRESHOLD: float = 40.0
    MAX_JOBS_PER_RUN: int = 10
    MAX_BROWSER_INSTANCES: int = 3
    HUMAN_APPROVAL_TIMEOUT_MINUTES: int = 60
    REQUIRE_HUMAN_APPROVAL: bool = True

    # Scraper
    JOB_CATEGORIES: List[str] = [
        "MERN Stack Developer",
        "Full Stack Developer",
        "Cloud Engineer",
        "DevOps Engineer",
        "AI Engineer",
        "ML Engineer",
    ]
    JOB_PORTALS: List[str] = ["linkedin", "indeed", "naukri"]
    JOB_LOCATIONS: List[str] = ["Remote", "Bangalore", "Mumbai", "Pune", "Hyderabad"]
    SCRAPE_INTERVAL_MINUTES: int = 60

    # Notifications
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    NOTIFICATION_EMAIL_TO: Optional[str] = None
    WEBHOOK_URL: Optional[str] = None
    

    # Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # Computed — built after all fields are loaded

    # Adzuna API (free 500/day - best for India jobs)
    # Register free: https://developer.adzuna.com/

    # Portal credentials for Playwright auto-apply
    LINKEDIN_EMAIL: Optional[str] = None
    LINKEDIN_PASSWORD: Optional[str] = None
    INDEED_EMAIL: Optional[str] = None
    INDEED_PASSWORD: Optional[str] = None
    NAUKRI_EMAIL: Optional[str] = None
    NAUKRI_PASSWORD: Optional[str] = None

    ADZUNA_APP_ID: Optional[str] = None
    ADZUNA_APP_KEY: Optional[str] = None

    DATABASE_URL: str = ""
    DATABASE_URL_SYNC: str = ""
    REDIS_URL: str = ""

    @model_validator(mode="after")
    def build_computed_fields(self) -> "Settings":
        self.DATABASE_URL = (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        self.DATABASE_URL_SYNC = (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        if self.REDIS_PASSWORD:
            self.REDIS_URL = (
                f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            )
        else:
            self.REDIS_URL = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return self

    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


@lru_cache()
def get_settings() -> Settings:
    return Settings()