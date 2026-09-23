import asyncio
import inspect
import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Dict, List, Optional, Union

import httpx

from backend.app.config import settings
from backend.app.models import (
    CallSession,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionDecision,
    ProtectionLevel,
    SessionStatus,
    UserWarningChannel,
    UserWarningRecord,
    UserWarningResult,
    UserWarningStatus,
)
from backend.app.services.session_store import session_store

logger = logging.getLogger("raksha.backend.user_warning_service")


class BaseUserWarningProvider(ABC):
    """Abstract interface for protected-user warning delivery."""

    @abstractmethod
    def warn_user(
        self,
        session_id: str,
        message: str,
        session: Optional[CallSession] = None,
    ) -> Union[UserWarningResult, Awaitable[UserWarningResult]]:
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

    name: str = "mock"

    def __init__(
        self,
        should_fail: bool = False,
        fail_error: str = "Simulated voice warning delivery failure",
    ) -> None:
        self.should_fail = should_fail
        self.fail_error = fail_error
        self.delivered_warnings: List[Dict[str, Any]] = []

    def warn_user(
        self,
        session_id: str,
        message: str,
        session: Optional[CallSession] = None,
    ) -> UserWarningResult:
        """Simulate delivering a voice warning to the protected caller."""
        if self.should_fail:
            logger.warning(
                "MockUserWarningProvider: Simulated delivery failure for session %s", session_id
            )
            return UserWarningResult(
                success=False,
                status=UserWarningStatus.FAILED,
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
            status=UserWarningStatus.DELIVERED,
            provider="mock",
        )

    def clear(self) -> None:
        """Clear delivered history and reset failure state."""
        self.delivered_warnings.clear()
        self.should_fail = False


class TwilioConferenceUserWarningProvider(BaseUserWarningProvider):
    """Live Twilio Conference Participant AnnounceUrl warning provider (Phase 7D-3C-2).

    Issues an authenticated HTTP POST to:
    https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Conferences/{ConferenceSid}/Participants/{CallSid}.json
    with AnnounceUrl and AnnounceMethod=POST.

    Safety Guarantees:
    - Target Isolation: strictly targets session.protected_user_call_sid. Scammer leg is NEVER targeted.
    - Media Isolation: Audio is delivered exclusively to the protected user's ear via AnnounceUrl.
      Never uses Media Stream injection or <Connect><Stream>.
    - Call State Safety: Verifies session is not ended and protected_user_connected is True before calling Twilio.
    - Bounded Timeout: Uses bounded HTTP timeout (settings.TWILIO_API_TIMEOUT_SECONDS, default 3.0s).
    - Secret Sanitization: Never logs Twilio auth tokens, credentials, or Authorization headers.
    - Deterministic Status Progression: 200/201 -> QUEUED; callback -> DELIVERED/FAILED.
    """

    name: str = "twilio_conference"

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url

    async def warn_user(
        self,
        session_id: str,
        message: str,
        session: Optional[CallSession] = None,
    ) -> UserWarningResult:
        """Deliver a protected-user-only announcement via Twilio Conference Participant API."""
        # 1. Resolve credentials first
        acc_sid = self.account_sid or settings.TWILIO_ACCOUNT_SID
        auth_tok = self.auth_token or settings.TWILIO_AUTH_TOKEN
        if not acc_sid or not auth_tok:
            logger.error(
                "TwilioConferenceUserWarningProvider: Missing Twilio credentials (account_sid or auth_token)"
            )
            return UserWarningResult(
                success=False,
                status=UserWarningStatus.FAILED,
                provider="twilio_conference",
                error="Twilio credentials not configured",
            )

        # 2. Resolve CallSession
        resolved_session = session or await session_store.get_session(session_id)
        if not resolved_session:
            logger.warning(
                "TwilioConferenceUserWarningProvider: CallSession %s not found", session_id
            )
            return UserWarningResult(
                success=False,
                status=UserWarningStatus.SKIPPED,
                provider="twilio_conference",
                error=f"CallSession {session_id} not found",
            )

        # 3. Check conference lifecycle: conference already ended?
        if resolved_session.status == SessionStatus.ENDED:
            logger.warning(
                "TwilioConferenceUserWarningProvider: Conference already ended for session %s",
                session_id,
            )
            return UserWarningResult(
                success=False,
                status=UserWarningStatus.SKIPPED,
                provider="twilio_conference",
                error="Conference already ended",
            )

        # 4. Check conference SID availability
        if not resolved_session.conference_sid:
            logger.warning(
                "TwilioConferenceUserWarningProvider: Conference SID missing for session %s",
                session_id,
            )
            return UserWarningResult(
                success=False,
                status=UserWarningStatus.SKIPPED,
                provider="twilio_conference",
                error="Conference SID not available for session",
            )

        # 5. Check protected user CallSid availability
        if not resolved_session.protected_user_call_sid:
            logger.warning(
                "TwilioConferenceUserWarningProvider: Protected user CallSid missing for session %s",
                session_id,
            )
            return UserWarningResult(
                success=False,
                status=UserWarningStatus.SKIPPED,
                provider="twilio_conference",
                error="Protected user CallSid not available for session",
            )

        # 6. Check protected user connected gate (Correction 1)
        # Note: Do not silently assume the local join callback state is perfectly synchronized
        # with the warning decision. If local state has not verified the protected user is connected,
        # we do not make an unsafe announcement and safely skip.
        if not resolved_session.protected_user_connected:
            logger.warning(
                "TwilioConferenceUserWarningProvider: Protected user is not verified connected "
                "(state unknown or pending join callback) for session %s; skipping announcement",
                session_id,
            )
            return UserWarningResult(
                success=False,
                status=UserWarningStatus.SKIPPED,
                provider="twilio_conference",
                error="Protected user participant is not verified connected",
            )

        # 7. Strict Target Isolation: Assert scammer / parent leg is NEVER targeted
        target_call_sid = resolved_session.protected_user_call_sid
        if target_call_sid == resolved_session.parent_call_sid:
            logger.critical(
                "SAFETY VIOLATION PREVENTED: Attempted to target parent/scammer leg %s for warning announcement!",
                target_call_sid,
            )
            return UserWarningResult(
                success=False,
                status=UserWarningStatus.FAILED,
                provider="twilio_conference",
                error="Safety violation: protected user CallSid matches parent/scammer CallSid",
            )

        # 8. Build unique warning_id and AnnounceUrl for deterministic correlation (Correction 2)
        warning_id = f"twilio-warning-{uuid.uuid4().hex[:8]}"
        base_url = self.base_url or settings.TWILIO_STREAM_BASE_URL or "http://localhost:8000"
        base_url = base_url.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
        announce_url = f"{base_url}/api/twilio/voice/warning-twiml/{session_id}?warning_id={warning_id}"

        api_url = (
            f"https://api.twilio.com/2010-04-01/Accounts/{acc_sid}/Conferences/"
            f"{resolved_session.conference_sid}/Participants/{target_call_sid}.json"
        )
        payload = {
            "AnnounceUrl": announce_url,
            "AnnounceMethod": "POST",
        }
        timeout = (
            self.timeout_seconds
            if self.timeout_seconds is not None
            else settings.TWILIO_API_TIMEOUT_SECONDS
        )

        logger.info(
            "TwilioConferenceUserWarningProvider: Requesting announcement on participant %s for session %s (warning_id=%s)",
            target_call_sid,
            session_id,
            warning_id,
        )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    api_url,
                    data=payload,
                    auth=(acc_sid, auth_tok),
                    headers={"Accept": "application/json"},
                )

            status_code = response.status_code

            if 200 <= status_code < 300:
                logger.info(
                    "Twilio accepted announcement request for session %s (status=%s, warning_id=%s)",
                    session_id,
                    status_code,
                    warning_id,
                )
                return UserWarningResult(
                    success=True,
                    warning_id=warning_id,
                    status=UserWarningStatus.QUEUED,
                    provider="twilio_conference",
                )
            elif status_code == 404:
                logger.warning(
                    "TwilioConferenceUserWarningProvider: Participant %s or conference %s not found (HTTP 404)",
                    target_call_sid,
                    resolved_session.conference_sid,
                )
                return UserWarningResult(
                    success=False,
                    warning_id=warning_id,
                    status=UserWarningStatus.FAILED,
                    provider="twilio_conference",
                    error="Conference or participant not found (HTTP 404)",
                )
            elif status_code in [401, 403]:
                logger.error(
                    "TwilioConferenceUserWarningProvider: Authentication/Authorization failed (HTTP %s)",
                    status_code,
                )
                return UserWarningResult(
                    success=False,
                    warning_id=warning_id,
                    status=UserWarningStatus.FAILED,
                    provider="twilio_conference",
                    error=f"Twilio authentication/authorization failed (HTTP {status_code})",
                )
            elif status_code == 429:
                logger.error("TwilioConferenceUserWarningProvider: Rate limited (HTTP 429)")
                return UserWarningResult(
                    success=False,
                    warning_id=warning_id,
                    status=UserWarningStatus.FAILED,
                    provider="twilio_conference",
                    error="Twilio rate limit exceeded (HTTP 429)",
                )
            elif status_code >= 500:
                logger.error(
                    "TwilioConferenceUserWarningProvider: Server error from Twilio (HTTP %s)",
                    status_code,
                )
                return UserWarningResult(
                    success=False,
                    warning_id=warning_id,
                    status=UserWarningStatus.FAILED,
                    provider="twilio_conference",
                    error=f"Twilio server error: HTTP {status_code}",
                )
            else:
                logger.error(
                    "TwilioConferenceUserWarningProvider: Unexpected HTTP status %s from Twilio",
                    status_code,
                )
                return UserWarningResult(
                    success=False,
                    warning_id=warning_id,
                    status=UserWarningStatus.FAILED,
                    provider="twilio_conference",
                    error=f"Twilio returned unexpected status: HTTP {status_code}",
                )

        except httpx.TimeoutException:
            logger.error(
                "TwilioConferenceUserWarningProvider: Request timed out after %s seconds for session %s",
                timeout,
                session_id,
            )
            return UserWarningResult(
                success=False,
                warning_id=warning_id,
                status=UserWarningStatus.FAILED,
                provider="twilio_conference",
                error="Twilio API request timed out",
            )
        except (httpx.NetworkError, httpx.RequestError) as net_err:
            logger.error(
                "TwilioConferenceUserWarningProvider: Network error for session %s: %s",
                session_id,
                net_err.__class__.__name__,
            )
            return UserWarningResult(
                success=False,
                warning_id=warning_id,
                status=UserWarningStatus.FAILED,
                provider="twilio_conference",
                error="Twilio network connection failed",
            )
        except Exception as exc:
            logger.exception(
                "TwilioConferenceUserWarningProvider: Unexpected error for session %s: %s",
                session_id,
                exc.__class__.__name__,
            )
            return UserWarningResult(
                success=False,
                warning_id=warning_id,
                status=UserWarningStatus.FAILED,
                provider="twilio_conference",
                error="Twilio announcement failed due to an unexpected error",
            )


class InvalidUserWarningProvider(BaseUserWarningProvider):
    """Safety fallback provider when an invalid/unknown user warning provider is configured."""

    name: str = "invalid"

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        self.name = provider_name

    def warn_user(
        self,
        session_id: str,
        message: str,
        session: Optional[CallSession] = None,
    ) -> UserWarningResult:
        logger.error(
            "Invalid user warning provider configured: '%s'. Delivery rejected.",
            self.provider_name,
        )
        return UserWarningResult(
            success=False,
            status=UserWarningStatus.FAILED,
            provider=self.provider_name,
            error=f"Invalid user warning provider configured: '{self.provider_name}'",
        )


def get_user_warning_provider(provider_type: Optional[str] = None) -> BaseUserWarningProvider:
    """Resolve the user warning provider deterministically from configuration.

    Modes:
    - 'mock' -> MockUserWarningProvider
    - 'twilio_conference' -> TwilioConferenceUserWarningProvider
    - invalid -> InvalidUserWarningProvider (explicit failure, no silent mock fallback)
    """
    selected = (
        provider_type if provider_type is not None else settings.USER_WARNING_PROVIDER
    ).strip().lower()

    if selected == "mock":
        return MockUserWarningProvider()
    elif selected == "twilio_conference":
        return TwilioConferenceUserWarningProvider()
    else:
        logger.error(
            "Unknown user warning provider configured: '%s'. Refusing to silently fallback to mock.",
            selected,
        )
        return InvalidUserWarningProvider(provider_name=selected)


class ProtectedUserWarningService:
    """Downstream warning service for notifying the user on the active call (Phase 7C / 7D-3C-2).

    Policy:
    - Downstream strictly of ProtectionDecision (never re-scores raw transcripts).
    - Dispatches a warning only when ProtectionDecision contains an operational
      DASHBOARD_ALERT with status EXECUTED and is at WARNING or CRITICAL_INTERCEPT level.
    - Respects 7A cooldown automatically: if ProtectionDecision has no executed
      DASHBOARD_ALERT due to cooldown suppression, no user warning is generated.
    - Never uses technical jargon, internal risk scores, model numbers, or raw transcripts.
    - Voice messages are designed to be calm, actionable, and suitable for elderly users.
    - Suppresses duplicate announcements if a warning is already in-flight (QUEUED).
    """

    def __init__(self, default_provider: Optional[BaseUserWarningProvider] = None) -> None:
        self._custom_provider = default_provider

    @property
    def default_provider(self) -> BaseUserWarningProvider:
        if self._custom_provider is not None:
            return self._custom_provider
        return get_user_warning_provider()

    @default_provider.setter
    def default_provider(self, provider: Optional[BaseUserWarningProvider]) -> None:
        self._custom_provider = provider

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

    def _create_record_from_result(
        self,
        result: UserWarningResult,
        session: CallSession,
        message: str,
        now: float,
    ) -> UserWarningRecord:
        if result.success:
            record_status = result.status or UserWarningStatus.DELIVERED
            return UserWarningRecord(
                warning_id=result.warning_id or str(uuid.uuid4()),
                session_id=session.session_id,
                channel=UserWarningChannel.VOICE,
                message=message,
                status=record_status,
                provider=result.provider,
                timestamp=now,
                error=None,
            )
        else:
            record_status = result.status or UserWarningStatus.FAILED
            return UserWarningRecord(
                warning_id=result.warning_id or str(uuid.uuid4()),
                session_id=session.session_id,
                channel=UserWarningChannel.VOICE,
                message=message,
                status=record_status,
                provider=result.provider,
                timestamp=now,
                error=result.error or "Delivery failed",
            )

    def warn_user(
        self,
        session: CallSession,
        decision: ProtectionDecision,
        provider: Optional[BaseUserWarningProvider] = None,
    ) -> Union[Optional[UserWarningRecord], Awaitable[Optional[UserWarningRecord]]]:
        """Evaluate policy and dispatch a protected-user warning if eligible.

        Supports both synchronous providers (MockUserWarningProvider) and asynchronous
        providers (TwilioConferenceUserWarningProvider).
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

        # 2. Idempotency: Suppress duplicate announcement if one is already in-flight (QUEUED)
        if any(rec.status == UserWarningStatus.QUEUED for rec in session.user_warning_history):
            logger.info(
                "A warning announcement is already in-flight (QUEUED) for session %s; skipping duplicate",
                session.session_id,
            )
            return None

        active_provider = provider or self.default_provider
        message = self.build_warning_message(decision)
        now = time.time()

        try:
            try:
                raw_res = active_provider.warn_user(session.session_id, message, session=session)
            except TypeError:
                raw_res = active_provider.warn_user(session.session_id, message)

            if inspect.isawaitable(raw_res):
                async def _async_warn() -> UserWarningRecord:
                    try:
                        res = await raw_res
                        return self._create_record_from_result(res, session, message, now)
                    except Exception as async_exc:
                        logger.exception(
                            "Unexpected async error delivering user warning for session %s: %s",
                            session.session_id,
                            async_exc,
                        )
                        return UserWarningRecord(
                            warning_id=str(uuid.uuid4()),
                            session_id=session.session_id,
                            channel=UserWarningChannel.VOICE,
                            message=message,
                            status=UserWarningStatus.FAILED,
                            provider=getattr(active_provider, "name", "unknown"),
                            timestamp=now,
                            error=str(async_exc),
                        )

                return _async_warn()
            else:
                return self._create_record_from_result(raw_res, session, message, now)

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
                provider=getattr(active_provider, "name", "mock"),
                timestamp=now,
                error=str(exc),
            )

    async def warn_user_async(
        self,
        session: CallSession,
        decision: ProtectionDecision,
        provider: Optional[BaseUserWarningProvider] = None,
    ) -> Optional[UserWarningRecord]:
        """Explicit async helper for awaiting user warning evaluation."""
        res = self.warn_user(session, decision, provider=provider)
        if inspect.isawaitable(res):
            return await res
        return res


# Global singleton instance
protected_user_warning_service = ProtectedUserWarningService()
