"""Minimal common-cause cut-set analysis.

Identifies the smallest component sets whose simultaneous failure causes both
primary and backup arrangements to become UNAVAILABLE.
Distinguishes CONFIRMED from POSSIBLE cut sets based on evidence verification.
"""

from __future__ import annotations
import itertools
from typing import List, Set, Dict, Tuple, Optional

from depsight.engine.models import (
    ArchitectureModel,
    CutSet,
    CutSetClassification,
    EvidenceStatus,
    DependencyRule,
    Scenario,
    ServiceOutcome,
)
from depsight.engine.graph import DependencyGraph
from depsight.engine.propagation import PropagationEngine


class CutSetAnalyzer:
    """Computes minimal common-cause cut sets for primary and backup arrangements."""

    def __init__(self, model: ArchitectureModel, graph: Optional[DependencyGraph] = None):
        self.model = model
        self.graph = graph or DependencyGraph(model)
        self.engine = PropagationEngine(model, self.graph)

    def compute_minimal_cut_sets(self, max_size: int = 2) -> List[CutSet]:
        """
        Compute minimal cut sets up to max_size (default 2).
        Enumerate size 1 first, prune supersets, then enumerate size 2, etc.
        """
        primary_root = self.model.service.primary_arrangement.root_component_id
        backup_root = self.model.service.backup_arrangement.root_component_id

        upstream_primary = self.graph.get_upstream_components(primary_root)
        upstream_backup = self.graph.get_upstream_components(backup_root)

        # Candidates must be in upstream of primary or backup
        all_candidates = sorted(list(upstream_primary.union(upstream_backup)))

        # Also identify shared failure domains
        shared_domains = self.graph.get_shared_failure_domains(primary_root, backup_root)

        minimal_cut_sets: List[CutSet] = []
        found_sets: List[Set[str]] = []

        for size in range(1, max_size + 1):
            for candidate_tuple in itertools.combinations(all_candidates, size):
                candidate_set = set(candidate_tuple)

                # Pruning: if candidate_set is a superset of an already found minimal cut set, skip!
                if any(found.issubset(candidate_set) for found in found_sets):
                    continue

                # Test failure of candidate_set
                test_scenario = Scenario(
                    id=f"cutset_test_{'_'.join(sorted(candidate_set))}",
                    name=f"Cut-set probe for {sorted(candidate_set)}",
                    description="Automated minimal cut-set detection probe",
                    failed_component_ids=sorted(list(candidate_set)),
                )

                result = self.engine.evaluate_scenario(test_scenario)

                if (
                    result.primary_result.outcome == ServiceOutcome.UNAVAILABLE
                    and result.backup_result.outcome == ServiceOutcome.UNAVAILABLE
                ):
                    # Minimal cut set found!
                    found_sets.append(candidate_set)

                    # Determine classification (CONFIRMED vs POSSIBLE) and supporting paths
                    classification, supporting_paths, limitations = self._grade_cut_set(
                        candidate_set, primary_root, backup_root
                    )

                    # Find shared failure domains for components in this cut set
                    comp_domains = set()
                    for cid in candidate_set:
                        comp = self.graph.get_component(cid)
                        if comp:
                            comp_domains.update(comp.failure_domains)

                    intersected_domains = sorted(list(comp_domains.intersection(set(shared_domains))))

                    cut_set = CutSet(
                        components=sorted(list(candidate_set)),
                        size=size,
                        classification=classification,
                        affected_arrangements=["primary", "backup"],
                        supporting_paths=supporting_paths,
                        evidence_limitations=limitations,
                        shared_failure_domains=intersected_domains,
                    )
                    minimal_cut_sets.append(cut_set)

        # Deterministic sorting: by size ascending, then classification (CONFIRMED before POSSIBLE), then component IDs
        minimal_cut_sets.sort(
            key=lambda cs: (
                cs.size,
                0 if cs.classification == CutSetClassification.CONFIRMED else 1,
                cs.components,
            )
        )
        return minimal_cut_sets

    def _grade_cut_set(
        self,
        cut_set_components: Set[str],
        primary_root: str,
        backup_root: str,
    ) -> Tuple[CutSetClassification, Dict[str, List[str]], List[str]]:
        """
        Grade cut set as CONFIRMED if all dependency edges on supporting paths are CONFIRMED.
        Otherwise grade as POSSIBLE and document evidence limitations.
        """
        supporting_paths: Dict[str, List[str]] = {}
        limitations: List[str] = []
        has_unconfirmed = False

        for arr_name, root_id in [("primary", primary_root), ("backup", backup_root)]:
            arr_paths = []
            for target in sorted(cut_set_components):
                paths = self.graph.find_all_paths_to_target(root_id, target)
                for p in paths:
                    arr_paths.append(" -> ".join(p))
                    # Check edges along path
                    for i in range(len(p) - 1):
                        u, v = p[i], p[i + 1]
                        dep = self.graph.dependencies_by_edge.get((u, v))
                        if dep:
                            if dep.evidence.status != EvidenceStatus.CONFIRMED:
                                has_unconfirmed = True
                                limitations.append(
                                    f"Relationship '{u} -> {v}' ({dep.id}) is {dep.evidence.status.value}: {dep.evidence.source}"
                                )
                            if dep.rule == DependencyRule.UNKNOWN:
                                has_unconfirmed = True
                                limitations.append(
                                    f"Relationship '{u} -> {v}' ({dep.id}) has UNKNOWN dependency rule"
                                )
            supporting_paths[arr_name] = sorted(list(set(arr_paths)))

        classification = (
            CutSetClassification.POSSIBLE if has_unconfirmed else CutSetClassification.CONFIRMED
        )
        return classification, supporting_paths, sorted(list(set(limitations)))
