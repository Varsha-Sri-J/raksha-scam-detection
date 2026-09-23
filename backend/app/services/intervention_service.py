import asyncio
import inspect
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Dict, List, Optional, Set, Union

import httpx

from backend.app.config import settings
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

# Strict Twilio CallSid validation pattern: Starts with CA followed by 32 hex chars
TWILIO_CALL_SID_PATTERN = re.compile(r"^CA[a-f0-9]{32}$")


class TwilioInterventionResult(InterventionResult):
    """Extended InterventionResult carrying exact InterventionStatus for live Twilio operations."""

    status: Optional[InterventionStatus] = None


class BaseInterventionProvider(ABC):
    """Abstract interface for call intervention delivery."""

    @abstractmethod
    def disconnect_call(
        self, session_id: str
    ) -> Union[InterventionResult, Awaitable[InterventionResult]]:
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

    name: str = "mock"

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


class TwilioRESTInterventionProvider(BaseInterventionProvider):
    """Live Twilio REST API call disconnect provider (Phase 7D-2).

    Issues an authenticated HTTP POST to:
    https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Calls/{CallSid}.json
    with Status=completed.

    Safety Guarantees:
    - Enforces strict regex validation on session_id (^CA[a-f0-9]{32}$).
    - Enforces configured Twilio credentials before any outbound HTTP attempt.
    - Uses application/x-www-form-urlencoded body format via httpx.
    - Uses HTTP Basic Authentication safely managed by httpx.
    - Strictly bounded network timeout (settings.TWILIO_API_TIMEOUT_SECONDS, default 3.0s).
    - Secret sanitization: NEVER stores, logs, or raises Twilio auth tokens or Authorization headers.
    - Deterministically identifies itself as 'twilio'.
    """

    name: str = "twilio"

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.timeout_seconds = timeout_seconds

    async def disconnect_call(self, session_id: str) -> TwilioInterventionResult:
        """Issue an HTTP POST to Twilio REST API to terminate the active call."""
        # 1. Strict CallSid validation before ANY network action
        if (
            not session_id
            or not isinstance(session_id, str)
            or not TWILIO_CALL_SID_PATTERN.match(session_id)
        ):
            logger.warning(
                "TwilioRESTInterventionProvider: Rejected non-Twilio or malformed session_id '%s'",
                session_id,
            )
            return TwilioInterventionResult(
                success=False,
                status=InterventionStatus.SKIPPED,
                provider="twilio",
                error=f"Invalid Twilio CallSid format: '{session_id}'",
            )

        # 2. Strict credential validation before ANY network action
        acc_sid = self.account_sid or settings.TWILIO_ACCOUNT_SID
        auth_tok = self.auth_token or settings.TWILIO_AUTH_TOKEN
        if not acc_sid or not auth_tok or not acc_sid.strip() or not auth_tok.strip():
            logger.warning("TwilioRESTInterventionProvider: Missing Twilio credentials")
            return TwilioInterventionResult(
                success=False,
                status=InterventionStatus.FAILED,
                provider="twilio",
                error="Twilio credentials not configured",
            )

        url = f"https://api.twilio.com/2010-04-01/Accounts/{acc_sid}/Calls/{session_id}.json"
        timeout = self.timeout_seconds or settings.TWILIO_API_TIMEOUT_SECONDS or 3.0

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    data={"Status": "completed"},
                    auth=(acc_sid, auth_tok),
                )

            status_code = response.status_code

            # 2xx Success: Call update accepted by Twilio
            if 200 <= status_code < 300:
                action_id = f"twilio-disconnect-{session_id[-8:]}"
                try:
                    resp_data = response.json()
                    if isinstance(resp_data, dict) and resp_data.get("sid"):
                        action_id = resp_data["sid"]
                except Exception:
                    pass

                logger.info(
                    "TwilioRESTInterventionProvider: Successfully requested disconnect for session %s (id=%s)",
                    session_id,
                    action_id,
                )
                return TwilioInterventionResult(
                    success=True,
                    status=InterventionStatus.EXECUTED,
                    intervention_id=action_id,
                    provider="twilio",
                )

            # 404: Call not found or already ended
            elif status_code == 404:
                logger.warning(
                    "TwilioRESTInterventionProvider: Call not found or already ended for session %s (HTTP 404)",
                    session_id,
                )
                return TwilioInterventionResult(
                    success=False,
                    status=InterventionStatus.SKIPPED,
                    provider="twilio",
                    error="Twilio call not found or already ended (HTTP 404)",
                )

            # 400: Rejection (e.g. Call is not in-progress, or invalid parameter)
            elif status_code == 400:
                err_msg = ""
                err_code = None
                try:
                    err_data = response.json()
                    if isinstance(err_data, dict):
                        err_code = err_data.get("code")
                        err_msg = err_data.get("message", "")
                except Exception:
                    pass

                # Twilio code 21220: Call is not in-progress (already completed/ended)
                if (
                    err_code == 21220
                    or "not in-progress" in err_msg.lower()
                    or "already completed" in err_msg.lower()
                ):
                    logger.warning(
                        "TwilioRESTInterventionProvider: Call already completed or not active for session %s (code=%s)",
                        session_id,
                        err_code,
                    )
                    return TwilioInterventionResult(
                        success=False,
                        status=InterventionStatus.SKIPPED,
                        provider="twilio",
                        error=f"Twilio call is not in-progress (code={err_code})",
                    )
                else:
                    logger.error(
                        "TwilioRESTInterventionProvider: Twilio rejected disconnect for session %s (HTTP 400)",
                        session_id,
                    )
                    return TwilioInterventionResult(
                        success=False,
                        status=InterventionStatus.FAILED,
                        provider="twilio",
                        error=f"Twilio rejected request: HTTP 400{f' - {err_msg}' if err_msg else ''}",
                    )

            # 401: Authentication failure
            elif status_code == 401:
                logger.error("TwilioRESTInterventionProvider: Authentication failed (HTTP 401)")
                return TwilioInterventionResult(
                    success=False,
                    status=InterventionStatus.FAILED,
                    provider="twilio",
                    error="Twilio authentication failed: invalid credentials (HTTP 401)",
                )

            # 403: Authorization / permission failure
            elif status_code == 403:
                logger.error("TwilioRESTInterventionProvider: Authorization failed (HTTP 403)")
                return TwilioInterventionResult(
                    success=False,
                    status=InterventionStatus.FAILED,
                    provider="twilio",
                    error="Twilio authorization failed: forbidden (HTTP 403)",
                )

            # 5xx: Twilio server error
            elif status_code >= 500:
                logger.error(
                    "TwilioRESTInterventionProvider: Server error from Twilio (HTTP %s)",
                    status_code,
                )
                return TwilioInterventionResult(
                    success=False,
                    status=InterventionStatus.FAILED,
                    provider="twilio",
                    error=f"Twilio server error: HTTP {status_code}",
                )

            else:
                logger.error(
                    "TwilioRESTInterventionProvider: Unexpected HTTP status %s from Twilio",
                    status_code,
                )
                return TwilioInterventionResult(
                    success=False,
                    status=InterventionStatus.FAILED,
                    provider="twilio",
                    error=f"Twilio returned unexpected status: HTTP {status_code}",
                )

        except httpx.TimeoutException:
            logger.error(
                "TwilioRESTInterventionProvider: Request timed out after %s seconds for session %s",
                timeout,
                session_id,
            )
            return TwilioInterventionResult(
                success=False,
                status=InterventionStatus.FAILED,
                provider="twilio",
                error="Twilio API request timed out",
            )

        except (httpx.NetworkError, httpx.RequestError) as net_err:
            logger.error(
                "TwilioRESTInterventionProvider: Network/transport error for session %s: %s",
                session_id,
                net_err.__class__.__name__,
            )
            return TwilioInterventionResult(
                success=False,
                status=InterventionStatus.FAILED,
                provider="twilio",
                error="Twilio network connection failed",
            )

        except Exception as exc:
            logger.exception(
                "TwilioRESTInterventionProvider: Unexpected error for session %s: %s",
                session_id,
                exc.__class__.__name__,
            )
            return TwilioInterventionResult(
                success=False,
                status=InterventionStatus.FAILED,
                provider="twilio",
                error="Twilio request failed due to an unexpected error",
            )


class InvalidInterventionProvider(BaseInterventionProvider):
    """Safety fallback provider when an invalid/unknown provider is configured."""

    name: str = "invalid"

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        self.name = provider_name

    def disconnect_call(self, session_id: str) -> TwilioInterventionResult:
        logger.error(
            "Invalid intervention provider configured: '%s'. Disconnect rejected.",
            self.provider_name,
        )
        return TwilioInterventionResult(
            success=False,
            status=InterventionStatus.FAILED,
            provider=self.provider_name,
            error=f"Invalid intervention provider configured: '{self.provider_name}'",
        )


def get_intervention_provider(provider_type: Optional[str] = None) -> BaseInterventionProvider:
    """Resolve the intervention provider deterministically from configuration.

    Modes:
    - 'mock' -> MockInterventionProvider
    - 'twilio' -> TwilioRESTInterventionProvider
    - invalid -> InvalidInterventionProvider (explicit failure, no silent mock fallback)
    """
    selected = (
        provider_type if provider_type is not None else settings.INTERVENTION_PROVIDER
    ).strip().lower()
    if selected == "mock":
        return MockInterventionProvider()
    elif selected == "twilio":
        return TwilioRESTInterventionProvider()
    else:
        logger.error(
            "Unknown intervention provider configured: '%s'. Refusing to silently fallback to mock.",
            selected,
        )
        return InvalidInterventionProvider(provider_name=selected)


class InterventionService:
    """Downstream intervention orchestration service for automated call protection (Phase 7D-2).

    Policy:
    - Downstream strictly of ProtectionDecision (never re-scores raw transcripts or embeddings).
    - Disconnect is eligible ONLY when:
        1. ProtectionDecision.level == ProtectionLevel.CRITICAL_INTERCEPT
        2. ProtectionDecision contains an operational DASHBOARD_ALERT with status EXECUTED
        3. Fresh acute extraction tactic present (INFORMATION_PHISHING or FINANCIAL_REDIRECTION)
    - If ProtectionDecision has no executed DASHBOARD_ALERT (e.g. cooldown suppressed), NO intervention.
    - If ProtectionDecision is WARNING / HIGH, NO disconnect.
    - Strict Idempotency: At most ONE disconnect execution per session. Subsequent attempts are SUPPRESSED.
    - Thread-safe & concurrency-safe: Uses session locks and EXECUTING status reservation to serialize
      near-simultaneous duplicate requests and prevent concurrent duplicate network requests.
    """

    def __init__(self, default_provider: Optional[BaseInterventionProvider] = None) -> None:
        self.default_provider = default_provider
        self._session_locks: Dict[str, asyncio.Lock] = {}

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Retrieve or create an asyncio.Lock for a specific session."""
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
            provider: Optional override provider (defaults to self.default_provider or configured provider).

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

        # 4. Resolve active provider deterministically
        active_provider = provider or self.default_provider or get_intervention_provider()
        provider_name = getattr(
            active_provider,
            "name",
            "mock" if isinstance(active_provider, MockInterventionProvider) else "twilio",
        )

        # 5. Acquire session lock to guarantee idempotency against concurrent requests
        lock = self._get_session_lock(session.session_id)
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
                    provider=provider_name,
                    reason="Disconnect already executed for this session",
                    timestamp=now,
                    error=None,
                )

            reason = "Critical scam threshold with acute extraction tactic triggered automated disconnect."

            # Reserve operation before network call using EXECUTING status model
            executing_record = InterventionRecord(
                intervention_id=str(uuid.uuid4()),
                session_id=session.session_id,
                type=InterventionType.DISCONNECT,
                status=InterventionStatus.EXECUTING,
                provider=provider_name,
                reason=reason,
                timestamp=now,
            )
            session.intervention_history.append(executing_record)

            try:
                res_or_coro = active_provider.disconnect_call(session.session_id)
                if inspect.isawaitable(res_or_coro):
                    result = await res_or_coro
                else:
                    result = res_or_coro

                if result.success:
                    final_status = getattr(result, "status", None) or InterventionStatus.EXECUTED
                    executing_record.status = final_status
                    executing_record.intervention_id = result.intervention_id or executing_record.intervention_id
                    executing_record.provider = result.provider
                    executing_record.error = None
                    return executing_record
                else:
                    final_status = getattr(result, "status", None) or InterventionStatus.FAILED
                    executing_record.status = final_status
                    executing_record.provider = result.provider
                    executing_record.error = result.error or "Disconnect execution failed"
                    return executing_record

            except Exception as exc:
                logger.exception(
                    "Unexpected error executing disconnect intervention for session %s: %s",
                    session.session_id,
                    exc,
                )
                executing_record.status = InterventionStatus.FAILED
                executing_record.provider = provider_name
                executing_record.error = str(exc)
                return executing_record


# Global singleton instance
intervention_service = InterventionService()
