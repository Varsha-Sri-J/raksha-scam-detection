"""Tests for the RAKSHA offline evaluation scenario dataset and runner (Phase 8B).

Validates:
1. Scenario model validation
2. Scenario isolation (no cross-scenario leakage)
3. Single-segment runner execution
4. Multi-segment runner execution
5. Tactic capture and confidence tracking
6. Risk progression capture
7. Protection decision capture
8. Caregiver notification capture
9. Protected-user warning capture
10. Intervention capture
11. Downstream failure isolation (SMS, warning, intervention)
12. Metric calculation
13. Report generation (text and JSON)
14. Deterministic repeated execution
15. Strict offline execution (zero network calls)
"""

import json
import pytest
from typing import List

from backend.app.models import ManipulationCategory, SpeakerType
from backend.app.services.intervention_service import MockInterventionProvider
from backend.app.services.notification_service import MockSMSProvider
from backend.app.services.user_warning_service import MockUserWarningProvider
from evaluation.metrics import calculate_metrics
from evaluation.models import (
    EvaluationScenario,
    EvaluationScenarioResult,
    EvaluationSegment,
    EvaluationSegmentResult,
)
from evaluation.report import generate_json_report, generate_text_report
from evaluation.runner import EvaluationRunner
from evaluation.scenarios import (
    ALL_EVALUATION_SCENARIOS,
    get_all_scenarios,
    get_scenarios_by_category,
)


# ==============================================================================
# 1. SCENARIO MODEL VALIDATION
# ==============================================================================

def test_scenario_model_validation():
    """Verify that models validate and initialize properly with correct defaults."""
    seg = EvaluationSegment(
        speaker=SpeakerType.CALLER,
        text="Sample test utterance",
        expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
        notes="Test note",
    )
    assert seg.speaker == SpeakerType.CALLER
    assert seg.text == "Sample test utterance"
    assert seg.expected_tactics == [ManipulationCategory.AUTHORITY_IMPERSONATION]

    scenario = EvaluationScenario(
        scenario_id="test_scenario_1",
        category="clear_scam",
        description="A test scam scenario",
        segments=[seg],
        expected_tactics=[ManipulationCategory.AUTHORITY_IMPERSONATION],
    )
    assert scenario.scenario_id == "test_scenario_1"
    assert scenario.category == "clear_scam"
    assert len(scenario.segments) == 1
    assert scenario.caregiver_should_fail is False

    dumped = scenario.model_dump()
    assert dumped["scenario_id"] == "test_scenario_1"
    assert dumped["segments"][0]["text"] == "Sample test utterance"


def test_scenario_dataset_inventory():
    """Verify benchmark dataset count and category distribution."""
    scenarios = get_all_scenarios()
    assert len(scenarios) == 30

    categories = [s.category for s in scenarios]
    assert categories.count("clear_scam") == 5
    assert categories.count("multi_tactic") == 4
    assert categories.count("novel_wording") == 5
    assert categories.count("legitimate_urgency") == 5
    assert categories.count("benign") == 5
    assert categories.count("progression") == 3
    assert categories.count("downstream_failure") == 3

    # Ensure all scenario IDs are unique
    ids = [s.scenario_id for s in scenarios]
    assert len(ids) == len(set(ids))

    # Verify get_scenarios_by_category
    benign = get_scenarios_by_category("benign")
    assert len(benign) == 5
    assert all(s.category == "benign" for s in benign)


# ==============================================================================
# 2. SCENARIO ISOLATION
# ==============================================================================

@pytest.mark.asyncio
async def test_scenario_isolation():
    """Verify that running a high-risk scenario does not contaminate a subsequent benign scenario."""
    runner = EvaluationRunner()

    scam_scenario = EvaluationScenario(
        scenario_id="isolate_scam",
        category="clear_scam",
        description="High risk scam",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is Officer Miller from the Federal Police Department. An arrest warrant has been issued in your name.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Withdraw all cash from your bank and deposit it into the federal escrow account immediately.",
            ),
        ],
    )

    benign_scenario = EvaluationScenario(
        scenario_id="isolate_benign",
        category="benign",
        description="Benign conversation",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Hi Grandma, how are you doing today? We are excited for dinner.",
            ),
        ],
    )

    res_scam = await runner.run_scenario(scam_scenario)
    assert res_scam.peak_tier in ["MEDIUM", "HIGH", "CRITICAL"]

    res_benign = await runner.run_scenario(benign_scenario)
    # Benign scenario must start clean and remain SAFE
    assert res_benign.peak_tier == "SAFE"
    assert res_benign.final_score < 25.0
    assert len(res_benign.detected_tactics) == 0


# ==============================================================================
# 3. SINGLE-SEGMENT RUNNER
# ==============================================================================

@pytest.mark.asyncio
async def test_single_segment_runner():
    """Verify execution of a single-segment scenario."""
    runner = EvaluationRunner()

    scenario = EvaluationScenario(
        scenario_id="single_seg_test",
        category="benign",
        description="Single benign turn",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Good morning, confirming your dental appointment for tomorrow at three.",
            )
        ],
    )

    result = await runner.run_scenario(scenario)
    assert result.scenario_id == "single_seg_test"
    assert len(result.segment_results) == 1
    assert result.segment_results[0].segment_index == 0
    assert result.segment_results[0].text == "Good morning, confirming your dental appointment for tomorrow at three."
    assert result.peak_tier == "SAFE"
    assert result.peak_score >= 0.0


# ==============================================================================
# 4. MULTI-SEGMENT RUNNER
# ==============================================================================

@pytest.mark.asyncio
async def test_multi_segment_runner():
    """Verify execution of a multi-segment progression scenario."""
    runner = EvaluationRunner()
    scenarios = get_scenarios_by_category("progression")
    assert len(scenarios) >= 1

    scenario = scenarios[0]
    result = await runner.run_scenario(scenario)

    assert len(result.segment_results) == len(scenario.segments)
    for idx, seg_res in enumerate(result.segment_results):
        assert seg_res.segment_index == idx
        assert seg_res.speaker in ["CALLER", "CALLEE"]
        assert isinstance(seg_res.risk_score, float)
        assert seg_res.risk_tier in ["SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


# ==============================================================================
# 5. TACTIC CAPTURE
# ==============================================================================

@pytest.mark.asyncio
async def test_tactic_capture():
    """Verify that detected tactics, confidences, and evidence are captured."""
    runner = EvaluationRunner()

    scenario = EvaluationScenario(
        scenario_id="tactic_capture_test",
        category="clear_scam",
        description="Testing tactic and evidence capture",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Read me the 6-digit one-time password OTP you just received on your phone right now.",
                expected_tactics=[ManipulationCategory.INFORMATION_PHISHING],
            )
        ],
    )

    result = await runner.run_scenario(scenario)
    assert len(result.detected_tactics) > 0
    assert "INFORMATION_PHISHING" in result.detected_tactics

    seg_0 = result.segment_results[0]
    assert "INFORMATION_PHISHING" in seg_0.detected_tactics
    assert "INFORMATION_PHISHING" in seg_0.confidence_values
    assert seg_0.confidence_values["INFORMATION_PHISHING"] >= 0.45
    assert len(seg_0.evidence) > 0


# ==============================================================================
# 6. RISK PROGRESSION CAPTURE
# ==============================================================================

@pytest.mark.asyncio
async def test_risk_progression_capture():
    """Verify peak score, peak tier, and first detection tracking."""
    runner = EvaluationRunner()

    scenario = EvaluationScenario(
        scenario_id="risk_prog_test",
        category="clear_scam",
        description="Progression of risk score",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Hello, hope you are having a nice day.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is Officer Miller from the Federal Police Department headquarters.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="You will be arrested and put in federal prison if you do not comply with our instructions.",
            ),
        ],
    )

    result = await runner.run_scenario(scenario)
    assert result.first_detection_segment is not None
    assert result.first_detection_segment >= 1
    assert result.peak_score >= result.segment_results[0].risk_score
    assert result.peak_tier in ["MEDIUM", "HIGH", "CRITICAL"]


# ==============================================================================
# 7. PROTECTION CAPTURE
# ==============================================================================

@pytest.mark.asyncio
async def test_protection_capture():
    """Verify that ProtectionEngine decisions and alert execution are captured."""
    runner = EvaluationRunner()

    scenario = EvaluationScenario(
        scenario_id="prot_capture_test",
        category="clear_scam",
        description="Testing protection capture",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="An arrest warrant has been issued in your name for criminal fraud, and deputies are being dispatched.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Withdraw all cash from your bank and deposit it into the federal escrow account immediately.",
            ),
        ],
    )

    result = await runner.run_scenario(scenario)
    levels = [s.protection_level for s in result.segment_results]
    assert any(lvl in ["WARNING", "CRITICAL_INTERCEPT"] for lvl in levels)
    assert any(s.alert_executed for s in result.segment_results)


# ==============================================================================
# 8. CAREGIVER CAPTURE
# ==============================================================================

@pytest.mark.asyncio
async def test_caregiver_capture():
    """Verify that caregiver notifications are recorded when high risk triggers an alert."""
    runner = EvaluationRunner()

    scenario = EvaluationScenario(
        scenario_id="cg_capture_test",
        category="clear_scam",
        description="Testing caregiver notification capture",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is Officer Miller from the Federal Police Department.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="An arrest warrant has been issued in your name for criminal fraud.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Within the next 15 minutes your account will be permanently blocked.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Deposit cash at the Bitcoin ATM terminal immediately to protect your remaining funds in federal escrow.",
            ),
        ],
    )

    result = await runner.run_scenario(scenario)
    cg_counts = [s.caregiver_notification_count for s in result.segment_results]
    assert sum(cg_counts) > 0


# ==============================================================================
# 9. WARNING CAPTURE
# ==============================================================================

@pytest.mark.asyncio
async def test_warning_capture():
    """Verify protected user warning dispatch is captured."""
    runner = EvaluationRunner()

    scenario = EvaluationScenario(
        scenario_id="warn_capture_test",
        category="clear_scam",
        description="Testing user warning capture",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is Officer Miller from the Federal Police Department.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="An arrest warrant has been issued in your name for criminal fraud.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Within the next 15 minutes your account will be permanently blocked.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Deposit cash at the Bitcoin ATM terminal immediately to protect your funds in federal escrow.",
            ),
        ],
    )

    result = await runner.run_scenario(scenario)
    warning_statuses = [
        s.user_warning_status for s in result.segment_results if s.user_warning_status
    ]
    assert len(warning_statuses) > 0
    assert any(st in ["DELIVERED", "QUEUED"] for st in warning_statuses)
    assert result.warning_segment is not None


# ==============================================================================
# 10. INTERVENTION CAPTURE
# ==============================================================================

@pytest.mark.asyncio
async def test_intervention_capture():
    """Verify call intervention disconnect dispatch is captured when acute tactic triggers."""
    runner = EvaluationRunner()

    scenario = EvaluationScenario(
        scenario_id="intervene_capture_test",
        category="clear_scam",
        description="Testing intervention disconnect capture",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Calling from the Central Bank fraud investigation team.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Police are already outside your house to take you into custody.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Read me the 6-digit one-time password OTP you just received immediately or go to jail.",
            ),
        ],
    )

    result = await runner.run_scenario(scenario)
    interventions = [
        s.intervention_status for s in result.segment_results if s.intervention_status
    ]
    assert len(interventions) > 0
    assert any(st in ["EXECUTED", "REQUESTED", "EXECUTING"] for st in interventions)
    assert result.intervention_segment is not None


# ==============================================================================
# 11. DOWNSTREAM FAILURE ISOLATION
# ==============================================================================

@pytest.mark.asyncio
async def test_downstream_failure_isolation():
    """Verify that caregiver, warning, or intervention failures do not break upstream pipeline."""
    runner = EvaluationRunner()

    # 1. Caregiver SMS failure
    sms_fail_scenario = EvaluationScenario(
        scenario_id="fail_sms",
        category="downstream_failure",
        description="Caregiver SMS failure",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is Officer Miller from the Federal Police Department.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Police are already outside your house to take you into custody.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Withdraw all cash from your bank and deposit it into the federal escrow account.",
            ),
        ],
        caregiver_should_fail=True,
    )
    res_sms = await runner.run_scenario(sms_fail_scenario)
    assert res_sms.failure_isolation_intact is True
    assert any(s.alert_executed for s in res_sms.segment_results)

    # 2. Voice warning failure
    warn_fail_scenario = EvaluationScenario(
        scenario_id="fail_warn",
        category="downstream_failure",
        description="Voice warning failure",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="This is customs and border protection narcotics division.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="An arrest warrant has been issued in your name for criminal fraud.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Within the next 15 minutes your account will be permanently blocked.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Purchase Apple or Target gift cards to verify and safeguard your funds.",
            ),
        ],
        warning_should_fail=True,
    )
    res_warn = await runner.run_scenario(warn_fail_scenario)
    assert res_warn.failure_isolation_intact is True
    assert any(s.protection_level in ["WARNING", "CRITICAL_INTERCEPT"] for s in res_warn.segment_results)
    # Check that warning status captured FAILED
    assert any(s.user_warning_status == "FAILED" for s in res_warn.segment_results)

    # 3. Intervention failure
    intervene_fail_scenario = EvaluationScenario(
        scenario_id="fail_intervene",
        category="downstream_failure",
        description="Intervention disconnect failure",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Calling from the Central Bank fraud investigation team.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Police are already outside your house to take you into custody.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Read me the 6-digit one-time password OTP you just received immediately.",
            ),
        ],
        intervention_should_fail=True,
    )
    res_intervene = await runner.run_scenario(intervene_fail_scenario)
    assert res_intervene.failure_isolation_intact is True
    assert res_intervene.peak_tier in ["HIGH", "CRITICAL"]


# ==============================================================================
# 12. METRIC CALCULATION
# ==============================================================================

def test_metric_calculation():
    """Verify metric calculations including false-positive rate and tier distribution."""
    mock_results = [
        EvaluationScenarioResult(
            scenario_id="scam_1",
            category="clear_scam",
            peak_score=85.0,
            peak_tier="HIGH",
            final_score=85.0,
            final_tier="HIGH",
            detected_tactics=["AUTHORITY_IMPERSONATION", "FEAR_INTIMIDATION"],
            expected_tactics=["AUTHORITY_IMPERSONATION", "FEAR_INTIMIDATION"],
            segment_results=[
                EvaluationSegmentResult(
                    segment_index=0,
                    text="Hello",
                    risk_score=40.0,
                    risk_tier="LOW",
                    alert_executed=False,
                ),
                EvaluationSegmentResult(
                    segment_index=1,
                    text="Scam",
                    risk_score=85.0,
                    risk_tier="HIGH",
                    alert_executed=True,
                    caregiver_notification_count=1,
                    user_warning_status="DELIVERED",
                    detected_tactics=["AUTHORITY_IMPERSONATION", "FEAR_INTIMIDATION"],
                ),
            ],
            first_detection_segment=1,
            warning_segment=1,
        ),
        EvaluationScenarioResult(
            scenario_id="benign_1",
            category="benign",
            peak_score=0.0,
            peak_tier="SAFE",
            final_score=0.0,
            final_tier="SAFE",
            detected_tactics=[],
            expected_tactics=[],
            segment_results=[
                EvaluationSegmentResult(
                    segment_index=0,
                    text="Nice weather today",
                    risk_score=0.0,
                    risk_tier="SAFE",
                    alert_executed=False,
                )
            ],
        ),
    ]

    metrics = calculate_metrics(mock_results)
    assert metrics.scenario_count == 2
    assert metrics.segment_count == 3
    assert metrics.category_counts["clear_scam"] == 1
    assert metrics.category_counts["benign"] == 1
    assert metrics.peak_tier_distribution["HIGH"] == 1
    assert metrics.peak_tier_distribution["SAFE"] == 1
    assert metrics.total_tactic_detections == 2
    assert metrics.expected_tactic_detection_rate == 1.0
    assert metrics.benign_false_positive_count == 0
    assert metrics.false_positive_rate == 0.0
    assert metrics.total_alerts_executed == 1
    assert metrics.caregiver_alert_count == 1
    assert metrics.user_warning_count == 1


# ==============================================================================
# 13. REPORT GENERATION
# ==============================================================================

def test_report_generation():
    """Verify that both plain text and JSON reports format cleanly and deterministically."""
    mock_results = [
        EvaluationScenarioResult(
            scenario_id="sample_scenario",
            category="clear_scam",
            description="A sample scam",
            peak_score=88.0,
            peak_tier="HIGH",
            final_score=88.0,
            final_tier="HIGH",
            detected_tactics=["AUTHORITY_IMPERSONATION"],
            expected_tactics=["AUTHORITY_IMPERSONATION"],
            segment_results=[
                EvaluationSegmentResult(
                    segment_index=0,
                    text="This is Officer Miller.",
                    risk_score=88.0,
                    risk_tier="HIGH",
                    protection_level="WARNING",
                    alert_executed=True,
                    caregiver_notification_count=1,
                    user_warning_status="DELIVERED",
                    detected_tactics=["AUTHORITY_IMPERSONATION"],
                )
            ],
            first_detection_segment=0,
            warning_segment=0,
        )
    ]

    text_rep = generate_text_report(mock_results)
    assert "RAKSHA OFFLINE EVALUATION BENCHMARK REPORT (PHASE 8B)" in text_rep
    assert "Total Scenarios Evaluated : 1" in text_rep
    assert "sample_scenario" in text_rep
    assert "AUTHORITY_IMPERSONATION" in text_rep

    json_rep = generate_json_report(mock_results)
    parsed = json.loads(json_rep)
    assert "benchmark_summary" in parsed
    assert "scenarios" in parsed
    assert parsed["benchmark_summary"]["scenario_count"] == 1
    assert parsed["scenarios"][0]["scenario_id"] == "sample_scenario"


# ==============================================================================
# 14. DETERMINISTIC REPEATED EXECUTION
# ==============================================================================

@pytest.mark.asyncio
async def test_deterministic_repeated_execution():
    """Verify that executing the same scenario multiple times yields identical results."""
    runner = EvaluationRunner()

    scenario = EvaluationScenario(
        scenario_id="repeat_test",
        category="clear_scam",
        description="Determinism test",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Calling from the Central Bank fraud investigation team.",
            ),
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Within the next 15 minutes your account will be permanently blocked.",
            ),
        ],
    )

    run_1 = await runner.run_scenario(scenario)
    run_2 = await runner.run_scenario(scenario)

    assert run_1.peak_score == run_2.peak_score
    assert run_1.peak_tier == run_2.peak_tier
    assert run_1.detected_tactics == run_2.detected_tactics
    assert len(run_1.segment_results) == len(run_2.segment_results)
    for s1, s2 in zip(run_1.segment_results, run_2.segment_results):
        assert s1.risk_score == s2.risk_score
        assert s1.risk_tier == s2.risk_tier
        assert s1.protection_level == s2.protection_level


# ==============================================================================
# 15. STRICT OFFLINE EXECUTION (NO NETWORK CALLS)
# ==============================================================================

@pytest.mark.asyncio
async def test_no_external_network_calls(monkeypatch):
    """Verify that evaluation runner executes completely offline with zero network attempts."""
    import socket

    def forbidden_connect(*args, **kwargs):
        raise RuntimeError("External network connection attempted during offline evaluation!")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)

    runner = EvaluationRunner()
    scenario = EvaluationScenario(
        scenario_id="offline_test",
        category="benign",
        description="Verify offline safety",
        segments=[
            EvaluationSegment(
                speaker=SpeakerType.CALLER,
                text="Hello, just calling to check on the delivery time for my order.",
            )
        ],
    )

    result = await runner.run_scenario(scenario)
    assert result.peak_tier == "SAFE"
