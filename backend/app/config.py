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

    # Campaign Link Analysis Configuration (Phase 10E-1)
    # Salt for deterministic non-reversible caller phone number hashing
    CAMPAIGN_HASH_SALT: str = "raksha_demo_salt_sec_2026"
    # Multi-factor similarity link cutoff (demo/engineering calibration threshold)
    CAMPAIGN_MATCH_THRESHOLD: float = 0.72
    # Bounded in-memory campaign registry ceiling
    CAMPAIGN_MAX_ACTIVE: int = 50
    # Campaign activity TTL sliding window (14 days default)
    CAMPAIGN_TTL_SECONDS: float = 86400.0 * 14
    # Multi-signal link score weights (sum = 1.0)
    CAMPAIGN_WEIGHT_TACTIC: float = 0.35
    CAMPAIGN_WEIGHT_PROGRESSION: float = 0.25
    CAMPAIGN_WEIGHT_TARGET: float = 0.25
    CAMPAIGN_WEIGHT_CALLER: float = 0.15
    # Maximum incident summaries retained per campaign (memory cap)
    CAMPAIGN_MAX_LINKED_INCIDENTS: int = 50
    # Phase 10E-2: Campaign Escalation Policy (Demo/Engineering Threshold)
    # Minimum linked HIGH/CRITICAL incidents required before campaign becomes ESCALATION_ELIGIBLE
    CAMPAIGN_ESCALATION_MIN_INCIDENTS: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
