"""Offline Evaluation Runner for RAKSHA (Phase 8B).

Executes EvaluationScenarios against the production RAKSHA StreamingPipeline
without modifying detector, risk, protection, or telephony components.
Guarantees session isolation and failure containment.
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional

from backend.app.models import (
    CaregiverContact,
    ProtectionActionStatus,
    ProtectionActionType,
    RiskTier,
    SpeakerType,
    TranscriptSegment,
)
from backend.app.services.intervention_service import (
    MockInterventionProvider,
    intervention_service,
)
from backend.app.services.notification_service import (
    MockSMSProvider,
    caregiver_notification_service,
)
from backend.app.services.pipeline import StreamingPipeline
from backend.app.services.protection_engine import protection_engine
from backend.app.services.session_store import session_store
from backend.app.services.stt import MockSTTProvider
from backend.app.services.user_warning_service import (
    MockUserWarningProvider,
    protected_user_warning_service,
)
from evaluation.models import (
    EvaluationScenario,
    EvaluationScenarioResult,
    EvaluationSegmentResult,
)

logger = logging.getLogger("raksha.evaluation.runner")

TIER_ORDER: Dict[str, int] = {
    RiskTier.SAFE.value: 0,
    RiskTier.LOW.value: 1,
    RiskTier.MEDIUM.value: 2,
    RiskTier.HIGH.value: 3,
    RiskTier.CRITICAL.value: 4,
}


def _max_tier(tiers: List[str]) -> str:
    """Return the highest risk tier from a list of tier strings."""
    if not tiers:
        return RiskTier.SAFE.value
    return max(tiers, key=lambda t: TIER_ORDER.get(t, 0))


class EvaluationRunner:
    """Offline test harness executing realistic conversation scenarios through RAKSHA."""

    def __init__(self, pipeline: Optional[StreamingPipeline] = None) -> None:
        self.pipeline = pipeline or StreamingPipeline(stt_provider=MockSTTProvider())

    async def run_scenario(self, scenario: EvaluationScenario) -> EvaluationScenarioResult:
        """Run a single scenario through the RAKSHA streaming pipeline in complete isolation."""
        session_id = f"eval-{scenario.scenario_id}-{uuid.uuid4().hex[:8]}"

        # 1. Initialize clean CallSession in SessionStore
        session = await session_store.create_session(session_id=session_id)
        session.callee_id = "Protected User"
        session.caregiver_contacts = [
            CaregiverContact(name="Primary Caregiver", phone_number="+15551234567", enabled=True)
        ]
        session.protected_user_connected = True  # Verified conference state for user warning

        # 2. Configure mock providers for scenario failure toggles
        original_caregiver_provider = caregiver_notification_service.default_provider
        original_warning_provider = protected_user_warning_service.default_provider
        original_intervention_provider = intervention_service.default_provider

        caregiver_notification_service.default_provider = MockSMSProvider(
            should_fail=scenario.caregiver_should_fail
        )
        protected_user_warning_service.default_provider = MockUserWarningProvider(
            should_fail=scenario.warning_should_fail
        )
        intervention_service.default_provider = MockInterventionProvider(
            should_fail=scenario.intervention_should_fail
        )

        protection_engine.reset_session(session_id)

        segment_results: List[EvaluationSegmentResult] = []
        all_detected_tactics: List[str] = []
        first_detection_idx: Optional[int] = None
        first_warning_idx: Optional[int] = None
        first_intervention_idx: Optional[int] = None

        try:
            for idx, eval_segment in enumerate(scenario.segments):
                speaker_val = (
                    eval_segment.speaker
                    if isinstance(eval_segment.speaker, SpeakerType)
                    else SpeakerType(eval_segment.speaker)
                )

                transcript_seg = TranscriptSegment(
                    session_id=session_id,
                    speaker=speaker_val,
                    text=eval_segment.text,
                    is_final=True,
                )

                # Process through production streaming pipeline (broadcast disabled)
                pipe_out = await self.pipeline.process_segment(transcript_seg, broadcast=False)

                matches = pipe_out.get("matches") or []
                risk = pipe_out.get("risk")
                protection = pipe_out.get("protection")
                notifications = pipe_out.get("notifications") or []
                user_warning = pipe_out.get("user_warning")
                intervention = pipe_out.get("intervention")
                events = pipe_out.get("events") or []

                detected_tactics = [m.tactic.value for m in matches]
                confidence_map = {m.tactic.value: round(m.confidence, 4) for m in matches}
                evidence_list = [m.evidence_text for m in matches]

                # Update cumulative distinct detected tactics
                for tactic_str in detected_tactics:
                    if tactic_str not in all_detected_tactics:
                        all_detected_tactics.append(tactic_str)

                risk_score = round(risk.overall_score, 2) if risk else 0.0
                risk_tier = risk.risk_tier.value if risk else RiskTier.SAFE.value
                protection_level = protection.level.value if protection else "MONITORING"

                alert_executed = False
                if protection and protection.triggered_actions:
                    alert_executed = any(
                        a.action_type == ProtectionActionType.DASHBOARD_ALERT
                        and a.status == ProtectionActionStatus.EXECUTED
                        for a in protection.triggered_actions
                    )

                warning_status_str: Optional[str] = None
                if user_warning:
                    status_attr = getattr(user_warning, "status", None)
                    warning_status_str = (
                        status_attr.value if hasattr(status_attr, "value") else str(status_attr)
                    )

                intervention_status_str: Optional[str] = None
                if intervention:
                    status_attr = getattr(intervention, "status", None)
                    intervention_status_str = (
                        status_attr.value if hasattr(status_attr, "value") else str(status_attr)
                    )

                event_types = [
                    e.type.value if hasattr(e.type, "value") else str(e.type) for e in events
                ]

                # Record first detection segment
                if first_detection_idx is None and detected_tactics:
                    first_detection_idx = idx

                # Record warning segment (when warning protection level or user warning occurs)
                if first_warning_idx is None and (
                    protection_level in ["WARNING", "CRITICAL_INTERCEPT"]
                    or warning_status_str in ["QUEUED", "DELIVERED", "FAILED"]
                ):
                    first_warning_idx = idx

                # Record intervention segment
                if first_intervention_idx is None and intervention_status_str is not None:
                    first_intervention_idx = idx

                seg_result = EvaluationSegmentResult(
                    segment_index=idx,
                    speaker=str(speaker_val.value),
                    text=eval_segment.text,
                    detected_tactics=detected_tactics,
                    confidence_values=confidence_map,
                    evidence=evidence_list,
                    risk_score=risk_score,
                    risk_tier=risk_tier,
                    protection_level=protection_level,
                    alert_executed=alert_executed,
                    caregiver_notification_count=len(notifications),
                    user_warning_status=warning_status_str,
                    intervention_status=intervention_status_str,
                    events_emitted=event_types,
                )
                segment_results.append(seg_result)

            peak_score = max((r.risk_score for r in segment_results), default=0.0)
            peak_tier = _max_tier([r.risk_tier for r in segment_results])
            final_score = segment_results[-1].risk_score if segment_results else 0.0
            final_tier = segment_results[-1].risk_tier if segment_results else RiskTier.SAFE.value

            expected_tactics_list = [
                t.value if hasattr(t, "value") else str(t)
                for t in (scenario.expected_tactics or [])
            ]

            # Verify downstream failure isolation
            # Upstream risk and protection engine must produce valid outputs even when downstream fails
            failure_isolation_intact = True
            if scenario.caregiver_should_fail:
                # Upstream alert execution must remain intact despite caregiver SMS failure
                failure_isolation_intact = any(r.alert_executed for r in segment_results)
            if scenario.warning_should_fail:
                # Upstream protection decision must remain intact
                failure_isolation_intact = any(
                    r.protection_level in ["WARNING", "CRITICAL_INTERCEPT"] for r in segment_results
                )
            if scenario.intervention_should_fail:
                # Upstream risk must remain intact (reached HIGH or CRITICAL)
                failure_isolation_intact = peak_tier in ["HIGH", "CRITICAL"]

            return EvaluationScenarioResult(
                scenario_id=scenario.scenario_id,
                category=scenario.category,
                description=scenario.description,
                segment_results=segment_results,
                peak_score=peak_score,
                peak_tier=peak_tier,
                first_detection_segment=first_detection_idx,
                warning_segment=first_warning_idx,
                intervention_segment=first_intervention_idx,
                final_score=final_score,
                final_tier=final_tier,
                detected_tactics=all_detected_tactics,
                expected_tactics=expected_tactics_list,
                failure_isolation_intact=failure_isolation_intact,
                notes=scenario.notes,
            )

        finally:
            # Restore original providers to prevent any leak
            caregiver_notification_service.default_provider = original_caregiver_provider
            protected_user_warning_service.default_provider = original_warning_provider
            intervention_service.default_provider = original_intervention_provider
            protection_engine.reset_session(session_id)

    async def run_all(
        self, scenarios: Optional[List[EvaluationScenario]] = None
    ) -> List[EvaluationScenarioResult]:
        """Run all provided scenarios sequentially, collecting results."""
        from evaluation.scenarios import ALL_EVALUATION_SCENARIOS

        target_scenarios = scenarios if scenarios is not None else ALL_EVALUATION_SCENARIOS
        results: List[EvaluationScenarioResult] = []
        for scenario in target_scenarios:
            result = await self.run_scenario(scenario)
            results.append(result)
        return results

    def run_all_sync(
        self, scenarios: Optional[List[EvaluationScenario]] = None
    ) -> List[EvaluationScenarioResult]:
        """Synchronous wrapper for running scenarios."""
        return asyncio.run(self.run_all(scenarios))
