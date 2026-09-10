"""
backend/app/core/config.py

Centralized application configuration using pydantic-settings.
Loads values from environment variables / a .env file so secrets
never live in source code.
"""

from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- General ---
    PROJECT_NAME: str = "Zentrax AI Graphics"
    ENVIRONMENT: str = Field(default="development")  # development | staging | production
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- Security / Auth ---
    SECRET_KEY: str = Field(..., min_length=32)  # required — no insecure default
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Database ---
    DATABASE_URL: str = Field(..., description="e.g. postgresql+asyncpg://user:pass@host/db")

    # --- CORS ---
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    # --- External / AI service ---
    AI_GENERATION_API_KEY: str | None = None
    AI_GENERATION_BASE_URL: str | None = None

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance. Use as a FastAPI dependency:

        from app.core.config import get_settings
        settings: Settings = Depends(get_settings)
    """
    return Settings()


settings = get_settings()