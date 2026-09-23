"""Evaluation data models for the offline RAKSHA evaluation harness (Phase 8B).

Provides structured Pydantic models for segments, scenarios, per-segment results,
and aggregate scenario results.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.models import ManipulationCategory, SpeakerType


class EvaluationSegment(BaseModel):
    """A single dialogue turn within an evaluation scenario."""

    speaker: SpeakerType = SpeakerType.CALLER
    text: str
    expected_tactics: Optional[List[ManipulationCategory]] = None
    notes: Optional[str] = None


class EvaluationScenario(BaseModel):
    """A complete conversational test case evaluated against RAKSHA.

    Distinguishes observed runtime outputs from optional human evaluation labels.
    """

    scenario_id: str
    category: str  # clear_scam, multi_tactic, novel_wording, legitimate_urgency, benign, progression, downstream_failure
    description: str
    segments: List[EvaluationSegment] = Field(default_factory=list)
    expected_tactics: Optional[List[ManipulationCategory]] = None
    expected_behavior: Optional[Dict[str, Any]] = None

    # Downstream failure injection toggles (Phase 8B Section 7)
    caregiver_should_fail: bool = False
    warning_should_fail: bool = False
    intervention_should_fail: bool = False

    notes: Optional[str] = None


class EvaluationSegmentResult(BaseModel):
    """Structured capture of RAKSHA pipeline output for a single transcript segment."""

    segment_index: int
    speaker: str = "CALLER"
    text: str
    detected_tactics: List[str] = Field(default_factory=list)
    confidence_values: Dict[str, float] = Field(default_factory=dict)
    evidence: List[str] = Field(default_factory=list)
    risk_score: float = 0.0
    risk_tier: str = "SAFE"
    protection_level: str = "MONITORING"
    alert_executed: bool = False
    caregiver_notification_count: int = 0
    user_warning_status: Optional[str] = None
    intervention_status: Optional[str] = None
    events_emitted: List[str] = Field(default_factory=list)


class EvaluationScenarioResult(BaseModel):
    """Complete observed evaluation result for a full scenario execution."""

    scenario_id: str
    category: str
    description: str = ""
    segment_results: List[EvaluationSegmentResult] = Field(default_factory=list)
    peak_score: float = 0.0
    peak_tier: str = "SAFE"
    first_detection_segment: Optional[int] = None
    warning_segment: Optional[int] = None
    intervention_segment: Optional[int] = None
    final_score: float = 0.0
    final_tier: str = "SAFE"
    detected_tactics: List[str] = Field(default_factory=list)
    expected_tactics: List[str] = Field(default_factory=list)
    failure_isolation_intact: bool = True
    notes: Optional[str] = None
