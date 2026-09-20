from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""

    # Server Configuration
    APP_NAME: str = "Raksha Scam Detection Engine"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS Settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # WebSocket Settings
    WS_HEARTBEAT_INTERVAL_SECONDS: int = 30

    # Risk Engine Defaults (Phase 1 Baseline)
    BASELINE_RISK_SCORE: float = 0.0

    # STT Provider Configuration (Phase 3B)
    STT_PROVIDER: str = "mock"  # "mock" or "deepgram"
    DEEPGRAM_API_KEY: Optional[str] = None
    DEEPGRAM_MODEL: str = "nova-2"
    DEEPGRAM_LANGUAGE: str = "en"
    DEEPGRAM_SAMPLE_RATE: int = 8000
    DEEPGRAM_ENCODING: str = "mulaw"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
