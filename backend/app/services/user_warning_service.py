import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from backend.app.models import (
    CallSession,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionDecision,
    ProtectionLevel,
    UserWarningChannel,
    UserWarningRecord,
    UserWarningResult,
    UserWarningStatus,
)

logger = logging.getLogger("raksha.backend.user_warning_service")


class BaseUserWarningProvider(ABC):
    """Abstract interface for protected-user warning delivery."""

    @abstractmethod
    def warn_user(self, session_id: str, message: str) -> UserWarningResult:
        """Deliver a warning advisory to the protected user on the given session."""
        pass


class MockUserWarningProvider(BaseUserWarningProvider):
    """Deterministic simulated voice warning provider for testing and demonstration.

    Guarantees:
    - Zero network calls or telephony API calls.
    - Injects zero audio and terminates no calls.
    - Returns deterministic simulated delivery results.
    - Explicit failure toggling for resilient failure-mode testing.
    """

    def __init__(
        self,
        should_fail: bool = False,
        fail_error: str = "Simulated voice warning delivery failure",
    ) -> None:
        self.should_fail = should_fail
        self.fail_error = fail_error
        self.delivered_warnings: List[Dict[str, Any]] = []

    def warn_user(self, session_id: str, message: str) -> UserWarningResult:
        """Simulate delivering a voice warning to the protected caller."""
        if self.should_fail:
            logger.warning(
                "MockUserWarningProvider: Simulated delivery failure for session %s", session_id
            )
            return UserWarningResult(
                success=False,
                error=self.fail_error,
                provider="mock",
            )

        warning_id = f"mock-warning-{uuid.uuid4().hex[:8]}"
        record = {
            "warning_id": warning_id,
            "session_id": session_id,
            "message": message,
            "timestamp": time.time(),
        }
        self.delivered_warnings.append(record)
        logger.info(
            "MockUserWarningProvider: Simulated warning delivered for session %s (id=%s)",
            session_id,
            warning_id,
        )
        return UserWarningResult(
            success=True,
            warning_id=warning_id,
            provider="mock",
        )

    def clear(self) -> None:
        """Clear delivered history and reset failure state."""
        self.delivered_warnings.clear()
        self.should_fail = False


class ProtectedUserWarningService:
    """Downstream warning service for notifying the user on the active call (Phase 7C).

    Policy:
    - Downstream strictly of ProtectionDecision (never re-scores raw transcripts).
    - Dispatches a warning only when ProtectionDecision contains an operational
      DASHBOARD_ALERT with status EXECUTED and is at WARNING or CRITICAL_INTERCEPT level.
    - Respects 7A cooldown automatically: if ProtectionDecision has no executed
      DASHBOARD_ALERT due to cooldown suppression, no user warning is generated.
    - Never uses technical jargon, internal risk scores, model numbers, or raw transcripts.
    - Voice messages are designed to be calm, actionable, and suitable for elderly users.
    """

    def __init__(self, default_provider: Optional[BaseUserWarningProvider] = None) -> None:
        self.default_provider = default_provider or MockUserWarningProvider()

    def build_warning_message(self, decision: ProtectionDecision) -> str:
        """Generate a calm, non-technical, actionable warning message for the user."""
        if decision.level == ProtectionLevel.CRITICAL_INTERCEPT:
            return (
                "Warning. This call appears highly suspicious. Please do not share OTPs, "
                "passwords, or send money. Consider ending the call."
            )
        else:
            return (
                "Please be careful. This call may be suspicious. Do not share OTPs, "
                "passwords, or banking details."
            )

    def warn_user(
        self,
        session: CallSession,
        decision: ProtectionDecision,
        provider: Optional[BaseUserWarningProvider] = None,
    ) -> Optional[UserWarningRecord]:
        """Evaluate policy and dispatch a protected-user warning if eligible.

        Args:
            session: Current CallSession.
            decision: ProtectionDecision from ProtectionEngine.
            provider: Optional override provider (defaults to self.default_provider).

        Returns:
            UserWarningRecord if eligible/dispatched, or None if suppressed/ineligible.
        """
        # 1. Policy Filter: User warnings occur ONLY when a real dashboard alert was executed
        has_executed_alert = any(
            action.action_type == ProtectionActionType.DASHBOARD_ALERT
            and action.status == ProtectionActionStatus.EXECUTED
            for action in decision.triggered_actions
        )

        if not has_executed_alert:
            return None

        if decision.level not in [ProtectionLevel.WARNING, ProtectionLevel.CRITICAL_INTERCEPT]:
            return None

        active_provider = provider or self.default_provider
        message = self.build_warning_message(decision)
        now = time.time()

        try:
            result = active_provider.warn_user(session.session_id, message)
            if result.success:
                return UserWarningRecord(
                    warning_id=result.warning_id or str(uuid.uuid4()),
                    session_id=session.session_id,
                    channel=UserWarningChannel.VOICE,
                    message=message,
                    status=UserWarningStatus.DELIVERED,
                    provider=result.provider,
                    timestamp=now,
                    error=None,
                )
            else:
                return UserWarningRecord(
                    warning_id=str(uuid.uuid4()),
                    session_id=session.session_id,
                    channel=UserWarningChannel.VOICE,
                    message=message,
                    status=UserWarningStatus.FAILED,
                    provider=result.provider,
                    timestamp=now,
                    error=result.error or "Delivery failed",
                )
        except Exception as exc:
            logger.exception(
                "Unexpected error delivering user warning for session %s: %s",
                session.session_id,
                exc,
            )
            return UserWarningRecord(
                warning_id=str(uuid.uuid4()),
                session_id=session.session_id,
                channel=UserWarningChannel.VOICE,
                message=message,
                status=UserWarningStatus.FAILED,
                provider="mock",
                timestamp=now,
                error=str(exc),
            )


# Global singleton instance
protected_user_warning_service = ProtectedUserWarningService()
