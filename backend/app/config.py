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

    # STT Provider Configuration (Phase 3B & Multilingual)
    STT_PROVIDER: str = "mock"  # "mock", "deepgram", or "sarvam"
    DEEPGRAM_API_KEY: Optional[str] = None
    DEEPGRAM_MODEL: str = "nova-2"
    DEEPGRAM_LANGUAGE: str = "en"
    DEEPGRAM_SAMPLE_RATE: int = 8000
    DEEPGRAM_ENCODING: str = "mulaw"

    # Sarvam Multilingual STT Provider Configuration
    SARVAM_API_KEY: Optional[str] = None
    SARVAM_STT_MODEL: str = "saaras:v3-realtime"
    SARVAM_LANGUAGE_CODE: str = "auto"
    SARVAM_SAMPLE_RATE: int = 8000
    SARVAM_ENCODING: str = "mulaw"

    # Twilio Configuration (Phase 5A)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None
    TWILIO_STREAM_BASE_URL: Optional[str] = None
    TWILIO_VALIDATE_SIGNATURE: bool = False
    TWILIO_API_TIMEOUT_SECONDS: float = 3.0

    # Intervention Provider Configuration (Phase 7D-2)
    INTERVENTION_PROVIDER: str = "mock"  # "mock" or "twilio"

    # User Warning Provider Configuration (Phase 7D-3)
    USER_WARNING_PROVIDER: str = "mock"  # "mock" or "twilio_conference" (Phase 7D-3C-2)
    PROTECTED_USER_PHONE_NUMBER: Optional[str] = None  # Demo/hackathon destination number

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
