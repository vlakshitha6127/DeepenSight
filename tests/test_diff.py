"""Tests for the Assessment Diff engine comparing baseline and improved architectures."""

import pytest
from depsight.validators.schema import load_model_from_file
from depsight.engine.diff import AssessmentDiffEngine


def test_assessment_diff_baseline_vs_improved():
    """Requirement: Diff correctly identifies fixed cut sets, resolved dependencies, and improved scenarios."""
    before_model = load_model_from_file("examples/fictional_payment_service/architecture_baseline.yaml")
    after_model = load_model_from_file("examples/fictional_payment_service/architecture_improved.yaml")

    diff_engine = AssessmentDiffEngine(before_model, after_model)
    res = diff_engine.compute_diff(max_cutset_size=2)

    assert res.before_snapshot_version == "1.0.0"
    assert res.after_snapshot_version == "1.1.0"

    # 1. Verify shared-iam-directory was resolved as a shared dependency
    assert "shared-iam-directory" in res.resolved_dependencies

    # 2. Verify shared-iam-directory was eliminated from minimal cut sets
    fixed_comps = [cs.components for cs in res.fixed_cut_sets]
    assert ["shared-iam-directory"] in fixed_comps

    # 3. Verify scenario outcome changed for Identity failure
    iam_change = [c for c in res.scenario_outcome_changes if c["scenario_id"] == "SCN-04-IDENTITY-ACCESS-FAILURE"]
    assert len(iam_change) == 1
    assert iam_change[0]["before"]["both_unavailable"] is True
    assert iam_change[0]["after"]["both_unavailable"] is False
    assert iam_change[0]["after"]["backup"] == "AVAILABLE"
