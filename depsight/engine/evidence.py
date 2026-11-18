"""Evidence grading, verification inspection, and data-gap identification."""

from __future__ import annotations
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple, Any

from depsight.engine.models import (
    ArchitectureModel,
    Evidence,
    EvidenceStatus,
    Dependency,
    Finding,
)
from depsight.engine.graph import DependencyGraph


class EvidenceInspector:
    """Inspects evidence quality, staleness, conflicts, and gaps."""

    def __init__(self, model: ArchitectureModel, graph: Optional[DependencyGraph] = None):
        self.model = model
        self.graph = graph or DependencyGraph(model)

    def is_stale(
        self,
        evidence: Evidence,
        cutoff_date_str: Optional[str] = None,
        staleness_threshold_days: int = 180,
    ) -> Tuple[bool, Optional[int]]:
        """
        Check if evidence is past its validity period or verification staleness threshold.
        Returns: (is_stale, days_since_verification)
        """
        if not evidence.verification_date and not evidence.evidence_date:
            return True, None

        ref_str = evidence.verification_date or evidence.evidence_date
        try:
            record_date = datetime.strptime(ref_str, "%Y-%m-%d").date()
        except ValueError:
            return True, None

        if cutoff_date_str:
            try:
                today = datetime.strptime(cutoff_date_str, "%Y-%m-%d").date()
            except ValueError:
                today = date.today()
        else:
            today = date.today()

        days_elapsed = (today - record_date).days
        threshold = evidence.validity_period_days or staleness_threshold_days
        return days_elapsed > threshold, days_elapsed

    def get_evidence_gaps(self, cutoff_date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """Identify missing, unverified, disputed, and stale evidence records."""
        gaps = []
        for dep in sorted(self.model.dependencies, key=lambda d: d.id):
            ev = dep.evidence
            is_stale, days = self.is_stale(ev, cutoff_date_str)

            if ev.status in (EvidenceStatus.UNVERIFIED, EvidenceStatus.INFERRED, EvidenceStatus.DISPUTED):
                gaps.append({
                    "dependency_id": dep.id,
                    "source": dep.source_component_id,
                    "target": dep.target_component_id,
                    "issue_type": ev.status.value,
                    "description": f"Relationship backed only by {ev.status.value} evidence: '{ev.source}'",
                    "owner": ev.owner or "Unassigned",
                    "evidence_date": ev.evidence_date,
                    "verification_date": ev.verification_date,
                })
            elif is_stale:
                gaps.append({
                    "dependency_id": dep.id,
                    "source": dep.source_component_id,
                    "target": dep.target_component_id,
                    "issue_type": "STALE",
                    "description": f"Evidence is stale ({days} days elapsed, threshold is {ev.validity_period_days or 180} days)",
                    "owner": ev.owner or "Unassigned",
                    "evidence_date": ev.evidence_date,
                    "verification_date": ev.verification_date,
                })
        return gaps

    def generate_findings(self, cutoff_date_str: Optional[str] = None) -> List[Finding]:
        """Produce actionable evidence-gap findings."""
        findings: List[Finding] = []
        finding_idx = 1

        primary_root = self.model.service.primary_arrangement.root_component_id
        backup_root = self.model.service.backup_arrangement.root_component_id
        primary_upstream = self.graph.get_upstream_components(primary_root)
        backup_upstream = self.graph.get_upstream_components(backup_root)

        for dep in sorted(self.model.dependencies, key=lambda d: d.id):
            ev = dep.evidence
            is_stale, days = self.is_stale(ev, cutoff_date_str)

            affected = []
            if dep.source_component_id in primary_upstream or dep.target_component_id in primary_upstream:
                affected.append("primary")
            if dep.source_component_id in backup_upstream or dep.target_component_id in backup_upstream:
                affected.append("backup")

            if ev.status == EvidenceStatus.DISPUTED:
                findings.append(
                    Finding(
                        id=f"FINDING-{finding_idx:03d}",
                        title=f"Disputed dependency relationship: {dep.source_component_id} -> {dep.target_component_id}",
                        severity="HIGH",
                        description=f"Evidence for dependency {dep.id} is marked DISPUTED. Conflicting architectural claims exist regarding whether {dep.target_component_id} is required.",
                        affected_arrangements=affected,
                        causal_components=[dep.source_component_id, dep.target_component_id],
                        evidence_status=EvidenceStatus.DISPUTED,
                        recommendation="Conduct an architectural interview to resolve dispute with authoritative code/config evidence.",
                    )
                )
                finding_idx += 1
            elif ev.status in (EvidenceStatus.UNVERIFIED, EvidenceStatus.INFERRED):
                severity = "HIGH" if len(affected) == 2 else "MEDIUM"
                findings.append(
                    Finding(
                        id=f"FINDING-{finding_idx:03d}",
                        title=f"{ev.status.value.title()} dependency on critical path: {dep.source_component_id} -> {dep.target_component_id}",
                        severity=severity,
                        description=f"Dependency {dep.id} relies on {ev.status.value.lower()} evidence ('{ev.source}'). Missing verified technical proof.",
                        affected_arrangements=affected,
                        causal_components=[dep.source_component_id, dep.target_component_id],
                        evidence_status=ev.status,
                        recommendation=f"Review active configuration or test runs to upgrade evidence status to CONFIRMED.",
                    )
                )
                finding_idx += 1
            elif is_stale:
                findings.append(
                    Finding(
                        id=f"FINDING-{finding_idx:03d}",
                        title=f"Stale verification: {dep.source_component_id} -> {dep.target_component_id}",
                        severity="LOW",
                        description=f"Dependency verification is {days} days old, exceeding the validity period of {ev.validity_period_days or 180} days.",
                        affected_arrangements=affected,
                        causal_components=[dep.source_component_id, dep.target_component_id],
                        evidence_status=ev.status,
                        recommendation="Conduct scheduled evidence refresh with component owner.",
                    )
                )
                finding_idx += 1

        return findings
