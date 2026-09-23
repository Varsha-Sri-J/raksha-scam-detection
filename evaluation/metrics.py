"""Metrics calculation for the RAKSHA offline evaluation harness (Phase 8B).

Calculates aggregate operational metrics and ground-truth comparisons while
strictly distinguishing observed runtime behaviors from evaluation annotations.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from evaluation.models import EvaluationScenarioResult


class EvaluationMetrics(BaseModel):
    """Structured aggregate metrics across an evaluation scenario run."""

    # Volume metrics
    scenario_count: int = 0
    segment_count: int = 0
    category_counts: Dict[str, int] = Field(default_factory=dict)

    # Observed Tactic Metrics
    tactic_detection_counts: Dict[str, int] = Field(default_factory=dict)
    total_tactic_detections: int = 0

    # Ground-truth comparison (where expectations are annotated)
    expected_tactic_annotations_count: int = 0
    expected_tactics_matched_count: int = 0
    expected_tactic_detection_rate: Optional[float] = None

    # False-positive analysis (benign & legitimate urgency)
    benign_or_legitimate_count: int = 0
    false_positive_count: int = 0
    false_positive_rate: float = 0.0
    benign_false_positive_count: int = 0
    legitimate_urgency_escalation_count: int = 0

    # Peak Tier Distribution
    peak_tier_distribution: Dict[str, int] = Field(
        default_factory=lambda: {"SAFE": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    )

    # Progression Timing Metrics (mean segment index of initial triggers)
    first_detection_segment_mean: Optional[float] = None
    first_warning_segment_mean: Optional[float] = None
    first_critical_segment_mean: Optional[float] = None
    intervention_segment_mean: Optional[float] = None

    # Downstream Protection Action Counts
    total_alerts_executed: int = 0
    caregiver_alert_count: int = 0
    user_warning_count: int = 0
    intervention_count: int = 0

    # Downstream Failure Containment
    downstream_failure_scenario_count: int = 0
    downstream_failure_isolated_count: int = 0
    downstream_failure_isolation_rate: float = 1.0


def calculate_metrics(results: List[EvaluationScenarioResult]) -> EvaluationMetrics:
    """Compute deterministic metrics across a list of scenario results."""
    metrics = EvaluationMetrics(
        scenario_count=len(results),
        segment_count=sum(len(r.segment_results) for r in results),
    )

    if not results:
        return metrics

    # Category counts
    for r in results:
        metrics.category_counts[r.category] = metrics.category_counts.get(r.category, 0) + 1

    # Tactic detections & expected tactic comparisons
    total_expected_matches = 0
    total_expected_annotations = 0

    detection_segments: List[int] = []
    warning_segments: List[int] = []
    critical_segments: List[int] = []
    intervention_segments: List[int] = []

    for r in results:
        # Peak tier distribution
        metrics.peak_tier_distribution[r.peak_tier] = (
            metrics.peak_tier_distribution.get(r.peak_tier, 0) + 1
        )

        # Count tactics across segments
        for seg in r.segment_results:
            for tactic in seg.detected_tactics:
                metrics.tactic_detection_counts[tactic] = (
                    metrics.tactic_detection_counts.get(tactic, 0) + 1
                )
                metrics.total_tactic_detections += 1

            if seg.alert_executed:
                metrics.total_alerts_executed += 1
            metrics.caregiver_alert_count += seg.caregiver_notification_count
            if seg.user_warning_status in ["QUEUED", "DELIVERED", "FAILED"]:
                metrics.user_warning_count += 1
            if seg.intervention_status in ["REQUESTED", "EXECUTING", "EXECUTED", "FAILED"]:
                metrics.intervention_count += 1

        # First trigger segment indices
        if r.first_detection_segment is not None:
            detection_segments.append(r.first_detection_segment)
        if r.warning_segment is not None:
            warning_segments.append(r.warning_segment)
        if r.intervention_segment is not None:
            intervention_segments.append(r.intervention_segment)

        # Check for first critical segment in this scenario
        for seg in r.segment_results:
            if seg.risk_tier == "CRITICAL":
                critical_segments.append(seg.segment_index)
                break

        # Ground-truth comparison where annotations exist
        if r.expected_tactics:
            for exp in r.expected_tactics:
                total_expected_annotations += 1
                if exp in r.detected_tactics:
                    total_expected_matches += 1

        # False-positive analysis:
        # Benign scenarios reaching MEDIUM, HIGH, or CRITICAL, or triggering alerts
        # Legitimate urgency scenarios reaching HIGH or CRITICAL (since isolated urgency caps at LOW/22.0)
        if r.category == "benign":
            metrics.benign_or_legitimate_count += 1
            if r.peak_tier in ["MEDIUM", "HIGH", "CRITICAL"] or any(
                s.alert_executed for s in r.segment_results
            ):
                metrics.benign_false_positive_count += 1
                metrics.false_positive_count += 1

        elif r.category == "legitimate_urgency":
            metrics.benign_or_legitimate_count += 1
            if r.peak_tier in ["HIGH", "CRITICAL"] or any(
                s.alert_executed for s in r.segment_results
            ):
                metrics.legitimate_urgency_escalation_count += 1
                metrics.false_positive_count += 1

        # Downstream failure containment check
        if r.category == "downstream_failure":
            metrics.downstream_failure_scenario_count += 1
            if r.failure_isolation_intact:
                metrics.downstream_failure_isolated_count += 1

    # Rates and averages
    if total_expected_annotations > 0:
        metrics.expected_tactic_annotations_count = total_expected_annotations
        metrics.expected_tactics_matched_count = total_expected_matches
        metrics.expected_tactic_detection_rate = round(
            total_expected_matches / total_expected_annotations, 4
        )

    if metrics.benign_or_legitimate_count > 0:
        metrics.false_positive_rate = round(
            metrics.false_positive_count / metrics.benign_or_legitimate_count, 4
        )

    if detection_segments:
        metrics.first_detection_segment_mean = round(
            sum(detection_segments) / len(detection_segments), 2
        )
    if warning_segments:
        metrics.first_warning_segment_mean = round(
            sum(warning_segments) / len(warning_segments), 2
        )
    if critical_segments:
        metrics.first_critical_segment_mean = round(
            sum(critical_segments) / len(critical_segments), 2
        )
    if intervention_segments:
        metrics.intervention_segment_mean = round(
            sum(intervention_segments) / len(intervention_segments), 2
        )

    if metrics.downstream_failure_scenario_count > 0:
        metrics.downstream_failure_isolation_rate = round(
            metrics.downstream_failure_isolated_count
            / metrics.downstream_failure_scenario_count,
            4,
        )

    return metrics
