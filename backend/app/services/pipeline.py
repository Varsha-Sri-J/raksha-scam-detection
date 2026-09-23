import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from backend.app.models import (
    CallSession,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionDecision,
    RiskAssessment,
    RiskTier,
    SpeakerType,
    TacticMatch,
    TranscriptSegment,
    WSMessage,
    WSMessageType,
)
from backend.app.services.connection_manager import manager
from backend.app.services.protection_engine import protection_engine
from backend.app.services.session_store import session_store
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

        # 7. Construct structured events
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
                data={"risk": updated_risk.model_dump()},
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
