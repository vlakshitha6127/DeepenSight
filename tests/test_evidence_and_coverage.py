"""Tests for evidence grading, staleness detection, and coverage metrics."""

import pytest
from datetime import date
from depsight.validators.schema import load_model_from_file
from depsight.engine.evidence import EvidenceInspector
from depsight.engine.coverage import EvidenceCoverageCalculator
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
)


def test_staleness_and_conflicting_evidence():
    """Requirement: Detect stale evidence and handle conflicting/disputed evidence."""
    components = [
        Component(id="root", name="Root", type="service"),
        Component(id="comp-a", name="A", type="db"),
        Component(id="comp-b", name="B", type="cache"),
    ]
    dependencies = [
        # Stale evidence: verified 300 days ago
        Dependency(
            id="dep-stale",
            source_component_id="root",
            target_component_id="comp-a",
            rule=DependencyRule.ALL,
            evidence=Evidence(
                id="ev-1",
                status=EvidenceStatus.CONFIRMED,
                source="Old Audit",
                verification_date="2025-01-01",
                validity_period_days=180,
            ),
        ),
        # Disputed evidence
        Dependency(
            id="dep-disputed",
            source_component_id="root",
            target_component_id="comp-b",
            rule=DependencyRule.ALL,
            evidence=Evidence(
                id="ev-2",
                status=EvidenceStatus.DISPUTED,
                source="Conflicting claims between team leads",
                verification_date="2026-10-01",
            ),
        ),
    ]
    model = ArchitectureModel(
        metadata=ModelMetadata(name="Evidence Test", created_at="2026-11-18"),
        service=Service(
            id="s1",
            name="S1",
            primary_arrangement=ServiceArrangement(name="primary", root_component_id="root"),
            backup_arrangement=ServiceArrangement(name="backup", root_component_id="root"),
        ),
        components=components,
        dependencies=dependencies,
    )

    inspector = EvidenceInspector(model)
    gaps = inspector.get_evidence_gaps(cutoff_date_str="2026-11-18")

    gap_types = [g["issue_type"] for g in gaps]
    assert "STALE" in gap_types
    assert "DISPUTED" in gap_types

    findings = inspector.generate_findings(cutoff_date_str="2026-11-18")
    assert any(f.evidence_status == EvidenceStatus.DISPUTED for f in findings)
    assert any("Stale verification" in f.title for f in findings)


def test_coverage_calculator_proportions():
    """Requirement: Accurate coverage percentages per arrangement without synthetic resilience score."""
    model = load_model_from_file("examples/fictional_payment_service/architecture_baseline.yaml")
    calculator = EvidenceCoverageCalculator(model)

    overall = calculator.calculate_coverage(cutoff_date_str="2026-11-18")
    primary = calculator.calculate_primary_coverage(cutoff_date_str="2026-11-18")
    backup = calculator.calculate_backup_coverage(cutoff_date_str="2026-11-18")

    assert overall.total_relationships == 14
    assert overall.confirmed_count > 0
    assert overall.inferred_or_unverified_count > 0
    assert overall.confirmed_percentage + overall.inferred_or_unverified_percentage <= 100.0

    # Ensure backup has unverified relationship ev-010
    assert backup.inferred_or_unverified_count >= 1
    # Check that coverage has no invented universal resilience score field
    assert not hasattr(overall, "resilience_score")
