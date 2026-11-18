"""Evidence coverage calculation.

Calculates evidence quality metrics per arrangement and overall:
- Percentage confirmed
- Percentage inferred or unverified
- Percentage past staleness threshold
- Count of UNKNOWN dependency rules
Strictly represents evidence quality, NOT a universal resilience score.
"""

from __future__ import annotations
from typing import Optional, List
from depsight.engine.models import (
    ArchitectureModel,
    EvidenceCoverage,
    EvidenceStatus,
    DependencyRule,
    Dependency,
)
from depsight.engine.graph import DependencyGraph
from depsight.engine.evidence import EvidenceInspector


class EvidenceCoverageCalculator:
    """Calculates deterministic evidence coverage metrics without synthesizing resilience scores."""

    def __init__(self, model: ArchitectureModel, graph: Optional[DependencyGraph] = None):
        self.model = model
        self.graph = graph or DependencyGraph(model)
        self.inspector = EvidenceInspector(model, self.graph)

    def calculate_coverage(
        self,
        scope_name: str = "Overall",
        dependencies: Optional[List[Dependency]] = None,
        cutoff_date_str: Optional[str] = None,
        staleness_threshold_days: int = 180,
    ) -> EvidenceCoverage:
        """Calculate evidence coverage breakdown for a given set of dependencies."""
        deps = dependencies if dependencies is not None else self.model.dependencies
        total = len(deps)

        if total == 0:
            return EvidenceCoverage(
                scope_name=scope_name,
                total_relationships=0,
                confirmed_count=0,
                confirmed_percentage=0.0,
                inferred_or_unverified_count=0,
                inferred_or_unverified_percentage=0.0,
                stale_count=0,
                stale_percentage=0.0,
                disputed_count=0,
                unknown_rule_count=0,
                staleness_threshold_days=staleness_threshold_days,
            )

        confirmed_count = 0
        inferred_or_unverified_count = 0
        stale_count = 0
        disputed_count = 0
        unknown_rule_count = 0

        for dep in deps:
            st = dep.evidence.status
            if st == EvidenceStatus.CONFIRMED:
                confirmed_count += 1
            elif st in (EvidenceStatus.INFERRED, EvidenceStatus.UNVERIFIED):
                inferred_or_unverified_count += 1
            elif st == EvidenceStatus.DISPUTED:
                disputed_count += 1

            if dep.rule == DependencyRule.UNKNOWN:
                unknown_rule_count += 1

            is_stale, _ = self.inspector.is_stale(dep.evidence, cutoff_date_str, staleness_threshold_days)
            if is_stale:
                stale_count += 1

        confirmed_pct = round((confirmed_count / total) * 100.0, 2)
        inferred_unverified_pct = round((inferred_or_unverified_count / total) * 100.0, 2)
        stale_pct = round((stale_count / total) * 100.0, 2)

        return EvidenceCoverage(
            scope_name=scope_name,
            total_relationships=total,
            confirmed_count=confirmed_count,
            confirmed_percentage=confirmed_pct,
            inferred_or_unverified_count=inferred_or_unverified_count,
            inferred_or_unverified_percentage=inferred_unverified_pct,
            stale_count=stale_count,
            stale_percentage=stale_pct,
            disputed_count=disputed_count,
            unknown_rule_count=unknown_rule_count,
            staleness_threshold_days=staleness_threshold_days,
        )

    def calculate_primary_coverage(self, cutoff_date_str: Optional[str] = None) -> EvidenceCoverage:
        """Calculate coverage specifically for dependencies in primary arrangement's upstream subgraph."""
        primary_root = self.model.service.primary_arrangement.root_component_id
        deps = self.graph.get_upstream_dependencies(primary_root)
        return self.calculate_coverage(
            scope_name="Primary Arrangement",
            dependencies=deps,
            cutoff_date_str=cutoff_date_str,
        )

    def calculate_backup_coverage(self, cutoff_date_str: Optional[str] = None) -> EvidenceCoverage:
        """Calculate coverage specifically for dependencies in backup arrangement's upstream subgraph."""
        backup_root = self.model.service.backup_arrangement.root_component_id
        deps = self.graph.get_upstream_dependencies(backup_root)
        return self.calculate_coverage(
            scope_name="Backup Arrangement",
            dependencies=deps,
            cutoff_date_str=cutoff_date_str,
        )
