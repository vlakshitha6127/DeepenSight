"""Tests for dependency rules (ALL, ANY, OPTIONAL, UNKNOWN) and three-valued logic."""

import pytest
from depsight.engine.models import (
    ArchitectureModel,
    Component,
    Dependency,
    DependencyGroup,
    DependencyRule,
    Evidence,
    EvidenceStatus,
    Service,
    ServiceArrangement,
    ModelMetadata,
    Scenario,
    ComponentState,
    ServiceOutcome,
)
from depsight.engine.graph import DependencyGraph
from depsight.engine.propagation import PropagationEngine


def create_minimal_model(
    rule: DependencyRule = DependencyRule.ALL,
    include_optional: bool = False,
    is_group: bool = False,
) -> ArchitectureModel:
    """Helper to create minimal two-component or multi-alternative model."""
    components = [
        Component(id="svc-root", name="Root Service", type="service"),
        Component(id="comp-a", name="Component A", type="backend"),
    ]
    groups = []
    dependencies = []

    if is_group:
        components.append(Component(id="comp-b", name="Component B", type="backend"))
        groups.append(
            DependencyGroup(
                id="group-1",
                dependent_component_id="svc-root",
                name="Group 1",
                rule=rule,
                member_target_ids=["comp-a", "comp-b"],
            )
        )
        dependencies.append(
            Dependency(
                id="dep-a",
                source_component_id="svc-root",
                target_component_id="comp-a",
                group_id="group-1",
                rule=rule,
                evidence=Evidence(id="ev-1", status=EvidenceStatus.CONFIRMED, source="Unit Test"),
            )
        )
        dependencies.append(
            Dependency(
                id="dep-b",
                source_component_id="svc-root",
                target_component_id="comp-b",
                group_id="group-1",
                rule=rule,
                evidence=Evidence(id="ev-2", status=EvidenceStatus.CONFIRMED, source="Unit Test"),
            )
        )
    else:
        dependencies.append(
            Dependency(
                id="dep-a",
                source_component_id="svc-root",
                target_component_id="comp-a",
                rule=rule,
                evidence=Evidence(id="ev-1", status=EvidenceStatus.CONFIRMED, source="Unit Test"),
            )
        )

    if include_optional:
        components.append(Component(id="comp-opt", name="Optional Cache", type="cache"))
        dependencies.append(
            Dependency(
                id="dep-opt",
                source_component_id="svc-root",
                target_component_id="comp-opt",
                rule=DependencyRule.OPTIONAL,
                evidence=Evidence(id="ev-opt", status=EvidenceStatus.CONFIRMED, source="Unit Test"),
            )
        )

    return ArchitectureModel(
        metadata=ModelMetadata(name="Test Model", created_at="2026-11-18"),
        service=Service(
            id="test-svc",
            name="Test Service",
            primary_arrangement=ServiceArrangement(name="primary", root_component_id="svc-root"),
            backup_arrangement=ServiceArrangement(name="backup", root_component_id="svc-root"),
        ),
        components=components,
        dependency_groups=groups,
        dependencies=dependencies,
    )


def test_rule_all_mandatory_failure():
    """Requirement: Under ALL, if any required member is DOWN, parent is UNAVAILABLE."""
    model = create_minimal_model(rule=DependencyRule.ALL)
    engine = PropagationEngine(model)

    scenario = Scenario(
        id="scn-all-down",
        name="ALL Dep Down",
        description="Testing ALL failure",
        failed_component_ids=["comp-a"],
    )
    result = engine.evaluate_scenario(scenario)

    assert result.primary_result.outcome == ServiceOutcome.UNAVAILABLE
    assert result.component_states["comp-a"] == ComponentState.DOWN
    assert result.component_states["svc-root"] == ComponentState.DOWN
    assert result.primary_result.causal_path == ["svc-root", "comp-a"]


def test_rule_any_alternative_survival():
    """Requirement: Under ANY, if at least one alternative is UP, parent remains AVAILABLE."""
    model = create_minimal_model(rule=DependencyRule.ANY, is_group=True)
    engine = PropagationEngine(model)

    # Fail only comp-a, comp-b remains UP
    scenario = Scenario(
        id="scn-any-one-down",
        name="One ANY Dep Down",
        description="Testing ANY resilience",
        failed_component_ids=["comp-a"],
    )
    result = engine.evaluate_scenario(scenario)

    assert result.primary_result.outcome == ServiceOutcome.AVAILABLE
    assert result.component_states["comp-a"] == ComponentState.DOWN
    assert result.component_states["comp-b"] == ComponentState.UP
    assert result.component_states["svc-root"] == ComponentState.UP


def test_rule_any_all_alternatives_failed():
    """Requirement: Under ANY, if ALL alternatives are DOWN, parent is UNAVAILABLE."""
    model = create_minimal_model(rule=DependencyRule.ANY, is_group=True)
    engine = PropagationEngine(model)

    scenario = Scenario(
        id="scn-any-both-down",
        name="Both ANY Deps Down",
        description="Testing complete ANY failure",
        failed_component_ids=["comp-a", "comp-b"],
    )
    result = engine.evaluate_scenario(scenario)

    assert result.primary_result.outcome == ServiceOutcome.UNAVAILABLE
    assert result.component_states["svc-root"] == ComponentState.DOWN


def test_rule_optional_component_failure():
    """Requirement: Under OPTIONAL, failure yields DEGRADED, not UNAVAILABLE."""
    model = create_minimal_model(rule=DependencyRule.ALL, include_optional=True)
    engine = PropagationEngine(model)

    scenario = Scenario(
        id="scn-opt-down",
        name="Optional Cache Down",
        description="Testing OPTIONAL degradation",
        failed_component_ids=["comp-opt"],
    )
    result = engine.evaluate_scenario(scenario)

    assert result.primary_result.outcome == ServiceOutcome.DEGRADED
    assert result.component_states["comp-opt"] == ComponentState.DOWN
    assert result.component_states["comp-a"] == ComponentState.UP
    assert result.component_states["svc-root"] == ComponentState.UP
    assert "comp-opt" in result.primary_result.causal_path


def test_unknown_dependency_evaluates_to_indeterminate():
    """Requirement: Undocumented or UNKNOWN dependency must evaluate to INDETERMINATE."""
    model = create_minimal_model(rule=DependencyRule.UNKNOWN)
    engine = PropagationEngine(model)

    scenario = Scenario(
        id="scn-unknown",
        name="Unknown Dep Scenario",
        description="Testing UNKNOWN rule handling",
        failed_component_ids=[],
    )
    result = engine.evaluate_scenario(scenario)

    assert result.primary_result.outcome == ServiceOutcome.INDETERMINATE
    assert result.component_states["svc-root"] == ComponentState.UNKNOWN


def test_failed_mandatory_with_unknown_still_unavailable():
    """Requirement: A failed mandatory dependency establishes UNAVAILABLE even if other deps are UNKNOWN."""
    # Model with one failed mandatory ALL and one UNKNOWN
    components = [
        Component(id="root", name="Root", type="service"),
        Component(id="mandatory-failed", name="Failed Dep", type="database"),
        Component(id="unknown-dep", name="Unknown Dep", type="service"),
    ]
    dependencies = [
        Dependency(
            id="dep-1",
            source_component_id="root",
            target_component_id="mandatory-failed",
            rule=DependencyRule.ALL,
            evidence=Evidence(id="e1", status=EvidenceStatus.CONFIRMED, source="test"),
        ),
        Dependency(
            id="dep-2",
            source_component_id="root",
            target_component_id="unknown-dep",
            rule=DependencyRule.UNKNOWN,
            evidence=Evidence(id="e2", status=EvidenceStatus.UNVERIFIED, source="test"),
        ),
    ]
    model = ArchitectureModel(
        metadata=ModelMetadata(name="Mandatory Overrides Unknown", created_at="2026-11-18"),
        service=Service(
            id="svc",
            name="Svc",
            primary_arrangement=ServiceArrangement(name="primary", root_component_id="root"),
            backup_arrangement=ServiceArrangement(name="backup", root_component_id="root"),
        ),
        components=components,
        dependencies=dependencies,
    )
    engine = PropagationEngine(model)
    scenario = Scenario(
        id="scn-mixed",
        name="Mixed Mandatory and Unknown",
        description="Test mandatory failure precedence",
        failed_component_ids=["mandatory-failed"],
    )
    result = engine.evaluate_scenario(scenario)

    assert result.primary_result.outcome == ServiceOutcome.UNAVAILABLE
    assert result.component_states["root"] == ComponentState.DOWN
