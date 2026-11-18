"""Tests for cyclic dependency handling and monotone fixed-point iteration."""

import pytest
from depsight.engine.models import (
    ArchitectureModel,
    Component,
    Dependency,
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
from depsight.engine.propagation import PropagationEngine


def test_cyclic_dependencies_terminate_deterministically():
    """Requirement: Cyclic graphs must terminate deterministically with monotone updates."""
    # Graph: A -> B -> C -> A (a 3-cycle)
    components = [
        Component(id="comp-a", name="Node A", type="service"),
        Component(id="comp-b", name="Node B", type="service"),
        Component(id="comp-c", name="Node C", type="service"),
    ]
    dependencies = [
        Dependency(
            id="dep-ab",
            source_component_id="comp-a",
            target_component_id="comp-b",
            rule=DependencyRule.ALL,
            evidence=Evidence(id="e1", status=EvidenceStatus.CONFIRMED, source="test"),
        ),
        Dependency(
            id="dep-bc",
            source_component_id="comp-b",
            target_component_id="comp-c",
            rule=DependencyRule.ALL,
            evidence=Evidence(id="e2", status=EvidenceStatus.CONFIRMED, source="test"),
        ),
        Dependency(
            id="dep-ca",
            source_component_id="comp-c",
            target_component_id="comp-a",
            rule=DependencyRule.ALL,
            evidence=Evidence(id="e3", status=EvidenceStatus.CONFIRMED, source="test"),
        ),
    ]
    model = ArchitectureModel(
        metadata=ModelMetadata(name="Cyclic Test", created_at="2026-11-18"),
        service=Service(
            id="cyclic-svc",
            name="Cyclic Service",
            primary_arrangement=ServiceArrangement(name="primary", root_component_id="comp-a"),
            backup_arrangement=ServiceArrangement(name="backup", root_component_id="comp-b"),
        ),
        components=components,
        dependencies=dependencies,
    )

    engine = PropagationEngine(model)

    # Test 1: All nodes UP -> fixed point should reach all UP without infinite loop
    res_up = engine.evaluate_scenario(
        Scenario(id="scn-none-failed", name="No faults", description="All healthy", failed_component_ids=[])
    )
    assert res_up.primary_result.outcome == ServiceOutcome.AVAILABLE
    assert res_up.backup_result.outcome == ServiceOutcome.AVAILABLE
    assert res_up.component_states["comp-a"] == ComponentState.UP
    assert res_up.component_states["comp-b"] == ComponentState.UP
    assert res_up.component_states["comp-c"] == ComponentState.UP

    # Test 2: Node C fails -> failure propagates back C -> B -> A, cycle stabilizes at DOWN
    res_down = engine.evaluate_scenario(
        Scenario(id="scn-c-failed", name="C fails", description="C faulted", failed_component_ids=["comp-c"])
    )
    assert res_down.component_states["comp-c"] == ComponentState.DOWN
    assert res_down.component_states["comp-b"] == ComponentState.DOWN
    assert res_down.component_states["comp-a"] == ComponentState.DOWN
    assert res_down.primary_result.outcome == ServiceOutcome.UNAVAILABLE
    assert res_down.backup_result.outcome == ServiceOutcome.UNAVAILABLE
