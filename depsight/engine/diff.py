"""Assessment Diff Engine.

Compares two architecture snapshots under identical scenarios to determine:
- Fixed cut sets (resilience improvements)
- Newly introduced cut sets (regressions)
- Resolved shared dependencies
- Newly introduced shared dependencies
- Evidence status changes
- Scenario outcome improvements
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional

from depsight.engine.models import (
    ArchitectureModel,
    AssessmentDiffResult,
    DiffItem,
    CutSet,
    ScenarioResult,
    ServiceOutcome,
)
from depsight.engine.graph import DependencyGraph
from depsight.engine.cutsets import CutSetAnalyzer
from depsight.engine.scenarios import ScenarioEngine


class AssessmentDiffEngine:
    """Computes exact before/after diffs between two architecture snapshots."""

    def __init__(self, before_model: ArchitectureModel, after_model: ArchitectureModel):
        self.before_model = before_model
        self.after_model = after_model
        self.before_graph = DependencyGraph(before_model)
        self.after_graph = DependencyGraph(after_model)

    def compute_diff(self, max_cutset_size: int = 2) -> AssessmentDiffResult:
        """Run comprehensive comparative assessment between snapshots."""
        differences: List[DiffItem] = []

        # 1. Compare Shared Dependencies
        before_shared = set(
            self.before_graph.get_shared_components(
                self.before_model.service.primary_arrangement.root_component_id,
                self.before_model.service.backup_arrangement.root_component_id,
            )
        )
        after_shared = set(
            self.after_graph.get_shared_components(
                self.after_model.service.primary_arrangement.root_component_id,
                self.after_model.service.backup_arrangement.root_component_id,
            )
        )

        resolved_deps = sorted(list(before_shared - after_shared))
        new_shared_deps = sorted(list(after_shared - before_shared))

        for dep_id in resolved_deps:
            differences.append(
                DiffItem(
                    category="shared_dependency",
                    change_type="resolved",
                    identifier=dep_id,
                    before_state="SHARED",
                    after_state="ISOLATED",
                    description=f"Shared dependency on '{dep_id}' was eliminated in updated architecture.",
                )
            )

        for dep_id in new_shared_deps:
            differences.append(
                DiffItem(
                    category="shared_dependency",
                    change_type="newly_introduced",
                    identifier=dep_id,
                    before_state="ISOLATED",
                    after_state="SHARED",
                    description=f"New shared dependency on '{dep_id}' introduced between primary and backup.",
                )
            )

        # 2. Compare Minimal Cut Sets
        before_cutsets = CutSetAnalyzer(self.before_model, self.before_graph).compute_minimal_cut_sets(max_size=max_cutset_size)
        after_cutsets = CutSetAnalyzer(self.after_model, self.after_graph).compute_minimal_cut_sets(max_size=max_cutset_size)

        before_cs_map = {tuple(sorted(cs.components)): cs for cs in before_cutsets}
        after_cs_map = {tuple(sorted(cs.components)): cs for cs in after_cutsets}

        fixed_cut_sets: List[CutSet] = []
        for key, cs in before_cs_map.items():
            if key not in after_cs_map:
                fixed_cut_sets.append(cs)
                differences.append(
                    DiffItem(
                        category="cut_set",
                        change_type="fixed",
                        identifier="+".join(cs.components),
                        before_state=f"CUT-SET ({cs.classification.value})",
                        after_state="SURVIVED",
                        description=f"Cut set '{'+'.join(cs.components)}' (size {cs.size}) successfully eliminated; backup now survives this failure.",
                    )
                )

        new_cut_sets: List[CutSet] = []
        for key, cs in after_cs_map.items():
            if key not in before_cs_map:
                new_cut_sets.append(cs)
                differences.append(
                    DiffItem(
                        category="cut_set",
                        change_type="newly_introduced",
                        identifier="+".join(cs.components),
                        before_state="SURVIVED",
                        after_state=f"CUT-SET ({cs.classification.value})",
                        description=f"New cut set '{'+'.join(cs.components)}' (size {cs.size}) emerged in updated architecture.",
                    )
                )

        # 3. Compare Scenario Outcomes
        before_scenarios = ScenarioEngine(self.before_model, self.before_graph).get_standard_scenarios()
        before_engine = ScenarioEngine(self.before_model, self.before_graph)
        after_engine = ScenarioEngine(self.after_model, self.after_graph)

        scenario_outcome_changes = []
        for scn in before_scenarios:
            b_res = before_engine.engine.evaluate_scenario(scn)
            a_res = after_engine.engine.evaluate_scenario(scn)

            changed = (
                b_res.primary_result.outcome != a_res.primary_result.outcome
                or b_res.backup_result.outcome != a_res.backup_result.outcome
                or b_res.both_unavailable != a_res.both_unavailable
            )

            if changed:
                change_record = {
                    "scenario_id": scn.id,
                    "scenario_name": scn.name,
                    "before": {
                        "primary": b_res.primary_result.outcome.value,
                        "backup": b_res.backup_result.outcome.value,
                        "both_unavailable": b_res.both_unavailable,
                    },
                    "after": {
                        "primary": a_res.primary_result.outcome.value,
                        "backup": a_res.backup_result.outcome.value,
                        "both_unavailable": a_res.both_unavailable,
                    },
                }
                scenario_outcome_changes.append(change_record)
                differences.append(
                    DiffItem(
                        category="scenario_outcome",
                        change_type="improved" if b_res.both_unavailable and not a_res.both_unavailable else "changed",
                        identifier=scn.id,
                        before_state=f"Both Unavailable: {b_res.both_unavailable}",
                        after_state=f"Both Unavailable: {a_res.both_unavailable}",
                        description=f"Under '{scn.name}', backup outcome changed from {b_res.backup_result.outcome.value} to {a_res.backup_result.outcome.value}.",
                    )
                )

        # 4. Compare Evidence Status
        before_deps_map = {d.id: d for d in self.before_model.dependencies}
        after_deps_map = {d.id: d for d in self.after_model.dependencies}
        evidence_status_changes = []

        for dep_id, after_dep in after_deps_map.items():
            if dep_id in before_deps_map:
                before_dep = before_deps_map[dep_id]
                if before_dep.evidence.status != after_dep.evidence.status:
                    record = {
                        "dependency_id": dep_id,
                        "source": after_dep.source_component_id,
                        "target": after_dep.target_component_id,
                        "before_status": before_dep.evidence.status.value,
                        "after_status": after_dep.evidence.status.value,
                    }
                    evidence_status_changes.append(record)
                    differences.append(
                        DiffItem(
                            category="evidence",
                            change_type="status_change",
                            identifier=dep_id,
                            before_state=before_dep.evidence.status.value,
                            after_state=after_dep.evidence.status.value,
                            description=f"Evidence for '{after_dep.source_component_id} -> {after_dep.target_component_id}' upgraded from {before_dep.evidence.status.value} to {after_dep.evidence.status.value}.",
                        )
                    )

        return AssessmentDiffResult(
            before_snapshot_version=self.before_model.metadata.version,
            after_snapshot_version=self.after_model.metadata.version,
            fixed_cut_sets=fixed_cut_sets,
            new_cut_sets=new_cut_sets,
            resolved_dependencies=resolved_deps,
            new_shared_dependencies=new_shared_deps,
            scenario_outcome_changes=scenario_outcome_changes,
            evidence_status_changes=evidence_status_changes,
            differences=differences,
        )
