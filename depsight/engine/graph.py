"""Dependency graph representation using NetworkX.

Conventions:
- Dependent component -> Required component (u -> v where u requires v)
- Failure propagates from target (v) back to source (u)
- Deterministic node and edge ordering
"""

from __future__ import annotations
from typing import Dict, List, Set, Optional, Tuple, Any
import networkx as nx

from depsight.engine.models import (
    ArchitectureModel,
    Component,
    Dependency,
    DependencyGroup,
    DependencyRule,
    Evidence,
    Provider,
    Deployment,
    FailureDomain,
)


class DependencyGraph:
    """NetworkX-backed dependency graph with deterministic indexing and path tracing."""

    def __init__(self, model: ArchitectureModel):
        self.model = model
        self.graph = nx.DiGraph()
        self._build_graph()

    def _build_graph(self) -> None:
        """Construct graph deterministically from the ArchitectureModel."""
        # Add nodes with metadata sorted by ID
        for comp in sorted(self.model.components, key=lambda c: c.id):
            self.graph.add_node(
                comp.id,
                name=comp.name,
                type=comp.type,
                provider_id=comp.provider_id,
                deployment_id=comp.deployment_id,
                failure_domains=sorted(comp.failure_domains),
                description=comp.description or "",
            )

        # Store dependency groups indexed by dependent_component_id
        self.groups_by_dependent: Dict[str, List[DependencyGroup]] = {}
        for g in sorted(self.model.dependency_groups, key=lambda x: x.id):
            self.groups_by_dependent.setdefault(g.dependent_component_id, []).append(g)

        # Map each (source, target) to its Dependency
        self.dependencies_by_edge: Dict[Tuple[str, str], Dependency] = {}
        for dep in sorted(self.model.dependencies, key=lambda d: d.id):
            edge = (dep.source_component_id, dep.target_component_id)
            self.dependencies_by_edge[edge] = dep
            self.graph.add_edge(
                dep.source_component_id,
                dep.target_component_id,
                id=dep.id,
                rule=dep.rule,
                group_id=dep.group_id,
                evidence=dep.evidence,
            )

    @property
    def node_ids(self) -> List[str]:
        """Deterministically sorted list of all component IDs."""
        return sorted(self.graph.nodes())

    def get_component(self, component_id: str) -> Optional[Component]:
        """Look up Component definition by ID."""
        for c in self.model.components:
            if c.id == component_id:
                return c
        return None

    def get_required_dependencies(self, component_id: str) -> List[str]:
        """Return target component IDs directly required by component_id (outgoing edges)."""
        if component_id not in self.graph:
            return []
        return sorted(self.graph.successors(component_id))

    def get_dependent_components(self, component_id: str) -> List[str]:
        """Return component IDs that directly depend on component_id (incoming edges)."""
        if component_id not in self.graph:
            return []
        return sorted(self.graph.predecessors(component_id))

    def get_upstream_components(self, root_id: str) -> Set[str]:
        """
        Return all transitive required dependencies (reachable from root_id).
        Includes the root_id itself.
        """
        if root_id not in self.graph:
            return set()
        reachable = nx.descendants(self.graph, root_id)
        reachable.add(root_id)
        return reachable

    def get_upstream_dependencies(self, root_id: str) -> List[Dependency]:
        """Return all Dependency edges within the reachable subgraph of root_id."""
        upstream_nodes = self.get_upstream_components(root_id)
        deps = []
        for (u, v), dep in sorted(self.dependencies_by_edge.items(), key=lambda x: x[0]):
            if u in upstream_nodes and v in upstream_nodes:
                deps.append(dep)
        return deps

    def get_shared_components(self, root_a: str, root_b: str) -> List[str]:
        """Find components required by both root_a and root_b arrangements."""
        upstream_a = self.get_upstream_components(root_a)
        upstream_b = self.get_upstream_components(root_b)
        shared = upstream_a.intersection(upstream_b)
        # Exclude the roots themselves if different
        shared.discard(root_a)
        shared.discard(root_b)
        return sorted(shared)

    def get_shared_failure_domains(self, root_a: str, root_b: str) -> List[str]:
        """Find failure domains shared across upstream components of both arrangements."""
        upstream_a = self.get_upstream_components(root_a)
        upstream_b = self.get_upstream_components(root_b)

        domains_a = set()
        for cid in upstream_a:
            comp = self.get_component(cid)
            if comp:
                domains_a.update(comp.failure_domains)

        domains_b = set()
        for cid in upstream_b:
            comp = self.get_component(cid)
            if comp:
                domains_b.update(comp.failure_domains)

        return sorted(domains_a.intersection(domains_b))

    def find_all_paths_to_target(self, source_id: str, target_id: str) -> List[List[str]]:
        """Find all simple directed dependency paths from source to target."""
        if source_id not in self.graph or target_id not in self.graph:
            return []
        try:
            return sorted(list(nx.all_simple_paths(self.graph, source_id, target_id)))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
