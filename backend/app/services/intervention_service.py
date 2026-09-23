import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

from backend.app.models import (
    CallSession,
    InterventionRecord,
    InterventionResult,
    InterventionStatus,
    InterventionType,
    ManipulationCategory,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionDecision,
    ProtectionLevel,
    RiskAssessment,
)

logger = logging.getLogger("raksha.backend.intervention_service")

# Canonical acute manipulation tactics required for disconnect eligibility
ACUTE_DISCONNECT_TACTICS: Set[ManipulationCategory] = {
    ManipulationCategory.INFORMATION_PHISHING,  # Credential / OTP extraction
    ManipulationCategory.FINANCIAL_REDIRECTION,  # Immediate fraudulent money transfer
}


class BaseInterventionProvider(ABC):
    """Abstract interface for call intervention delivery."""

    @abstractmethod
    def disconnect_call(self, session_id: str) -> InterventionResult:
        """Simulate or execute disconnecting the call for the given session."""
        pass


class MockInterventionProvider(BaseInterventionProvider):
    """Deterministic simulated intervention provider for testing and demonstration (Phase 7D-1).

    Guarantees:
    - Zero network calls or telephony API calls.
    - Does not call Twilio REST API or manipulate carrier lines.
    - Injects zero audio and does not perform real call termination.
    - Returns deterministic simulated execution results.
    - Explicit failure toggling for resilient failure-mode testing.
    - Unambiguously identifies itself as 'mock'.
    """

    def __init__(
        self,
        should_fail: bool = False,
        fail_error: str = "Simulated call disconnect operation failed",
    ) -> None:
        self.should_fail = should_fail
        self.fail_error = fail_error
        self.executed_disconnects: List[Dict[str, Any]] = []

    def disconnect_call(self, session_id: str) -> InterventionResult:
        """Simulate disconnecting a call session."""
        if self.should_fail:
            logger.warning(
                "MockInterventionProvider: Simulated disconnect failure for session %s",
                session_id,
            )
            return InterventionResult(
                success=False,
                error=self.fail_error,
                provider="mock",
            )

        action_id = f"mock-disconnect-{uuid.uuid4().hex[:8]}"
        record = {
            "intervention_id": action_id,
            "session_id": session_id,
            "timestamp": time.time(),
        }
        self.executed_disconnects.append(record)
        logger.info(
            "MockInterventionProvider: Simulated disconnect executed for session %s (id=%s)",
            session_id,
            action_id,
        )
        return InterventionResult(
            success=True,
            intervention_id=action_id,
            provider="mock",
        )

    def clear(self) -> None:
        """Clear executed history and reset failure state."""
        self.executed_disconnects.clear()
        self.should_fail = False


class InterventionService:
    """Downstream intervention orchestration service for automated call protection (Phase 7D-1).

    Policy:
    - Downstream strictly of ProtectionDecision (never re-scores raw transcripts or embeddings).
    - Disconnect is eligible ONLY when:
        1. ProtectionDecision.level == ProtectionLevel.CRITICAL_INTERCEPT
        2. ProtectionDecision contains an operational DASHBOARD_ALERT with status EXECUTED
        3. Fresh acute extraction tactic present (INFORMATION_PHISHING or FINANCIAL_REDIRECTION)
    - If ProtectionDecision has no executed DASHBOARD_ALERT (e.g. cooldown suppressed), NO intervention.
    - If ProtectionDecision is WARNING / HIGH, NO disconnect.
    - Strict Idempotency: At most ONE disconnect execution per session. Subsequent attempts are SUPPRESSED.
    - Thread-safe & concurrency-safe: Uses session locks to serialize near-simultaneous duplicate requests.
    """

    def __init__(self, default_provider: Optional[BaseInterventionProvider] = None) -> None:
        self.default_provider = default_provider or MockInterventionProvider()
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Retrieve or create an asyncio.Lock for a specific session."""
        async with self._global_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
            return self._session_locks[session_id]

    def _has_acute_tactic(self, risk: Optional[RiskAssessment]) -> bool:
        """Check if fresh acute manipulation tactics are present in the risk assessment."""
        if not risk or not risk.triggered_tactics:
            return False
        return any(match.tactic in ACUTE_DISCONNECT_TACTICS for match in risk.triggered_tactics)

    def _is_already_executed(self, session: CallSession) -> bool:
        """Check if a disconnect intervention was already executed or requested for this session."""
        return any(
            rec.type == InterventionType.DISCONNECT
            and rec.status in [InterventionStatus.EXECUTED, InterventionStatus.EXECUTING]
            for rec in session.intervention_history
        )

    async def evaluate_and_execute(
        self,
        session: CallSession,
        decision: ProtectionDecision,
        risk: Optional[RiskAssessment] = None,
        provider: Optional[BaseInterventionProvider] = None,
    ) -> Optional[InterventionRecord]:
        """Evaluate intervention policy and execute call disconnect if strictly eligible.

        Args:
            session: Current CallSession.
            decision: ProtectionDecision from ProtectionEngine.
            risk: Optional latest RiskAssessment for checking fresh acute tactics.
            provider: Optional override provider (defaults to self.default_provider).

        Returns:
            InterventionRecord if eligible/dispatched/suppressed, or None if completely ineligible.
        """
        # 1. Level Requirement: Strictly CRITICAL_INTERCEPT only
        if decision.level != ProtectionLevel.CRITICAL_INTERCEPT:
            return None

        # 2. Alert Requirement: DASHBOARD_ALERT must be present and EXECUTED
        has_executed_alert = any(
            action.action_type == ProtectionActionType.DASHBOARD_ALERT
            and action.status == ProtectionActionStatus.EXECUTED
            for action in decision.triggered_actions
        )
        if not has_executed_alert:
            return None

        # 3. Acute Tactic Requirement: Must have acute credential or financial extraction
        if not self._has_acute_tactic(risk):
            return None

        # 4. Acquire session lock to guarantee idempotency against concurrent requests
        lock = await self._get_session_lock(session.session_id)
        async with lock:
            now = time.time()

            # Idempotency check: At most ONE disconnect execution per session
            if self._is_already_executed(session):
                logger.info(
                    "InterventionService: Disconnect suppressed under idempotency invariant for session %s",
                    session.session_id,
                )
                return InterventionRecord(
                    session_id=session.session_id,
                    type=InterventionType.DISCONNECT,
                    status=InterventionStatus.SUPPRESSED,
                    provider="mock",
                    reason="Disconnect already executed for this session",
                    timestamp=now,
                    error=None,
                )

            active_provider = provider or self.default_provider
            reason = "Critical scam threshold with acute extraction tactic triggered automated disconnect."

            try:
                result = active_provider.disconnect_call(session.session_id)
                if result.success:
                    return InterventionRecord(
                        intervention_id=result.intervention_id or str(uuid.uuid4()),
                        session_id=session.session_id,
                        type=InterventionType.DISCONNECT,
                        status=InterventionStatus.EXECUTED,
                        provider=result.provider,
                        reason=reason,
                        timestamp=now,
                        error=None,
                    )
                else:
                    return InterventionRecord(
                        intervention_id=str(uuid.uuid4()),
                        session_id=session.session_id,
                        type=InterventionType.DISCONNECT,
                        status=InterventionStatus.FAILED,
                        provider=result.provider,
                        reason=reason,
                        timestamp=now,
                        error=result.error or "Disconnect execution failed",
                    )
            except Exception as exc:
                logger.exception(
                    "Unexpected error executing disconnect intervention for session %s: %s",
                    session.session_id,
                    exc,
                )
                return InterventionRecord(
                    intervention_id=str(uuid.uuid4()),
                    session_id=session.session_id,
                    type=InterventionType.DISCONNECT,
                    status=InterventionStatus.FAILED,
                    provider="mock",
                    reason=reason,
                    timestamp=now,
                    error=str(exc),
                )


# Global singleton instance
intervention_service = InterventionService()
