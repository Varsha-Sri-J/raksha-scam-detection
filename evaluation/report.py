"""Report generation for the RAKSHA offline evaluation harness (Phase 8B).

Produces deterministic, human-readable text reports and structured JSON exports
detailing aggregate metrics and per-scenario progression.
"""

import json
from typing import List, Optional

from evaluation.metrics import EvaluationMetrics, calculate_metrics
from evaluation.models import EvaluationScenarioResult


def generate_json_report(
    results: List[EvaluationScenarioResult],
    metrics: Optional[EvaluationMetrics] = None,
    indent: int = 2,
) -> str:
    """Generate a clean, structured JSON report string."""
    calc_metrics = metrics or calculate_metrics(results)
    report_dict = {
        "benchmark_summary": calc_metrics.model_dump(),
        "scenarios": [r.model_dump() for r in results],
    }
    return json.dumps(report_dict, indent=indent, default=str)


def generate_text_report(
    results: List[EvaluationScenarioResult],
    metrics: Optional[EvaluationMetrics] = None,
) -> str:
    """Generate a readable, deterministic plain text evaluation report."""
    calc_metrics = metrics or calculate_metrics(results)
    lines: List[str] = []

    lines.append("=" * 78)
    lines.append("RAKSHA OFFLINE EVALUATION BENCHMARK REPORT (PHASE 8B)")
    lines.append("=" * 78)
    lines.append("")

    # 1. High-level Summary
    lines.append("1. AGGREGATE SUMMARY")
    lines.append("-" * 78)
    lines.append(f"Total Scenarios Evaluated : {calc_metrics.scenario_count}")
    lines.append(f"Total Dialogue Turns      : {calc_metrics.segment_count}")
    lines.append("")
    lines.append("Category Breakdown:")
    for cat, count in sorted(calc_metrics.category_counts.items()):
        lines.append(f"  - {cat:<24} : {count}")
    lines.append("")

    # 2. Peak Risk Tier Distribution
    lines.append("Peak Risk Tier Distribution:")
    for tier in ["SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        count = calc_metrics.peak_tier_distribution.get(tier, 0)
        pct = (
            f"{(count / calc_metrics.scenario_count * 100):.1f}%"
            if calc_metrics.scenario_count > 0
            else "0.0%"
        )
        lines.append(f"  - {tier:<10} : {count:>2} ({pct})")
    lines.append("")

    # 3. Tactic Detection Statistics
    lines.append("Observed Tactic Detection Counts:")
    lines.append(f"  Total Detections: {calc_metrics.total_tactic_detections}")
    for tactic, count in sorted(calc_metrics.tactic_detection_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  - {tactic:<28} : {count}")
    lines.append("")

    # 4. Ground-Truth Match Rate
    lines.append("Ground-Truth Tactic Matching (where annotated):")
    rate_str = (
        f"{calc_metrics.expected_tactic_detection_rate * 100:.1f}%"
        if calc_metrics.expected_tactic_detection_rate is not None
        else "N/A"
    )
    lines.append(
        f"  Matched {calc_metrics.expected_tactics_matched_count} of "
        f"{calc_metrics.expected_tactic_annotations_count} annotated tactics ({rate_str})"
    )
    lines.append("")

    # 5. False Positive & Safety Metrics
    lines.append("False-Positive / Escalation Analysis:")
    lines.append(f"  Benign & Legitimate Urgency Total : {calc_metrics.benign_or_legitimate_count}")
    lines.append(f"  Benign False Positives (MEDIUM+) : {calc_metrics.benign_false_positive_count}")
    lines.append(
        f"  Legitimate Urgency High Escalation: {calc_metrics.legitimate_urgency_escalation_count}"
    )
    lines.append(f"  Aggregate False-Positive Rate     : {calc_metrics.false_positive_rate * 100:.1f}%")
    lines.append("")

    # 6. Progression Timing (Averages)
    lines.append("Progression Timing (Mean Segment Index):")
    lines.append(f"  First Tactic Detection : {calc_metrics.first_detection_segment_mean}")
    lines.append(f"  First Warning / Advisory: {calc_metrics.first_warning_segment_mean}")
    lines.append(f"  First Critical Escalation: {calc_metrics.first_critical_segment_mean}")
    lines.append(f"  First Call Intervention : {calc_metrics.intervention_segment_mean}")
    lines.append("")

    # 7. Downstream Actions & Failure Containment
    lines.append("Downstream Protection Actions:")
    lines.append(f"  Dashboard Alerts Executed  : {calc_metrics.total_alerts_executed}")
    lines.append(f"  Caregiver SMS Dispatches   : {calc_metrics.caregiver_alert_count}")
    lines.append(f"  User Warnings Dispatched   : {calc_metrics.user_warning_count}")
    lines.append(f"  Interventions Dispatched   : {calc_metrics.intervention_count}")
    lines.append(
        f"  Failure Isolation Rate     : {calc_metrics.downstream_failure_isolation_rate * 100:.1f}% "
        f"({calc_metrics.downstream_failure_isolated_count}/{calc_metrics.downstream_failure_scenario_count})"
    )
    lines.append("")

    # 8. Per-Scenario Detailed Walkthrough
    lines.append("=" * 78)
    lines.append("2. PER-SCENARIO DETAILED RESULTS")
    lines.append("=" * 78)

    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i:02d}] Scenario: {r.scenario_id}")
        lines.append(f"     Category   : {r.category}")
        lines.append(f"     Description: {r.description}")
        lines.append(
            f"     Peak State : {r.peak_tier} (Score: {r.peak_score}) | Final State: {r.final_tier} ({r.final_score})"
        )
        exp_tactics_str = ", ".join(r.expected_tactics) if r.expected_tactics else "None"
        obs_tactics_str = ", ".join(r.detected_tactics) if r.detected_tactics else "None"
        lines.append(f"     Expected   : [{exp_tactics_str}]")
        lines.append(f"     Observed   : [{obs_tactics_str}]")

        risk_prog = " -> ".join(f"T{s.segment_index}:{s.risk_score}({s.risk_tier})" for s in r.segment_results)
        prot_prog = " -> ".join(f"T{s.segment_index}:{s.protection_level}" for s in r.segment_results)
        lines.append(f"     Risk Path  : {risk_prog}")
        lines.append(f"     Prot Path  : {prot_prog}")

        # Action notes
        alerts = [s.segment_index for s in r.segment_results if s.alert_executed]
        cg_alerts = sum(s.caregiver_notification_count for s in r.segment_results)
        warnings = [
            f"T{s.segment_index}:{s.user_warning_status}"
            for s in r.segment_results
            if s.user_warning_status
        ]
        interventions = [
            f"T{s.segment_index}:{s.intervention_status}"
            for s in r.segment_results
            if s.intervention_status
        ]

        actions_summary = []
        if alerts:
            actions_summary.append(f"Alerts at turns {alerts}")
        if cg_alerts:
            actions_summary.append(f"Caregiver SMS: {cg_alerts}")
        if warnings:
            actions_summary.append(f"Voice Warnings: [{', '.join(warnings)}]")
        if interventions:
            actions_summary.append(f"Interventions: [{', '.join(interventions)}]")

        if actions_summary:
            lines.append(f"     Actions    : {'; '.join(actions_summary)}")
        else:
            lines.append("     Actions    : None (Monitored)")

        if r.category == "downstream_failure":
            lines.append(f"     Isolation  : {'INTACT' if r.failure_isolation_intact else 'COMPROMISED'}")

    lines.append("\n" + "=" * 78)
    lines.append("END OF REPORT")
    lines.append("=" * 78)

    return "\n".join(lines)
