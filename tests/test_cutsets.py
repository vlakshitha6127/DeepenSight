"""Tests for minimal common-cause cut sets and brute-force equivalence."""

import pytest
import itertools
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
    ServiceOutcome,
    CutSetClassification,
)
from depsight.engine.cutsets import CutSetAnalyzer
from depsight.engine.propagation import PropagationEngine
from depsight.validators.schema import load_model_from_file


def test_minimal_cutsets_against_brute_force():
    """
    Requirement 11 & 13: Verify cut-set correctness against brute-force enumeration on small graphs.
    Small graph:
    Primary: P -> X, P -> Y
    Backup: B -> Y, B -> Z
    Here:
    - {Y} alone makes both P and B fail (cut set of size 1).
    - {X, Z} makes P fail (via X) and B fail (via Z) (cut set of size 2).
    - {X, Y} is a cut set of size 2, BUT NOT MINIMAL because {Y} is already a cut set!
    """
    components = [
        Component(id="P", name="Primary Root", type="service"),
        Component(id="B", name="Backup Root", type="service"),
        Component(id="X", name="Component X", type="db"),
        Component(id="Y", name="Shared Y", type="iam"),
        Component(id="Z", name="Component Z", type="db"),
    ]
    dependencies = [
        Dependency(id="d-px", source_component_id="P", target_component_id="X", rule=DependencyRule.ALL,
                   evidence=Evidence(id="e1", status=EvidenceStatus.CONFIRMED, source="test")),
        Dependency(id="d-py", source_component_id="P", target_component_id="Y", rule=DependencyRule.ALL,
                   evidence=Evidence(id="e2", status=EvidenceStatus.CONFIRMED, source="test")),
        Dependency(id="d-by", source_component_id="B", target_component_id="Y", rule=DependencyRule.ALL,
                   evidence=Evidence(id="e3", status=EvidenceStatus.CONFIRMED, source="test")),
        Dependency(id="d-bz", source_component_id="B", target_component_id="Z", rule=DependencyRule.ALL,
                   evidence=Evidence(id="e4", status=EvidenceStatus.CONFIRMED, source="test")),
    ]
    model = ArchitectureModel(
        metadata=ModelMetadata(name="Brute Force Reference", created_at="2026-11-18"),
        service=Service(
            id="cutset-svc",
            name="Cut Set Service",
            primary_arrangement=ServiceArrangement(name="primary", root_component_id="P"),
            backup_arrangement=ServiceArrangement(name="backup", root_component_id="B"),
        ),
        components=components,
        dependencies=dependencies,
    )

    # Brute-force ground truth enumeration
    engine = PropagationEngine(model)
    all_nodes = ["P", "B", "X", "Y", "Z"]
    brute_force_cutsets = []

    # Size 1
    for c in all_nodes:
        res = engine.evaluate_scenario(Scenario(id=f"bf-{c}", name=c, description="bf", failed_component_ids=[c]))
        if res.primary_result.outcome == ServiceOutcome.UNAVAILABLE and res.backup_result.outcome == ServiceOutcome.UNAVAILABLE:
            brute_force_cutsets.append({c})

    # Size 2 minimal
    for pair in itertools.combinations(all_nodes, 2):
        s = set(pair)
        if any(single.issubset(s) for single in brute_force_cutsets):
            continue  # not minimal
        res = engine.evaluate_scenario(Scenario(id=f"bf-{pair}", name=str(pair), description="bf", failed_component_ids=list(pair)))
        if res.primary_result.outcome == ServiceOutcome.UNAVAILABLE and res.backup_result.outcome == ServiceOutcome.UNAVAILABLE:
            brute_force_cutsets.append(s)

    # Now run CutSetAnalyzer
    analyzer = CutSetAnalyzer(model)
    computed_cutsets = analyzer.compute_minimal_cut_sets(max_size=2)
    computed_as_sets = [set(cs.components) for cs in computed_cutsets]

    # Verify exact match between engine and brute-force
    assert len(computed_as_sets) == len(brute_force_cutsets)
    for bf in brute_force_cutsets:
        assert bf in computed_as_sets

    # Expected: {Y} of size 1, and {X, Z} of size 2
    assert {"Y"} in computed_as_sets
    assert {"X", "Z"} in computed_as_sets


def test_cutset_confirmed_vs_possible_classification():
    """Verify that an unverified link produces a POSSIBLE cut set, while verified produces CONFIRMED."""
    model = load_model_from_file("examples/fictional_payment_service/architecture_baseline.yaml")
    analyzer = CutSetAnalyzer(model)
    cutsets = analyzer.compute_minimal_cut_sets(max_size=2)

    # Look for shared-edge-dns (CONFIRMED) and shared-iam-directory (POSSIBLE due to unverified backup dep)
    dns_cs = [cs for cs in cutsets if cs.components == ["shared-edge-dns"]][0]
    iam_cs = [cs for cs in cutsets if cs.components == ["shared-iam-directory"]][0]

    assert dns_cs.classification == CutSetClassification.CONFIRMED
    assert iam_cs.classification == CutSetClassification.POSSIBLE
    assert len(iam_cs.evidence_limitations) > 0
    assert any("UNVERIFIED" in lim for lim in iam_cs.evidence_limitations)
