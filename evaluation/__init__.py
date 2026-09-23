"""RAKSHA Offline Evaluation Package (Phase 8B).

Provides dataset models, deterministic scenario definitions, an isolated execution runner,
quantitative metrics calculation, and structured report generators.
"""

from evaluation.metrics import EvaluationMetrics, calculate_metrics
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

__all__ = [
    "EvaluationSegment",
    "EvaluationScenario",
    "EvaluationSegmentResult",
    "EvaluationScenarioResult",
    "EvaluationMetrics",
    "calculate_metrics",
    "EvaluationRunner",
    "generate_text_report",
    "generate_json_report",
    "ALL_EVALUATION_SCENARIOS",
    "get_all_scenarios",
    "get_scenarios_by_category",
]
