"""Core Pydantic Domain Models for DepenSight.

Strict typing and deterministic representation of:
- Three-valued logic (UP, DOWN, UNKNOWN)
- Service outcomes (AVAILABLE, DEGRADED, UNAVAILABLE, INDETERMINATE)
- Dependency rules (ALL, ANY, OPTIONAL, UNKNOWN)
- Evidence grading (CONFIRMED, INFERRED, UNVERIFIED, DISPUTED, SUPERSEDED)
- Architecture entities, cut sets, scenarios, and assessment reports.
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import date
from pydantic import BaseModel, Field, ConfigDict


class ComponentState(str, Enum):
    """Three-valued component state."""
    UP = "UP"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class ServiceOutcome(str, Enum):
    """Four-valued service-level outcome."""
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    INDETERMINATE = "INDETERMINATE"


class DependencyRule(str, Enum):
    """Rule evaluated over a dependency or dependency group."""
    ALL = "ALL"
    ANY = "ANY"
    OPTIONAL = "OPTIONAL"
    UNKNOWN = "UNKNOWN"


class EvidenceStatus(str, Enum):
    """Evidence grading classification."""
    CONFIRMED = "CONFIRMED"
    INFERRED = "INFERRED"
    UNVERIFIED = "UNVERIFIED"
    DISPUTED = "DISPUTED"
    SUPERSEDED = "SUPERSEDED"


class CutSetClassification(str, Enum):
    """Classification for minimal common-cause cut sets."""
    CONFIRMED = "CONFIRMED"
    POSSIBLE = "POSSIBLE"


class Provider(BaseModel):
    """External or internal infrastructure / service provider."""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    category: str = "infrastructure"  # cloud, saas, payment, identity, telecom, etc.
    description: Optional[str] = None


class Deployment(BaseModel):
    """Provider-specific regional deployment or hosting unit."""
    model_config = ConfigDict(extra="forbid")
    id: str
    provider_id: str
    region: str
    environment: str = "production"
    description: Optional[str] = None


class FailureDomain(BaseModel):
    """Named failure domain boundary (region, AZ, cloud tenant, network segment)."""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    type: str  # region, az, provider, account, network, control_plane
    provider_id: Optional[str] = None
    description: Optional[str] = None


class Component(BaseModel):
    """Graph node representing a software component, service, or resource."""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    type: str  # service, api, database, idp, dns, gateway, queue, cache
    provider_id: Optional[str] = None
    deployment_id: Optional[str] = None
    failure_domains: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class Evidence(BaseModel):
    """Traceable evidence backing a dependency relationship."""
    model_config = ConfigDict(extra="forbid")
    id: str
    relationship_id: Optional[str] = None
    status: EvidenceStatus = EvidenceStatus.UNVERIFIED
    source: str
    evidence_reference: Optional[str] = None
    evidence_date: Optional[str] = None  # YYYY-MM-DD
    verification_date: Optional[str] = None  # YYYY-MM-DD
    owner: Optional[str] = None
    review_status: Optional[str] = "unreviewed"
    validity_period_days: Optional[int] = 180
    scope: Optional[str] = None
    notes: Optional[str] = None


class Dependency(BaseModel):
    """
    Directed edge: Dependent component -> Required component.
    Failure propagates backward from a failed required component to dependents.
    """
    model_config = ConfigDict(extra="forbid")
    id: str
    source_component_id: str  # Dependent
    target_component_id: str  # Required
    group_id: Optional[str] = None
    rule: DependencyRule = DependencyRule.ALL
    evidence: Evidence
    description: Optional[str] = None


class DependencyGroup(BaseModel):
    """
    Group of required dependencies evaluated under a single combined rule
    (e.g., ANY of [Stripe, Adyen] or ALL of [Database, Cache]).
    """
    model_config = ConfigDict(extra="forbid")
    id: str
    dependent_component_id: str
    name: str
    rule: DependencyRule = DependencyRule.ALL
    member_target_ids: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class ServiceArrangement(BaseModel):
    """Arrangement definition for primary or backup service flow."""
    model_config = ConfigDict(extra="forbid")
    name: str  # primary or backup
    root_component_id: str
    description: Optional[str] = None


class Service(BaseModel):
    """Critical business service under analysis."""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    criticality: str = "critical"
    primary_arrangement: ServiceArrangement
    backup_arrangement: ServiceArrangement
    description: Optional[str] = None


class ModelMetadata(BaseModel):
    """Metadata describing the architecture model snapshot."""
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str = "1.0.0"
    ruleset_version: str = "2026.11"
    created_at: str
    updated_at: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None


class ArchitectureModel(BaseModel):
    """Complete specification of a system architecture under review."""
    model_config = ConfigDict(extra="forbid")
    metadata: ModelMetadata
    service: Service
    providers: List[Provider] = Field(default_factory=list)
    deployments: List[Deployment] = Field(default_factory=list)
    failure_domains: List[FailureDomain] = Field(default_factory=list)
    components: List[Component] = Field(default_factory=list)
    dependency_groups: List[DependencyGroup] = Field(default_factory=list)
    dependencies: List[Dependency] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)


class Scenario(BaseModel):
    """Outage scenario specification for evaluation."""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    description: str
    failed_component_ids: List[str] = Field(default_factory=list)
    failed_failure_domain_ids: List[str] = Field(default_factory=list)
    assumed_behavior: Dict[str, ComponentState] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)


class CausalStep(BaseModel):
    """Step in causal failure chain."""
    model_config = ConfigDict(extra="forbid")
    component_id: str
    component_name: str
    state: ComponentState
    rule: DependencyRule
    reason: str
    failed_dependencies: List[str] = Field(default_factory=list)


class ArrangementResult(BaseModel):
    """Outcome for a single arrangement (primary or backup)."""
    model_config = ConfigDict(extra="forbid")
    arrangement_name: str
    root_component_id: str
    outcome: ServiceOutcome
    causal_path: List[str] = Field(default_factory=list)
    causal_steps: List[CausalStep] = Field(default_factory=list)
    primary_failure_reason: Optional[str] = None


class ScenarioResult(BaseModel):
    """Comprehensive evaluation outcome of a scenario."""
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    scenario_name: str
    primary_result: ArrangementResult
    backup_result: ArrangementResult
    both_unavailable: bool
    joint_degraded: bool
    component_states: Dict[str, ComponentState] = Field(default_factory=dict)
    active_failed_components: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)


class CutSet(BaseModel):
    """Minimal common-cause cut set."""
    model_config = ConfigDict(extra="forbid")
    components: List[str]
    size: int
    classification: CutSetClassification
    affected_arrangements: List[str] = Field(default_factory=lambda: ["primary", "backup"])
    supporting_paths: Dict[str, List[str]] = Field(default_factory=dict)
    evidence_limitations: List[str] = Field(default_factory=list)
    shared_failure_domains: List[str] = Field(default_factory=list)


class EvidenceCoverage(BaseModel):
    """Evidence coverage metrics per arrangement or overall."""
    model_config = ConfigDict(extra="forbid")
    scope_name: str
    total_relationships: int
    confirmed_count: int
    confirmed_percentage: float
    inferred_or_unverified_count: int
    inferred_or_unverified_percentage: float
    stale_count: int
    stale_percentage: float
    disputed_count: int
    unknown_rule_count: int
    staleness_threshold_days: int = 180


class DiffItem(BaseModel):
    """Difference item between two assessments."""
    model_config = ConfigDict(extra="forbid")
    category: str  # cut_set, dependency, evidence, scenario_outcome
    change_type: str  # added, removed, changed, resolved, newly_introduced
    identifier: str
    before_state: Optional[Any] = None
    after_state: Optional[Any] = None
    description: str


class AssessmentDiffResult(BaseModel):
    """Comparison between two architecture snapshots under identical scenarios."""
    model_config = ConfigDict(extra="forbid")
    before_snapshot_version: str
    after_snapshot_version: str
    fixed_cut_sets: List[CutSet] = Field(default_factory=list)
    new_cut_sets: List[CutSet] = Field(default_factory=list)
    resolved_dependencies: List[str] = Field(default_factory=list)
    new_shared_dependencies: List[str] = Field(default_factory=list)
    scenario_outcome_changes: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_status_changes: List[Dict[str, Any]] = Field(default_factory=list)
    differences: List[DiffItem] = Field(default_factory=list)


class Finding(BaseModel):
    """Defensible finding produced by an assessment run."""
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    severity: str  # HIGH, MEDIUM, LOW, INFORMATIONAL
    description: str
    affected_arrangements: List[str] = Field(default_factory=list)
    causal_components: List[str] = Field(default_factory=list)
    evidence_status: EvidenceStatus
    recommendation: str


class AssessmentReport(BaseModel):
    """Complete, deterministic Backup Independence Report."""
    model_config = ConfigDict(extra="forbid")
    report_id: str
    title: str
    generated_at: str
    engine_version: str
    ruleset_version: str
    service_id: str
    service_name: str
    scope: Dict[str, Any]
    architecture_metadata: ModelMetadata
    evidence_cutoff_date: str
    assumptions: List[str]
    scenario_outcomes: List[ScenarioResult]
    common_cause_cut_sets: List[CutSet]
    primary_coverage: EvidenceCoverage
    backup_coverage: EvidenceCoverage
    overall_coverage: EvidenceCoverage
    findings: List[Finding]
    open_questions: List[str]
    limitations: List[str]
