import logging
import time
from typing import Dict, List, Optional, Set, Tuple

from backend.app.config import settings
from backend.app.models import (
    CallSession,
    ManipulationCategory,
    RiskAssessment,
    RiskTier,
    TacticMatch,
    TranscriptSegment,
)
from ai.tactics import TACTIC_REGISTRY

logger = logging.getLogger("raksha.backend.risk_engine")


class RiskEngine:
    """Dynamic, deterministic, and explainable risk engine for RAKSHA (Phase 2B).

    Consumes TacticMatch results across a conversation and computes a dynamic RiskAssessment.
    Guarantees:
    - Bounded scoring between 0.0 and 100.0.
    - Zero random numbers or synthetic hallucinations.
    - Non-linear co-occurrence escalation when complementary scam tactics combine.
    - Temporal repetition tracking with harmonic diminishing returns and evidence deduplication.
    - Explicit safeguards preventing legitimate urgency from triggering scam alarms.
    - Human-readable explainability for every score change and tier transition.
    """

    BASE_TACTIC_WEIGHT: float = 20.0
    MAX_REPETITION_BONUS_PER_TACTIC: float = 12.0
    ISOLATED_URGENCY_CAP: float = 22.0
    ISOLATED_AUTHORITY_CAP: float = 35.0

    def __init__(self, baseline_score: float = settings.BASELINE_RISK_SCORE) -> None:
        self.baseline_score = baseline_score

    def determine_tier(self, score: float) -> RiskTier:
        """Map a bounded 0-100 score to a deterministic RiskTier."""
        if score < 25.0:
            return RiskTier.SAFE
        elif score < 50.0:
            return RiskTier.LOW
        elif score < 75.0:
            return RiskTier.MEDIUM
        elif score < 90.0:
            return RiskTier.HIGH
        else:
            return RiskTier.CRITICAL

    def calculate_risk(
        self,
        session_id: str,
        new_matches: List[TacticMatch],
        previous_assessment: Optional[RiskAssessment] = None,
    ) -> RiskAssessment:
        """Compute an updated RiskAssessment given new tactic matches and previous state.

        Args:
            session_id: Identifier for the call session.
            new_matches: TacticMatch items detected in the latest segment/utterance.
            previous_assessment: Optional previous assessment state for temporal progression.

        Returns:
            Updated RiskAssessment with score, tier, delta, accumulated tactics, and explanation.
        """
        prev_score = previous_assessment.overall_score if previous_assessment else self.baseline_score
        accumulated_evidence: Set[str] = (
            set(previous_assessment.evidence_segments) if previous_assessment else set()
        )
        accumulated_tactics: Set[ManipulationCategory] = (
            set(previous_assessment.accumulated_tactics) if previous_assessment else set()
        )

        # Track tactic details: category -> dict(max_confidence, evidence_set)
        tactic_stats: Dict[ManipulationCategory, Dict[str, any]] = {}

        # Reconstruct existing state if available from previous_assessment
        if previous_assessment and previous_assessment.tactic_evidence:
            for cat_str, ev_list in previous_assessment.tactic_evidence.items():
                try:
                    category = ManipulationCategory(cat_str)
                    tactic_stats[category] = {
                        "max_confidence": 0.5,
                        "evidence": set(ev_list),
                    }
                except ValueError:
                    pass

        # Filter and deduplicate incoming matches
        fresh_matches: List[TacticMatch] = []
        for match in new_matches:
            cleaned_text = match.evidence_text.strip().lower()
            is_new_evidence = cleaned_text not in accumulated_evidence

            if is_new_evidence:
                accumulated_evidence.add(cleaned_text)
                fresh_matches.append(match)

            if match.tactic not in tactic_stats:
                tactic_stats[match.tactic] = {
                    "max_confidence": match.confidence,
                    "evidence": {cleaned_text},
                }
            else:
                tactic_stats[match.tactic]["max_confidence"] = max(
                    tactic_stats[match.tactic]["max_confidence"], match.confidence
                )
                tactic_stats[match.tactic]["evidence"].add(cleaned_text)

            accumulated_tactics.add(match.tactic)

        # If absolutely no tactics have ever been detected, return pure baseline
        if not accumulated_tactics:
            return RiskAssessment(
                session_id=session_id,
                overall_score=0.0,
                risk_tier=RiskTier.SAFE,
                triggered_tactics=[],
                accumulated_tactics=[],
                evidence_segments=[],
                tactic_evidence={},
                score_delta=0.0 - prev_score,
                explanation="No manipulation tactics detected. Call is in a normal, safe state.",
                timestamp=time.time(),
            )

        # 1. Base Score Calculation per Tactic
        base_scores: Dict[ManipulationCategory, float] = {}
        for category, stats in tactic_stats.items():
            tactic_def = TACTIC_REGISTRY.get(category)
            severity = tactic_def.severity_weight if tactic_def else 0.70
            conf = stats["max_confidence"]

            # Base score = scale * severity * confidence
            tactic_base = self.BASE_TACTIC_WEIGHT * severity * conf

            # Repetition bonus for distinct pieces of evidence (diminishing harmonic returns)
            distinct_count = len(stats["evidence"])
            repetition_bonus = 0.0
            for k in range(2, distinct_count + 1):
                repetition_bonus += 4.0 / k
            repetition_bonus = min(repetition_bonus, self.MAX_REPETITION_BONUS_PER_TACTIC)

            base_scores[category] = tactic_base + repetition_bonus

        raw_sum = sum(base_scores.values())

        # 2. Co-occurrence Multiplier
        num_unique_tactics = len(accumulated_tactics)
        if num_unique_tactics <= 1:
            co_occurrence_mult = 1.0
        elif num_unique_tactics == 2:
            co_occurrence_mult = 1.15
        elif num_unique_tactics == 3:
            co_occurrence_mult = 1.35
        elif num_unique_tactics == 4:
            co_occurrence_mult = 1.50
        else:
            co_occurrence_mult = 1.65

        calculated_score = raw_sum * co_occurrence_mult

        # 3. High-Danger Synergy Bonuses
        synergies_applied: List[str] = []

        # Synergy: Authority + Fear / Arrest Threat
        has_auth = ManipulationCategory.AUTHORITY_IMPERSONATION in accumulated_tactics
        has_fear = ManipulationCategory.FEAR_INTIMIDATION in accumulated_tactics
        has_urgency = ManipulationCategory.URGENCY in accumulated_tactics
        has_financial = (
            ManipulationCategory.FINANCIAL_REDIRECTION in accumulated_tactics
            or ManipulationCategory.INFORMATION_PHISHING in accumulated_tactics
        )
        has_isolation = ManipulationCategory.ISOLATION_SECRECY in accumulated_tactics

        if has_auth and has_fear:
            calculated_score += 8.0
            synergies_applied.append("Authority + Fear synergy (+8.0)")

        # Synergy: Coercive Impending Arrest Triad (Authority + Fear + Urgency)
        if has_auth and has_fear and has_urgency:
            calculated_score += 10.0
            synergies_applied.append("Coercive Impending Arrest Triad (+10.0)")

        # Synergy: Financial Redirection / Phishing + Urgency or Fear
        if has_financial and (has_urgency or has_fear):
            calculated_score += 12.0
            synergies_applied.append("Financial/Phishing + Coercion synergy (+12.0)")

        # Synergy: Full Coercive Scam Nexus (>= 4 high-severity tactics including Authority & Financial/Phishing)
        if num_unique_tactics >= 4 and has_auth and has_financial:
            calculated_score += 15.0
            synergies_applied.append("Full Coercive Scam Nexus (+15.0)")

        # 4. Legitimate Call Safeguards
        safeguards_applied: List[str] = []

        # Safeguard: Isolated Urgency (e.g. hospital emergency, flight delay, doctor's call)
        if num_unique_tactics == 1 and has_urgency:
            if calculated_score > self.ISOLATED_URGENCY_CAP:
                calculated_score = self.ISOLATED_URGENCY_CAP
            safeguards_applied.append(
                f"Isolated urgency safeguard active: capped at {self.ISOLATED_URGENCY_CAP}"
            )

        # Safeguard: Isolated Authority without Coercion (e.g. legitimate bank fraud notice or generic officer intro)
        if num_unique_tactics == 1 and has_auth:
            if calculated_score > self.ISOLATED_AUTHORITY_CAP:
                calculated_score = self.ISOLATED_AUTHORITY_CAP
            safeguards_applied.append(
                f"Isolated authority safeguard active: capped at {self.ISOLATED_AUTHORITY_CAP}"
            )

        # 5. Bound Final Score
        final_score = round(max(0.0, min(100.0, calculated_score)), 1)
        tier = self.determine_tier(final_score)
        delta = round(final_score - prev_score, 1)

        # 6. Generate Human-Readable Explanation
        explanation_parts = []
        if fresh_matches:
            new_tactic_names = ", ".join(m.tactic.value for m in fresh_matches)
            explanation_parts.append(
                f"Score changed by {delta:+.1f} (now {final_score}, {tier.value}) "
                f"due to newly detected tactics: [{new_tactic_names}]."
            )
        elif delta == 0.0:
            explanation_parts.append(
                f"Score remained stable at {final_score} ({tier.value}). "
                f"No new unique manipulation tactics or evidence detected."
            )
        else:
            explanation_parts.append(
                f"Score updated by {delta:+.1f} (now {final_score}, {tier.value})."
            )

        if num_unique_tactics > 1:
            explanation_parts.append(
                f"Co-occurrence multiplier {co_occurrence_mult:.2f}x applied across {num_unique_tactics} unique tactics."
            )
        if synergies_applied:
            explanation_parts.append("; ".join(synergies_applied) + ".")
        if safeguards_applied:
            explanation_parts.append("; ".join(safeguards_applied) + ".")

        full_explanation = " ".join(explanation_parts)

        # Build tactic_evidence mapping for persistence
        tactic_evidence_map: Dict[str, List[str]] = {
            cat.value: list(stats["evidence"]) for cat, stats in tactic_stats.items()
        }

        return RiskAssessment(
            session_id=session_id,
            overall_score=final_score,
            risk_tier=tier,
            triggered_tactics=fresh_matches,
            accumulated_tactics=sorted(list(accumulated_tactics), key=lambda x: x.value),
            evidence_segments=list(accumulated_evidence),
            tactic_evidence=tactic_evidence_map,
            score_delta=delta,
            explanation=full_explanation,
            timestamp=time.time(),
        )

    def evaluate_session(
        self, session: CallSession, new_matches: Optional[List[TacticMatch]] = None
    ) -> RiskAssessment:
        """Evaluate risk for an entire CallSession."""
        matches_to_evaluate = new_matches if new_matches is not None else []
        return self.calculate_risk(
            session_id=session.session_id,
            new_matches=matches_to_evaluate,
            previous_assessment=session.latest_risk,
        )

    def evaluate_segment(
        self, segment: TranscriptSegment, session: Optional[CallSession] = None
    ) -> Tuple[List[TacticMatch], RiskAssessment]:
        """Evaluate a single segment using semantic classifier and update risk."""
        from ai.classifier import semantic_classifier

        matches = semantic_classifier.classify_segment(segment)
        prev_risk = session.latest_risk if session else None
        session_id = session.session_id if session else segment.session_id

        assessment = self.calculate_risk(
            session_id=session_id,
            new_matches=matches,
            previous_assessment=prev_risk,
        )
        return matches, assessment


# Global singleton instance
risk_engine = RiskEngine()
