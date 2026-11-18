"""Standard outage scenario library and execution manager."""

from __future__ import annotations
from typing import List, Dict, Optional

from depsight.engine.models import ArchitectureModel, Scenario, ScenarioResult
from depsight.engine.graph import DependencyGraph
from depsight.engine.propagation import PropagationEngine


class ScenarioEngine:
    """Manages standard and custom scenario evaluation."""

    def __init__(self, model: ArchitectureModel, graph: Optional[DependencyGraph] = None):
        self.model = model
        self.graph = graph or DependencyGraph(model)
        self.engine = PropagationEngine(model, self.graph)

    def get_standard_scenarios(self) -> List[Scenario]:
        """
        Build the canonical 7 standard scenarios adapted to the current ArchitectureModel:
        1. Single component failure (Primary Core Database / Gateway)
        2. Regional outage (Primary cloud region)
        3. Provider-service disruption (Primary cloud provider)
        4. Identity or access failure (IAM / Auth Directory)
        5. DNS or connectivity loss (Public DNS / Edge Network)
        6. Primary and backup both degraded (Shared caching or metrics loss)
        7. Backup unavailable during primary failure (Simultaneous primary failure + backup dependency gap)
        """
        scenarios: List[Scenario] = []

        # Find key archetypal components/domains in the model
        primary_root = self.model.service.primary_arrangement.root_component_id
        backup_root = self.model.service.backup_arrangement.root_component_id

        # Look for regions/providers/IAM/DNS in model
        primary_comp = self.graph.get_component(primary_root)
        primary_deployment_id = primary_comp.deployment_id if primary_comp else None
        primary_region = None
        for d in self.model.deployments:
            if d.id == primary_deployment_id:
                primary_region = d.region

        # Regional failure domain
        regional_domain_id = None
        for fd in self.model.failure_domains:
            if fd.type in ("region", "az"):
                regional_domain_id = fd.id
                break

        # IAM / Auth component
        iam_comp_id = None
        for c in self.model.components:
            if c.type in ("idp", "iam", "auth") or "iam" in c.id.lower() or "auth" in c.id.lower():
                iam_comp_id = c.id
                break

        # DNS component
        dns_comp_id = None
        for c in self.model.components:
            if c.type in ("dns", "edge", "cdn") or "dns" in c.id.lower():
                dns_comp_id = c.id
                break

        # Primary database or internal service
        db_comp_id = None
        for c in self.model.components:
            if c.type in ("database", "db") or "db" in c.id.lower() or "database" in c.id.lower():
                db_comp_id = c.id
                break
        if not db_comp_id and len(self.model.components) > 1:
            db_comp_id = [c.id for c in self.model.components if c.id != primary_root and c.id != backup_root][0]

        # 1. Single component failure
        target_single = db_comp_id or primary_root
        scenarios.append(
            Scenario(
                id="SCN-01-SINGLE-COMPONENT",
                name="Single Component Failure",
                description=f"Isolated outage of primary database/subsystem '{target_single}'.",
                failed_component_ids=[target_single],
                assumptions=["Component experiences complete outage; fails immediately."],
            )
        )

        # 2. Regional outage
        target_fd = regional_domain_id or (self.model.failure_domains[0].id if self.model.failure_domains else "region-primary")
        scenarios.append(
            Scenario(
                id="SCN-02-REGIONAL-OUTAGE",
                name="Regional Outage",
                description=f"Complete availability failure of primary hosting failure domain '{target_fd}'.",
                failed_failure_domain_ids=[target_fd],
                assumptions=["All workloads and managed components residing within failure domain collapse simultaneously."],
            )
        )

        # 3. Provider-service disruption
        primary_provider_id = primary_comp.provider_id if primary_comp else (self.model.providers[0].id if self.model.providers else "provider-primary")
        provider_comps = [c.id for c in self.model.components if c.provider_id == primary_provider_id]
        scenarios.append(
            Scenario(
                id="SCN-03-PROVIDER-DISRUPTION",
                name="Provider-Service Disruption",
                description=f"Major control plane or service disruption across provider '{primary_provider_id}'.",
                failed_component_ids=sorted(provider_comps),
                assumptions=[f"All services hosted under provider {primary_provider_id} become inaccessible."],
            )
        )

        # 4. Identity or access failure
        target_iam = iam_comp_id or (self.model.components[1].id if len(self.model.components) > 1 else primary_root)
        scenarios.append(
            Scenario(
                id="SCN-04-IDENTITY-ACCESS-FAILURE",
                name="Identity or Access Failure",
                description=f"Outage of directory / identity provider '{target_iam}' used for cross-service authentication.",
                failed_component_ids=[target_iam],
                assumptions=["Token issuance and identity federation fail completely."],
            )
        )

        # 5. DNS or connectivity loss
        target_dns = dns_comp_id or (self.model.components[2].id if len(self.model.components) > 2 else primary_root)
        scenarios.append(
            Scenario(
                id="SCN-05-DNS-CONNECTIVITY-LOSS",
                name="DNS or Connectivity Loss",
                description=f"Outage of edge routing / DNS resolution provider '{target_dns}'.",
                failed_component_ids=[target_dns],
                assumptions=["DNS name resolution drops or routes traffic to dead endpoints."],
            )
        )

        # 6. Primary and backup both degraded
        # Pick any optional component, or an analytics/cache node
        opt_comp = None
        for dep in self.model.dependencies:
            if dep.rule.value == "OPTIONAL":
                opt_comp = dep.target_component_id
                break
        target_deg = opt_comp or target_dns
        scenarios.append(
            Scenario(
                id="SCN-06-DUAL-DEGRADATION",
                name="Primary and Backup Both Degraded",
                description=f"Non-fatal dependency '{target_deg}' fails, causing degradation without full outage.",
                failed_component_ids=[target_deg],
                assumptions=["Non-mandatory caching, telemetry or auxiliary services fail."],
            )
        )

        # 7. Backup unavailable during primary failure
        # Primary root fails while secondary database / backup critical path also fails
        backup_comps = sorted(list(self.graph.get_upstream_components(backup_root)))
        target_backup_sub = backup_comps[1] if len(backup_comps) > 1 else backup_root
        scenarios.append(
            Scenario(
                id="SCN-07-BACKUP-UNAVAILABLE-DURING-PRIMARY",
                name="Backup Unavailable During Primary Failure",
                description="Primary fails over to backup, but backup suffers internal dependency failure.",
                failed_component_ids=sorted(list({primary_root, target_backup_sub})),
                assumptions=["Simultaneous primary outage and backup dependency failure."],
            )
        )

        return scenarios

    def evaluate_all(self, scenarios: Optional[List[Scenario]] = None) -> List[ScenarioResult]:
        """Evaluate a collection of scenarios (or all standard ones) in deterministic order."""
        active_scenarios = scenarios or self.get_standard_scenarios()
        results = []
        for scn in sorted(active_scenarios, key=lambda s: s.id):
            results.append(self.engine.evaluate_scenario(scn))
        return results
