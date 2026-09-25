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
    ISOLATION_SECRECY = "ISOLATION_SECRECY"
    FINANCIAL_REDIRECTION = "FINANCIAL_REDIRECTION"
    FEAR_INTIMIDATION = "FEAR_INTIMIDATION"
    INFORMATION_PHISHING = "INFORMATION_PHISHING"
    CONFUSION_OVERWHELM = "CONFUSION_OVERWHELM"
    RELIEF_FALSE_SALVATION = "RELIEF_FALSE_SALVATION"

    # Backward compatibility aliases
    ISOLATION = "ISOLATION_SECRECY"
    FINANCIAL_EXTRACTION = "FINANCIAL_REDIRECTION"
    THREAT_INTIMIDATION = "FEAR_INTIMIDATION"
    CREDENTIAL_HARVESTING = "INFORMATION_PHISHING"
    FALSE_SALVATION = "RELIEF_FALSE_SALVATION"


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
    explanation: Optional[str] = None
    description: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class RiskAssessment(BaseModel):
    session_id: str
    overall_score: float = Field(ge=0.0, le=100.0, default=0.0)
    risk_tier: RiskTier = RiskTier.SAFE
    triggered_tactics: List[TacticMatch] = Field(default_factory=list)
    accumulated_tactics: List[ManipulationCategory] = Field(default_factory=list)
    evidence_segments: List[str] = Field(default_factory=list)
    tactic_evidence: Dict[str, List[str]] = Field(default_factory=dict)
    score_delta: float = 0.0
    explanation: str = "Baseline safe state."
    timestamp: float = Field(default_factory=time.time)


class ProtectionLevel(str, Enum):
    MONITORING = "MONITORING"
    ADVISORY = "ADVISORY"
    WARNING = "WARNING"
    CRITICAL_INTERCEPT = "CRITICAL_INTERCEPT"


class ProtectionActionType(str, Enum):
    DASHBOARD_ALERT = "DASHBOARD_ALERT"
    PROTECTED_USER_WHISPER = "PROTECTED_USER_WHISPER"
    CAREGIVER_SMS = "CAREGIVER_SMS"
    CALL_DISCONNECT = "CALL_DISCONNECT"


class ProtectionActionStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    SUPPRESSED = "SUPPRESSED"


class ProtectionAction(BaseModel):
    action_type: ProtectionActionType
    level: ProtectionLevel
    recipient: Optional[str] = None
    message: str
    status: ProtectionActionStatus = ProtectionActionStatus.EXECUTED
    timestamp: float = Field(default_factory=time.time)


class ProtectionDecision(BaseModel):
    session_id: str
    level: ProtectionLevel
    triggered_actions: List[ProtectionAction] = Field(default_factory=list)
    trigger_score: float
    trigger_tier: RiskTier
    is_escalation: bool = False
    cooldown_applied: bool = False
    explanation: str
    timestamp: float = Field(default_factory=time.time)


class CaregiverContact(BaseModel):
    name: str
    phone_number: str
    relationship: Optional[str] = None
    enabled: bool = True


class NotificationChannel(str, Enum):
    SMS = "SMS"


class NotificationStatus(str, Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class NotificationRecord(BaseModel):
    notification_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    channel: NotificationChannel = NotificationChannel.SMS
    recipient: str
    message: str
    status: NotificationStatus
    provider: str = "mock"
    timestamp: float = Field(default_factory=time.time)
    error: Optional[str] = None


class NotificationResult(BaseModel):
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    provider: str = "mock"


class UserWarningChannel(str, Enum):
    VOICE = "VOICE"


class UserWarningStatus(str, Enum):
    QUEUED = "QUEUED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class UserWarningRecord(BaseModel):
    warning_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    channel: UserWarningChannel = UserWarningChannel.VOICE
    message: str
    status: UserWarningStatus
    provider: str = "mock"
    timestamp: float = Field(default_factory=time.time)
    error: Optional[str] = None


class UserWarningResult(BaseModel):
    success: bool
    warning_id: Optional[str] = None
    status: Optional[UserWarningStatus] = None
    error: Optional[str] = None
    provider: str = "mock"


class InterventionType(str, Enum):
    DISCONNECT = "DISCONNECT"


class InterventionStatus(str, Enum):
    REQUESTED = "REQUESTED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"
    SKIPPED = "SKIPPED"


class InterventionRecord(BaseModel):
    intervention_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    type: InterventionType = InterventionType.DISCONNECT
    status: InterventionStatus
    provider: str = "mock"
    reason: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    error: Optional[str] = None


class InterventionResult(BaseModel):
    success: bool
    intervention_id: Optional[str] = None
    provider: str = "mock"
    error: Optional[str] = None


class CallSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    caller_id: Optional[str] = "Unknown"
    callee_id: Optional[str] = "Protected Callee"
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    transcript_history: List[TranscriptSegment] = Field(default_factory=list)
    latest_risk: Optional[RiskAssessment] = None
    protection_history: List[ProtectionDecision] = Field(default_factory=list)
    caregiver_contacts: List[CaregiverContact] = Field(default_factory=list)
    notification_history: List[NotificationRecord] = Field(default_factory=list)
    user_warning_history: List[UserWarningRecord] = Field(default_factory=list)
    intervention_history: List[InterventionRecord] = Field(default_factory=list)

    # Telephony Topology & Conference State (Phase 7D-3)
    parent_call_sid: Optional[str] = None
    protected_user_call_sid: Optional[str] = None
    conference_sid: Optional[str] = None
    conference_name: Optional[str] = None
    stream_sid: Optional[str] = None
    protected_user_phone_number: Optional[str] = None
    call_topology: str = "standard"
    protected_user_connected: bool = False

    # Campaign & Attack Sequence Tracking (Phase 10E-1)
    ordered_tactic_sequence: List[ManipulationCategory] = Field(default_factory=list)


class WSMessageType(str, Enum):
    TRANSCRIPT_UPDATE = "TRANSCRIPT_UPDATE"
    TRANSCRIPT_STREAM = "TRANSCRIPT_STREAM"  # Backward-compatible alias
    TACTIC_DETECTED = "TACTIC_DETECTED"
    RISK_UPDATE = "RISK_UPDATE"
    ALERT_TRIGGERED = "ALERT_TRIGGERED"
    SESSION_STATUS = "SESSION_STATUS"
    PING = "PING"
    PONG = "PONG"
    ERROR = "ERROR"
    CAMPAIGN_UPDATE = "CAMPAIGN_UPDATE"


class WSMessage(BaseModel):
    type: WSMessageType
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


# --- Campaign Link Analysis Models (Phase 10E-1) ---


class CampaignStatus(str, Enum):
    DETECTED = "DETECTED"
    ACTIVE_MONITORING = "ACTIVE_MONITORING"
    ESCALATION_ELIGIBLE = "ESCALATION_ELIGIBLE"
    REPORT_GENERATED = "REPORT_GENERATED"


class PrivacyMinimizedIncident(BaseModel):
    """Privacy-minimized representation of a single suspicious incident for cross-call campaign linkage.

    Guarantees:
    - Zero raw audio or speech recordings stored.
    - Zero conversational transcripts or raw evidence text stored.
    - Zero victim PII (names, physical addresses, bank accounts) stored.
    - Zero caregiver phone numbers stored.
    - Raw caller phone number is NEVER stored; only salted SHA-256 hash & masked display string.
    """

    incident_id: str
    timestamp: float = Field(default_factory=time.time)
    caller_hash: Optional[str] = None
    caller_masked: str = "Unknown"
    tactic_signature: List[ManipulationCategory] = Field(default_factory=list)
    tactic_sequence: List[str] = Field(default_factory=list)
    target_category: str = "GENERAL_MANIPULATION"
    peak_risk_score: float = 0.0
    final_risk_tier: RiskTier = RiskTier.SAFE
    caregiver_notification_outcome: Optional[str] = "NOT_TRIGGERED"
    intervention_outcome: Optional[str] = "NOT_TRIGGERED"


class CampaignRecord(BaseModel):
    """Aggregated campaign intelligence linking multiple related scam incidents."""

    campaign_id: str = Field(default_factory=lambda: f"CMP-{uuid.uuid4().hex[:8].upper()}")
    status: CampaignStatus = CampaignStatus.DETECTED
    first_seen: float = Field(default_factory=time.time)
    last_seen: float = Field(default_factory=time.time)
    incident_count: int = 1
    linked_incidents: List[PrivacyMinimizedIncident] = Field(default_factory=list)
    observed_caller_identifiers: List[str] = Field(default_factory=list)
    dominant_tactics: List[ManipulationCategory] = Field(default_factory=list)
    target_categories: List[str] = Field(default_factory=list)
    average_risk_score: float = 0.0
    highest_risk_score: float = 0.0
    risk_tier_distribution: Dict[str, int] = Field(default_factory=dict)


class LawEnforcementReport(BaseModel):
    """Privacy-minimized mock law-enforcement report for a syndicated scam campaign.

    IMPORTANT:
    DEMO ONLY — NO ACTUAL TRANSMISSION TO LAW ENFORCEMENT.
    Strictly zero storage of raw audio, transcripts, victim PII, or raw phone numbers.
    """

    report_id: str = Field(default_factory=lambda: f"RAKSHA-NCRP-{uuid.uuid4().hex[:8].upper()}")
    campaign_id: str
    generated_at: float = Field(default_factory=time.time)
    campaign_status: CampaignStatus = CampaignStatus.REPORT_GENERATED
    incident_count: int
    first_seen: float
    last_seen: float
    observed_caller_identifiers: List[str] = Field(default_factory=list)
    dominant_tactics: List[ManipulationCategory] = Field(default_factory=list)
    target_categories: List[str] = Field(default_factory=list)
    risk_tier_distribution: Dict[str, int] = Field(default_factory=dict)
    highest_risk_score: float
    average_risk_score: float
    attack_progression_summary: List[str] = Field(default_factory=list)
    linked_incident_ids: List[str] = Field(default_factory=list)
    escalation_reason: str
    status: str = "MOCK_REPORT_GENERATED"
    disclaimer: str = "DEMO ONLY — NO ACTUAL TRANSMISSION TO LAW ENFORCEMENT"
    integrity_hash: Optional[str] = None
