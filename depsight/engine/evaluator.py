"""Top-level analytical evaluator orchestrating the complete Backup Independence Assessment."""

from __future__ import annotations
import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any

import depsight
from depsight.engine.models import (
    ArchitectureModel,
    AssessmentReport,
    Scenario,
    ScenarioResult,
    CutSet,
    EvidenceCoverage,
    Finding,
    EvidenceStatus,
    ServiceOutcome,
)
from depsight.engine.graph import DependencyGraph
from depsight.engine.propagation import PropagationEngine
from depsight.engine.cutsets import CutSetAnalyzer
from depsight.engine.scenarios import ScenarioEngine
from depsight.engine.coverage import EvidenceCoverageCalculator
from depsight.engine.evidence import EvidenceInspector


class IndependenceEvaluator:
    """Master evaluator coordinating graph analysis, scenarios, cut sets, and reports."""

    def __init__(self, model: ArchitectureModel):
        self.model = model
        self.graph = DependencyGraph(model)
        self.propagation_engine = PropagationEngine(model, self.graph)
        self.cutset_analyzer = CutSetAnalyzer(model, self.graph)
        self.scenario_engine = ScenarioEngine(model, self.graph)
        self.coverage_calc = EvidenceCoverageCalculator(model, self.graph)
        self.evidence_inspector = EvidenceInspector(model, self.graph)

    def run_assessment(
        self,
        custom_scenarios: Optional[List[Scenario]] = None,
        max_cutset_size: int = 2,
        evidence_cutoff_date: Optional[str] = None,
        fixed_timestamp: Optional[str] = None,
    ) -> AssessmentReport:
        """
        Execute full Backup Independence Assessment deterministically.
        Produces the 12-section Backup Independence Report data model.
        """
        cutoff_date = evidence_cutoff_date or self.model.metadata.created_at[:10]
        gen_timestamp = fixed_timestamp or f"{cutoff_date}T00:00:00Z"

        # 1. Scope
        primary_root = self.model.service.primary_arrangement.root_component_id
        backup_root = self.model.service.backup_arrangement.root_component_id
        shared_comps = self.graph.get_shared_components(primary_root, backup_root)
        shared_domains = self.graph.get_shared_failure_domains(primary_root, backup_root)

        scope = {
            "service_id": self.model.service.id,
            "service_name": self.model.service.name,
            "criticality": self.model.service.criticality,
            "primary_arrangement": {
                "name": self.model.service.primary_arrangement.name,
                "root_component_id": primary_root,
                "upstream_components_count": len(self.graph.get_upstream_components(primary_root)),
            },
            "backup_arrangement": {
                "name": self.model.service.backup_arrangement.name,
                "root_component_id": backup_root,
                "upstream_components_count": len(self.graph.get_upstream_components(backup_root)),
            },
            "shared_components": shared_comps,
            "shared_failure_domains": shared_domains,
            "total_components": len(self.model.components),
            "total_dependencies": len(self.model.dependencies),
        }

        # 2. Architecture snapshot
        arch_snapshot = {
            "model_name": self.model.metadata.name,
            "model_version": self.model.metadata.version,
            "created_at": self.model.metadata.created_at,
            "providers_count": len(self.model.providers),
            "deployments_count": len(self.model.deployments),
            "failure_domains_count": len(self.model.failure_domains),
        }

        # 3. Scenarios
        active_scenarios = custom_scenarios or self.scenario_engine.get_standard_scenarios()
        scenario_outcomes = self.scenario_engine.evaluate_all(active_scenarios)

        # 4. Common-cause cut sets
        cut_sets = self.cutset_analyzer.compute_minimal_cut_sets(max_size=max_cutset_size)

        # 5. Evidence Coverage
        primary_coverage = self.coverage_calc.calculate_primary_coverage(cutoff_date)
        backup_coverage = self.coverage_calc.calculate_backup_coverage(cutoff_date)
        overall_coverage = self.coverage_calc.calculate_coverage(cutoff_date_str=cutoff_date)

        # 6. Findings
        findings = self.evidence_inspector.generate_findings(cutoff_date)

        # Add cut set findings
        for cs in cut_sets:
            severity = "HIGH" if cs.size == 1 else "MEDIUM"
            findings.append(
                Finding(
                    id=f"FINDING-CS-{'+'.join(cs.components)}",
                    title=f"Common-Cause Cut Set ({cs.classification.value}): {' + '.join(cs.components)}",
                    severity=severity,
                    description=(
                        f"Simultaneous failure of {cs.components} causes both primary and backup arrangements "
                        f"to evaluate to UNAVAILABLE. Classification is {cs.classification.value}."
                    ),
                    affected_arrangements=["primary", "backup"],
                    causal_components=cs.components,
                    evidence_status=EvidenceStatus.CONFIRMED if cs.classification.value == "CONFIRMED" else EvidenceStatus.INFERRED,
                    recommendation=(
                        f"Architecturally isolate or provide independent failover rails for {', '.join(cs.components)}."
                    ),
                )
            )

        # 7. Open Questions
        open_questions = [
            "Are unverified upstream fallback activation timeouts tested during load under partial network partitions?",
            "Can identity provider tokens be cached or verified offline during an active IdP outage?",
            "What automated change-control mechanism ensures future deployments do not re-introduce shared dependencies?",
        ]
        if overall_coverage.inferred_or_unverified_count > 0:
            open_questions.append(
                f"Who will review and provide verifiable technical logs for the {overall_coverage.inferred_or_unverified_count} unverified/inferred relationships?"
            )
        if overall_coverage.stale_count > 0:
            open_questions.append(
                f"When will the {overall_coverage.stale_count} stale architecture evidence records be re-certified?"
            )

        # 8. Limitations
        limitations = [
            "Assessment conclusions hold strictly for the modeled architecture scope, explicit scenario assumptions, and recorded evidence.",
            "Missing evidence is never interpreted as independence; unverified dependencies are graded accordingly.",
            "This assessment evaluates deterministic structural dependencies and static failover topology, not runtime chaos injection, network latency dynamics, or recovery time estimates (RTO/RPO).",
            "Provider corporate diversity does not guarantee physical or logical failure domain diversity.",
        ]

        # Generate deterministic report ID
        report_id = f"DIR-{self.model.service.id.upper()}-{self.model.metadata.version}"

        return AssessmentReport(
            report_id=report_id,
            title=f"Backup Independence Assessment Report: {self.model.service.name}",
            generated_at=gen_timestamp,
            engine_version=depsight.__version__,
            ruleset_version=self.model.metadata.ruleset_version,
            service_id=self.model.service.id,
            service_name=self.model.service.name,
            scope=scope,
            architecture_metadata=self.model.metadata,
            evidence_cutoff_date=cutoff_date,
            assumptions=sorted(self.model.assumptions),
            scenario_outcomes=scenario_outcomes,
            common_cause_cut_sets=cut_sets,
            primary_coverage=primary_coverage,
            backup_coverage=backup_coverage,
            overall_coverage=overall_coverage,
            findings=findings,
            open_questions=open_questions,
            limitations=limitations,
        )
