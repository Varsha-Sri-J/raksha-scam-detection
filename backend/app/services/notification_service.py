import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from backend.app.models import (
    CallSession,
    NotificationChannel,
    NotificationRecord,
    NotificationResult,
    NotificationStatus,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionDecision,
    ProtectionLevel,
)

logger = logging.getLogger("raksha.backend.notification_service")


class BaseNotificationProvider(ABC):
    """Abstract interface for external notification delivery."""

    @abstractmethod
    def send_sms(self, recipient: str, message: str) -> NotificationResult:
        """Deliver an SMS notification to the given recipient."""
        pass


class MockSMSProvider(BaseNotificationProvider):
    """Deterministic simulated SMS provider for testing and demonstration.

    Guarantees:
    - Zero external network requests or telephony API calls.
    - Deterministic message ID generation and delivery tracking.
    - Explicit failure toggling for resilient failure-mode testing.
    """

    def __init__(
        self,
        should_fail: bool = False,
        fail_error: str = "Simulated SMS delivery failure",
    ) -> None:
        self.should_fail = should_fail
        self.fail_error = fail_error
        self.sent_messages: List[Dict[str, Any]] = []

    def send_sms(self, recipient: str, message: str) -> NotificationResult:
        """Simulate delivering an SMS."""
        if self.should_fail:
            logger.warning("MockSMSProvider: Simulated delivery failure to %s", recipient)
            return NotificationResult(
                success=False,
                error=self.fail_error,
                provider="mock",
            )

        msg_id = f"mock-sms-{uuid.uuid4().hex[:8]}"
        record = {
            "message_id": msg_id,
            "recipient": recipient,
            "message": message,
            "timestamp": time.time(),
        }
        self.sent_messages.append(record)
        logger.info("MockSMSProvider: Simulated SMS delivered to %s (id=%s)", recipient, msg_id)
        return NotificationResult(
            success=True,
            message_id=msg_id,
            provider="mock",
        )

    def clear(self) -> None:
        """Clear sent history and reset failure state."""
        self.sent_messages.clear()
        self.should_fail = False


class CaregiverNotificationService:
    """Downstream notification service for family and caregiver alerting (Phase 7B).

    Policy:
    - Downstream strictly of ProtectionDecision (never re-scores raw transcripts).
    - Dispatches notifications only when ProtectionDecision contains an operational
      DASHBOARD_ALERT and is at WARNING or CRITICAL_INTERCEPT level.
    - Respects 7A cooldown automatically: if ProtectionDecision has no DASHBOARD_ALERT
      due to cooldown suppression, no caregiver notification is generated.
    - Constructs concise, non-invasive safety advisories without leaking call transcripts.
    """

    def __init__(self, default_provider: Optional[BaseNotificationProvider] = None) -> None:
        self.default_provider = default_provider or MockSMSProvider()

    def build_caregiver_message(
        self, session: CallSession, decision: ProtectionDecision
    ) -> str:
        """Generate a concise, safe message without exposing sensitive transcript contents."""
        callee_name = session.callee_id or "the protected user"
        tier_str = decision.trigger_tier.value

        if decision.level == ProtectionLevel.CRITICAL_INTERCEPT:
            return (
                f"RAKSHA CRITICAL ALERT: A critical scam/coercion call was detected for {callee_name}. "
                f"Risk level: {tier_str}. Please check on them immediately."
            )
        else:
            return (
                f"RAKSHA ALERT: A high-risk suspicious call was detected for {callee_name}. "
                f"Risk level: {tier_str}. Active monitoring engaged. Please check on them."
            )

    def dispatch_notifications(
        self,
        session: CallSession,
        decision: ProtectionDecision,
        provider: Optional[BaseNotificationProvider] = None,
    ) -> List[NotificationRecord]:
        """Dispatch notifications to configured caregiver contacts based on ProtectionDecision.

        Args:
            session: Current CallSession with caregiver_contacts.
            decision: ProtectionDecision from ProtectionEngine.
            provider: Optional override provider (defaults to self.default_provider).

        Returns:
            List of generated NotificationRecord items.
        """
        # 1. Policy Filter: Caregivers are alerted ONLY when a real dashboard alert was executed
        has_executed_alert = any(
            action.action_type == ProtectionActionType.DASHBOARD_ALERT
            and action.status == ProtectionActionStatus.EXECUTED
            for action in decision.triggered_actions
        )

        if not has_executed_alert:
            return []

        if decision.level not in [ProtectionLevel.WARNING, ProtectionLevel.CRITICAL_INTERCEPT]:
            return []

        if not session.caregiver_contacts:
            return []

        active_provider = provider or self.default_provider
        message = self.build_caregiver_message(session, decision)
        now = time.time()
        records: List[NotificationRecord] = []

        for contact in session.caregiver_contacts:
            if not contact.enabled:
                record = NotificationRecord(
                    session_id=session.session_id,
                    channel=NotificationChannel.SMS,
                    recipient=contact.phone_number,
                    message=message,
                    status=NotificationStatus.SKIPPED,
                    provider="mock",
                    timestamp=now,
                    error="Caregiver contact is disabled",
                )
                records.append(record)
                continue

            try:
                result = active_provider.send_sms(contact.phone_number, message)
                if result.success:
                    record = NotificationRecord(
                        session_id=session.session_id,
                        channel=NotificationChannel.SMS,
                        recipient=contact.phone_number,
                        message=message,
                        status=NotificationStatus.SENT,
                        provider=result.provider,
                        timestamp=now,
                        error=None,
                    )
                else:
                    record = NotificationRecord(
                        session_id=session.session_id,
                        channel=NotificationChannel.SMS,
                        recipient=contact.phone_number,
                        message=message,
                        status=NotificationStatus.FAILED,
                        provider=result.provider,
                        timestamp=now,
                        error=result.error or "Delivery failed",
                    )
            except Exception as exc:
                logger.exception("Unexpected error delivering notification to %s: %s", contact.phone_number, exc)
                record = NotificationRecord(
                    session_id=session.session_id,
                    channel=NotificationChannel.SMS,
                    recipient=contact.phone_number,
                    message=message,
                    status=NotificationStatus.FAILED,
                    provider="mock",
                    timestamp=now,
                    error=str(exc),
                )

            records.append(record)

        return records


# Global singleton instance
caregiver_notification_service = CaregiverNotificationService()
