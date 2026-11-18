"""Tests for the 7 standard outage scenarios and reference architecture simulations."""

import pytest
from depsight.validators.schema import load_model_from_file
from depsight.engine.scenarios import ScenarioEngine
from depsight.engine.models import ServiceOutcome


@pytest.fixture
def baseline_model():
    return load_model_from_file("examples/fictional_payment_service/architecture_baseline.yaml")


def test_standard_7_scenarios_execute(baseline_model):
    """Requirement: All seven standard scenarios must execute deterministically."""
    scenario_engine = ScenarioEngine(baseline_model)
    scenarios = scenario_engine.get_standard_scenarios()
    assert len(scenarios) == 7

    results = scenario_engine.evaluate_all(scenarios)
    assert len(results) == 7

    result_map = {r.scenario_id: r for r in results}

    # 1. Single component failure (primary DB): Primary UNAVAILABLE, Backup AVAILABLE (survives!)
    r1 = result_map["SCN-01-SINGLE-COMPONENT"]
    assert r1.primary_result.outcome == ServiceOutcome.UNAVAILABLE
    assert r1.backup_result.outcome == ServiceOutcome.AVAILABLE
    assert not r1.both_unavailable

    # 2. Regional outage (AWS Ireland): Primary UNAVAILABLE, Azure Backup AVAILABLE
    r2 = result_map["SCN-02-REGIONAL-OUTAGE"]
    assert r2.primary_result.outcome == ServiceOutcome.UNAVAILABLE
    assert r2.backup_result.outcome == ServiceOutcome.AVAILABLE
    assert not r2.both_unavailable

    # 4. Identity or access failure (Okta shared tenant): BOTH UNAVAILABLE (common-mode failure demonstrated!)
    r4 = result_map["SCN-04-IDENTITY-ACCESS-FAILURE"]
    assert r4.primary_result.outcome == ServiceOutcome.UNAVAILABLE
    assert r4.backup_result.outcome == ServiceOutcome.UNAVAILABLE
    assert r4.both_unavailable
    assert "shared-iam-directory" in r4.primary_result.causal_path
    assert "shared-iam-directory" in r4.backup_result.causal_path

    # 5. DNS loss: BOTH UNAVAILABLE
    r5 = result_map["SCN-05-DNS-CONNECTIVITY-LOSS"]
    assert r5.both_unavailable

    # 6. Degradation (optional cache failure): Both DEGRADED or Primary DEGRADED, not UNAVAILABLE
    r6 = result_map["SCN-06-DUAL-DEGRADATION"]
    assert r6.primary_result.outcome in (ServiceOutcome.DEGRADED, ServiceOutcome.AVAILABLE)
    assert not r6.both_unavailable
