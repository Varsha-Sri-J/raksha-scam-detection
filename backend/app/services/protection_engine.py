import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from backend.app.models import (
    ManipulationCategory,
    ProtectionAction,
    ProtectionActionStatus,
    ProtectionActionType,
    ProtectionDecision,
    ProtectionLevel,
    RiskAssessment,
    RiskTier,
    TranscriptSegment,
)

logger = logging.getLogger("raksha.backend.protection_engine")

# Constant: Bounded alert cooldown window (seconds)
ALERT_COOLDOWN_SECONDS: float = 20.0

# Canonical acute manipulation tactics that warrant immediate escalation override
# even if the session is already in a high/critical state.
ACUTE_ESCALATION_TACTICS: Set[ManipulationCategory] = {
    ManipulationCategory.INFORMATION_PHISHING,  # OTP / Credential extraction
    ManipulationCategory.FINANCIAL_REDIRECTION,  # Immediate fund transfer / gift card demand
}


@dataclass
class _SessionProtectionState:
    """Thread-safe, isolated in-memory tracking of protection state per session."""

    last_alert_timestamp: Optional[float] = None
    last_alert_level: Optional[ProtectionLevel] = None
    last_evaluated_level: ProtectionLevel = ProtectionLevel.MONITORING
    last_score: float = 0.0
    alert_count: int = 0
    updated_at: float = field(default_factory=time.time)


class ProtectionEngine:
    """Deterministic Protection and Alert Engine for RAKSHA (Phase 7A).

    Downstream consumer of RiskAssessment. Responsible for:
    - Mapping RiskTier to deterministic ProtectionLevel.
    - Generating operational DASHBOARD_ALERT actions.
    - Applying session-isolated alert cooldowns to prevent alert fatigue.
    - Enforcing escalation bypasses (HIGH -> CRITICAL, acute credential/financial extraction).
    - Recording deterministic ProtectionDecision audit records.

    Guarantees:
    - Pure, deterministic policy execution (zero random values, zero sleeps).
    - Time injection support for fully synchronous, un-delayed unit testing.
    - Strict session isolation (cooldown in Session A never affects Session B).
    - Zero external side-effects (telephony or SMS).
    """

    def __init__(self, cooldown_seconds: float = ALERT_COOLDOWN_SECONDS) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._session_states: Dict[str, _SessionProtectionState] = {}

    def _get_or_create_state(self, session_id: str, now: float) -> _SessionProtectionState:
        """Retrieve or initialize isolated protection state for a session."""
        if session_id not in self._session_states:
            self._session_states[session_id] = _SessionProtectionState(updated_at=now)
        return self._session_states[session_id]

    def reset_session(self, session_id: str) -> None:
        """Clear isolation state for a given session."""
        if session_id in self._session_states:
            del self._session_states[session_id]

    def clear(self) -> None:
        """Clear all session states (test teardown)."""
        self._session_states.clear()

    def prune_stale_sessions(self, max_age_seconds: float = 86400.0, current_time: Optional[float] = None) -> int:
        """Evict sessions inactive longer than max_age_seconds to prevent memory growth."""
        now = current_time if current_time is not None else time.time()
        stale_keys = [
            sid for sid, state in self._session_states.items()
            if now - state.updated_at > max_age_seconds
        ]
        for sid in stale_keys:
            del self._session_states[sid]
        return len(stale_keys)

    def evaluate(
        self,
        session_id: str,
        risk_assessment: RiskAssessment,
        segment: Optional[TranscriptSegment] = None,
        current_time: Optional[float] = None,
    ) -> ProtectionDecision:
        """Evaluate protection policy deterministically given risk and transcript context.

        Args:
            session_id: The ID of the monitored call session.
            risk_assessment: Output from RiskEngine.
            segment: Optional latest transcript segment triggering this evaluation.
            current_time: Optional injected timestamp for deterministic testing.

        Returns:
            ProtectionDecision with level, triggered_actions, cooldown_applied, and escalation flag.
        """
        now = current_time if current_time is not None else time.time()
        state = self._get_or_create_state(session_id, now)
        state.updated_at = now

        score = risk_assessment.overall_score
        tier = risk_assessment.risk_tier

        # 1. Map RiskTier to ProtectionLevel
        if tier in [RiskTier.SAFE, RiskTier.LOW]:
            level = ProtectionLevel.MONITORING
        elif tier == RiskTier.MEDIUM:
            level = ProtectionLevel.ADVISORY
        elif tier == RiskTier.HIGH:
            level = ProtectionLevel.WARNING
        else:  # RiskTier.CRITICAL
            level = ProtectionLevel.CRITICAL_INTERCEPT

        # 2. Check for Acute Extraction Tactics in fresh matches
        fresh_tactics: Set[ManipulationCategory] = set()
        if risk_assessment.triggered_tactics:
            for m in risk_assessment.triggered_tactics:
                fresh_tactics.add(m.tactic)

        has_acute_tactic = bool(fresh_tactics.intersection(ACUTE_ESCALATION_TACTICS))

        # 3. Determine Escalation Status
        # Escalation occurs if:
        # a) Transitioning from lower level to CRITICAL_INTERCEPT (e.g. WARNING -> CRITICAL_INTERCEPT)
        # b) Fresh acute credential/financial extraction tactic observed in high/critical tier
        prev_level = state.last_evaluated_level
        is_tier_escalation = (
            prev_level != ProtectionLevel.CRITICAL_INTERCEPT
            and level == ProtectionLevel.CRITICAL_INTERCEPT
        )
        is_tactic_escalation = (
            level in [ProtectionLevel.WARNING, ProtectionLevel.CRITICAL_INTERCEPT]
            and has_acute_tactic
        )
        is_escalation = is_tier_escalation or is_tactic_escalation

        state.last_evaluated_level = level
        state.last_score = score

        # 4. Policy Execution by ProtectionLevel
        triggered_actions: List[ProtectionAction] = []
        cooldown_applied = False
        explanation_parts: List[str] = []

        if level == ProtectionLevel.MONITORING:
            explanation_parts.append(
                f"Risk tier is {tier.value} ({score:.1f}). Call is in baseline monitoring state."
            )

        elif level == ProtectionLevel.ADVISORY:
            explanation_parts.append(
                f"Risk tier is {tier.value} ({score:.1f}). Elevated manipulation indicators detected; "
                f"heightened advisory monitoring active."
            )

        elif level in [ProtectionLevel.WARNING, ProtectionLevel.CRITICAL_INTERCEPT]:
            # Cooldown Evaluation:
            # Check elapsed time since the last alert was fired for this session.
            last_alert_time = state.last_alert_timestamp
            in_cooldown = (
                last_alert_time is not None
                and (now - last_alert_time) < self.cooldown_seconds
            )

            # Determine whether to fire or suppress
            if in_cooldown and not is_escalation:
                cooldown_applied = True
                elapsed = now - last_alert_time
                remaining = self.cooldown_seconds - elapsed
                explanation_parts.append(
                    f"{level.value} alert active ({score:.1f}); repeated alert suppressed "
                    f"under {self.cooldown_seconds:.0f}s cooldown ({remaining:.1f}s remaining)."
                )
            else:
                # Alert triggers: either out of cooldown or escalation bypasses cooldown
                state.last_alert_timestamp = now
                state.last_alert_level = level
                state.alert_count += 1

                if is_tier_escalation:
                    override_reason = "Escalation to CRITICAL tier"
                elif is_tactic_escalation:
                    matching_acute = [t.value for t in fresh_tactics.intersection(ACUTE_ESCALATION_TACTICS)]
                    override_reason = f"Acute extraction tactic observed [{', '.join(matching_acute)}]"
                else:
                    override_reason = None

                if in_cooldown and override_reason:
                    explanation_parts.append(
                        f"{override_reason} bypassed cooldown. Immediate alert triggered ({score:.1f})."
                    )
                else:
                    explanation_parts.append(
                        f"{level.value} threat threshold reached ({score:.1f}). "
                        f"Dashboard alert dispatched."
                    )

                action_msg = (
                    f"{level.value}: Overall threat score {score:.1f} ({tier.value}). "
                    f"{risk_assessment.explanation}"
                )

                action = ProtectionAction(
                    action_type=ProtectionActionType.DASHBOARD_ALERT,
                    level=level,
                    recipient="dashboard",
                    message=action_msg,
                    status=ProtectionActionStatus.EXECUTED,
                    timestamp=now,
                )
                triggered_actions.append(action)

        full_explanation = " ".join(explanation_parts)

        return ProtectionDecision(
            session_id=session_id,
            level=level,
            triggered_actions=triggered_actions,
            trigger_score=score,
            trigger_tier=tier,
            is_escalation=is_escalation,
            cooldown_applied=cooldown_applied,
            explanation=full_explanation,
            timestamp=now,
        )


# Global singleton instance
protection_engine = ProtectionEngine()
