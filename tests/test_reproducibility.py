"""Tests for byte-identical reproducibility and deterministic report regeneration."""

import pytest
from depsight.validators.schema import load_model_from_file
from depsight.engine.evaluator import IndependenceEvaluator
from depsight.engine.reproducibility import (
    serialize_canonical_json,
    compute_sha256,
    verify_reproducibility,
)


def test_byte_identical_reproducibility_with_fixed_timestamp():
    """Requirement: Identical inputs with explicit fixed input timestamp produce byte-identical serialized outputs."""
    model_a = load_model_from_file("examples/fictional_payment_service/architecture_baseline.yaml")
    model_b = load_model_from_file("examples/fictional_payment_service/architecture_baseline.yaml")

    evaluator_a = IndependenceEvaluator(model_a)
    evaluator_b = IndependenceEvaluator(model_b)

    report_a = evaluator_a.run_assessment(fixed_timestamp="2026-11-18T12:00:00Z")
    report_b = evaluator_b.run_assessment(fixed_timestamp="2026-11-18T12:00:00Z")

    assert verify_reproducibility(report_a, report_b, ignore_timestamps=False)

    json_a = serialize_canonical_json(report_a)
    json_b = serialize_canonical_json(report_b)

    assert json_a == json_b
    assert compute_sha256(json_a) == compute_sha256(json_b)


def test_reproducibility_excluding_volatile_timestamps():
    """Requirement: Exclude variable timestamps from byte-reproducibility comparison."""
    model = load_model_from_file("examples/fictional_payment_service/architecture_baseline.yaml")
    evaluator = IndependenceEvaluator(model)

    report_1 = evaluator.run_assessment(fixed_timestamp="2026-11-18T10:00:00Z")
    report_2 = evaluator.run_assessment(fixed_timestamp="2026-11-18T18:30:00Z")

    # Timestamps differ
    assert report_1.generated_at != report_2.generated_at

    # But with volatile timestamp excluded/normalized, representation and analytical results are byte-identical
    assert verify_reproducibility(report_1, report_2, ignore_timestamps=True)


def test_historical_report_regeneration():
    """Requirement: Historical reports regenerate consistently from stored snapshots."""
    model = load_model_from_file("examples/fictional_payment_service/architecture_baseline.yaml")
    evaluator = IndependenceEvaluator(model)

    run_1 = evaluator.run_assessment(fixed_timestamp="2026-11-18T10:00:00Z")
    run_2 = evaluator.run_assessment(fixed_timestamp="2026-11-18T10:00:00Z")

    assert run_1.report_id == run_2.report_id
    assert len(run_1.common_cause_cut_sets) == len(run_2.common_cause_cut_sets)
    assert len(run_1.scenario_outcomes) == len(run_2.scenario_outcomes)
    assert compute_sha256(serialize_canonical_json(run_1)) == compute_sha256(serialize_canonical_json(run_2))
