import asyncio
import inspect
import logging
import time
from typing import Any, Dict, List, Optional

from backend.app.models import (
    CallSession,
    InterventionRecord,
    NotificationRecord,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionDecision,
    RiskAssessment,
    RiskTier,
    SpeakerType,
    TacticMatch,
    TranscriptSegment,
    UserWarningRecord,
    WSMessage,
    WSMessageType,
)
from backend.app.services.connection_manager import manager
from backend.app.services.intervention_service import intervention_service
from backend.app.services.notification_service import caregiver_notification_service
from backend.app.services.protection_engine import protection_engine
from backend.app.services.session_store import session_store
from backend.app.services.user_warning_service import protected_user_warning_service
from backend.app.services.stt import (
    BaseSTTProvider,
    MockSTTProvider,
    get_stt_provider,
)
from backend.app.risk_engine import risk_engine
from ai.classifier import semantic_classifier

logger = logging.getLogger("raksha.backend.pipeline")


class StreamingPipeline:
    """Core real-time streaming pipeline for RAKSHA.

    Processes incoming transcript segments through:
      TranscriptSegment
             ↓
      SemanticClassifier (Phase 2A)
             ↓
      RiskEngine (Phase 2B)
             ↓
      RiskAssessment
             ↓
      WebSocket Events (TRANSCRIPT_UPDATE, TACTIC_DETECTED, RISK_UPDATE, ALERT_TRIGGERED)
    """

    def __init__(self, stt_provider: Optional[BaseSTTProvider] = None) -> None:
        self.stt_provider = stt_provider or get_stt_provider()
        self.mock_stt = MockSTTProvider()

    async def process_segment(
        self,
        segment: TranscriptSegment,
        broadcast: bool = True,
    ) -> Dict[str, Any]:
        """Process a single transcript segment through the RAKSHA detection pipeline."""
        session_id = segment.session_id

        # 1. Ensure session exists
        session = await session_store.get_session(session_id)
        if not session:
            session = await session_store.create_session(session_id=session_id)

        # 2. Append segment to session history
        await session_store.add_transcript_segment(session_id, segment)

        # 3. Classify segment using Phase 2A semantic classifier (non-blocking in worker thread)
        matches: List[TacticMatch] = []
        classification_error: Optional[str] = None
        try:
            matches = await asyncio.to_thread(semantic_classifier.classify_segment, segment)
            if matches:
                for m in matches:
                    if m.tactic not in session.ordered_tactic_sequence:
                        session.ordered_tactic_sequence.append(m.tactic)
        except Exception as exc:
            classification_error = str(exc)
            logger.exception("Semantic classification failed for session %s: %s", session_id, exc)

        # 4. Compute updated risk using Phase 2B dynamic risk engine
        prev_risk = session.latest_risk
        updated_risk: Optional[RiskAssessment] = None
        risk_error: Optional[str] = None
        try:
            if classification_error is not None:
                # Do not fabricate risk when classification fails; preserve last valid assessment
                updated_risk = prev_risk or risk_engine.evaluate_session(session)
            else:
                updated_risk = risk_engine.calculate_risk(
                    session_id=session_id,
                    new_matches=matches,
                    previous_assessment=prev_risk,
                )
        except Exception as exc:
            risk_error = str(exc)
            logger.exception("Risk calculation failed for session %s: %s", session_id, exc)
            # Preserve last valid assessment without fabricating new score
            updated_risk = prev_risk or risk_engine.evaluate_session(session)

        # 5. Persist updated risk in session store
        if updated_risk:
            await session_store.update_risk_assessment(session_id, updated_risk)
            session.latest_risk = updated_risk

        # 6. Evaluate protection policy downstream of risk engine
        protection_decision: Optional[ProtectionDecision] = None
        if updated_risk:
            protection_decision = protection_engine.evaluate(
                session_id=session_id,
                risk_assessment=updated_risk,
                segment=segment,
            )
            await session_store.add_protection_decision(session_id, protection_decision)

        # 7. Evaluate and dispatch caregiver notifications if eligible (Phase 7B)
        notification_records: List[NotificationRecord] = []
        if session and protection_decision:
            try:
                notification_records = caregiver_notification_service.dispatch_notifications(
                    session=session,
                    decision=protection_decision,
                )
                for record in notification_records:
                    await session_store.add_notification_record(session_id, record)
            except Exception as exc:
                logger.exception(
                    "Caregiver notification dispatch failed for session %s: %s", session_id, exc
                )

        # 8. Evaluate and dispatch protected-user warning if eligible (Phase 7C / 7D-3C-2)
        user_warning_record: Optional[UserWarningRecord] = None
        if session and protection_decision:
            try:
                res = protected_user_warning_service.warn_user(
                    session=session,
                    decision=protection_decision,
                )
                if inspect.isawaitable(res):
                    user_warning_record = await res
                else:
                    user_warning_record = res
                if user_warning_record:
                    await session_store.add_user_warning_record(session_id, user_warning_record)
            except Exception as exc:
                logger.exception(
                    "Protected user warning dispatch failed for session %s: %s", session_id, exc
                )

        # 9. Evaluate and dispatch call intervention if eligible (Phase 7D-1)
        intervention_record: Optional[InterventionRecord] = None
        if session and protection_decision:
            try:
                intervention_record = await intervention_service.evaluate_and_execute(
                    session=session,
                    decision=protection_decision,
                    risk=updated_risk,
                )
                if intervention_record:
                    await session_store.add_intervention_record(session_id, intervention_record)
            except Exception as exc:
                logger.exception(
                    "Call intervention dispatch failed for session %s: %s", session_id, exc
                )

        # 10. Construct structured events
        events: List[WSMessage] = []

        # Event: TRANSCRIPT_UPDATE
        transcript_event = WSMessage(
            type=WSMessageType.TRANSCRIPT_UPDATE,
            data={"segment": segment.model_dump()},
        )
        events.append(transcript_event)

        # Event: ERROR (if classification failed)
        if classification_error:
            events.append(
                WSMessage(
                    type=WSMessageType.ERROR,
                    data={
                        "session_id": session_id,
                        "error": f"Semantic classification error: {classification_error}",
                    },
                )
            )

        # Event: TACTIC_DETECTED (if any tactics matched this segment)
        if matches:
            tactic_event = WSMessage(
                type=WSMessageType.TACTIC_DETECTED,
                data={
                    "session_id": session_id,
                    "tactics": [m.model_dump() for m in matches],
                    "utterance": segment.text,
                },
            )
            events.append(tactic_event)

        # Event: ERROR (if risk evaluation failed)
        if risk_error:
            events.append(
                WSMessage(
                    type=WSMessageType.ERROR,
                    data={
                        "session_id": session_id,
                        "error": f"Risk engine error: {risk_error}",
                    },
                )
            )

        # Event: RISK_UPDATE
        if updated_risk:
            risk_event = WSMessage(
                type=WSMessageType.RISK_UPDATE,
                data={
                    "risk": updated_risk.model_dump(),
                    "cooldown_applied": protection_decision.cooldown_applied if protection_decision else False,
                },
            )
            events.append(risk_event)

        # Event: ALERT_TRIGGERED (governed by ProtectionEngine decision)
        if protection_decision and any(
            a.action_type == ProtectionActionType.DASHBOARD_ALERT
            and a.status == ProtectionActionStatus.EXECUTED
            for a in protection_decision.triggered_actions
        ):
            alert_event = WSMessage(
                type=WSMessageType.ALERT_TRIGGERED,
                data={
                    "session_id": session_id,
                    "overall_score": updated_risk.overall_score,
                    "risk_tier": updated_risk.risk_tier.value,
                    "accumulated_tactics": [t.value for t in updated_risk.accumulated_tactics],
                    "explanation": updated_risk.explanation,
                    "latest_evidence": segment.text,
                    # Backward-compatible Phase 7A protection metadata
                    "protection_level": protection_decision.level.value,
                    "is_escalation": protection_decision.is_escalation,
                    "cooldown_applied": protection_decision.cooldown_applied,
                    # Phase 10C: Enriched downstream protection execution records
                    "caregiver_notifications": [r.model_dump() for r in notification_records],
                    "user_warning": user_warning_record.model_dump() if user_warning_record else None,
                    "intervention": intervention_record.model_dump() if intervention_record else None,
                },
            )
            events.append(alert_event)

        # 8. Broadcast events to all active WebSocket listeners on this session
        if broadcast:
            for event in events:
                await manager.broadcast_session(session_id, event)

        return {
            "segment": segment,
            "matches": matches,
            "risk": updated_risk,
            "protection": protection_decision,
            "notifications": notification_records,
            "user_warning": user_warning_record,
            "intervention": intervention_record,
            "events": events,
        }

    async def run_simulation(
        self,
        session_id: str,
        chunks: Optional[List[str]] = None,
        speaker: SpeakerType = SpeakerType.CALLER,
        delay_seconds: float = 0.0,
        broadcast: bool = True,
    ) -> List[Dict[str, Any]]:
        """Run a mock streaming STT simulation through the pipeline."""
        results: List[Dict[str, Any]] = []

        async for segment in self.mock_stt.stream_transcripts(
            session_id=session_id,
            input_data=chunks,
            speaker=speaker,
            delay_seconds=delay_seconds,
        ):
            step_result = await self.process_segment(segment, broadcast=broadcast)
            results.append(step_result)

        return results


# Global singleton instance
streaming_pipeline = StreamingPipeline()
