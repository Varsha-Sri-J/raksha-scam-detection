import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SpeakerType(str, Enum):
    CALLER = "CALLER"
    CALLEE = "CALLEE"
    UNKNOWN = "UNKNOWN"


class RiskTier(str, Enum):
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ManipulationCategory(str, Enum):
    URGENCY = "URGENCY"
    AUTHORITY_IMPERSONATION = "AUTHORITY_IMPERSONATION"
    ISOLATION = "ISOLATION"
    FINANCIAL_EXTRACTION = "FINANCIAL_EXTRACTION"
    THREAT_INTIMIDATION = "THREAT_INTIMIDATION"
    CREDENTIAL_HARVESTING = "CREDENTIAL_HARVESTING"
    CONFUSION_OVERWHELM = "CONFUSION_OVERWHELM"
    FALSE_SALVATION = "FALSE_SALVATION"


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class TranscriptSegment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    speaker: SpeakerType = SpeakerType.UNKNOWN
    text: str
    timestamp: float = Field(default_factory=time.time)
    is_final: bool = True


class TacticMatch(BaseModel):
    tactic: ManipulationCategory
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_text: str
    timestamp: float = Field(default_factory=time.time)


class RiskAssessment(BaseModel):
    session_id: str
    overall_score: float = Field(ge=0.0, le=100.0, default=0.0)
    risk_tier: RiskTier = RiskTier.SAFE
    triggered_tactics: List[TacticMatch] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class CallSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    caller_id: Optional[str] = "Unknown"
    callee_id: Optional[str] = "Protected Callee"
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    transcript_history: List[TranscriptSegment] = Field(default_factory=list)
    latest_risk: Optional[RiskAssessment] = None


class WSMessageType(str, Enum):
    TRANSCRIPT_STREAM = "TRANSCRIPT_STREAM"
    RISK_UPDATE = "RISK_UPDATE"
    SESSION_STATUS = "SESSION_STATUS"
    PING = "PING"
    PONG = "PONG"
    ERROR = "ERROR"


class WSMessage(BaseModel):
    type: WSMessageType
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
