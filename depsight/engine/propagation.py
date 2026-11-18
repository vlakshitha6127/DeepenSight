"""Propagation engine implementing three-valued logic, fixed-point iteration, and causal path tracing."""

from __future__ import annotations
from typing import Dict, List, Set, Tuple, Optional, Any
from copy import deepcopy

from depsight.engine.models import (
    ArchitectureModel,
    ComponentState,
    ServiceOutcome,
    DependencyRule,
    Scenario,
    CausalStep,
    ArrangementResult,
    ScenarioResult,
)
from depsight.engine.graph import DependencyGraph


class PropagationEngine:
    """Deterministic failure propagation engine using monotone fixed-point updates."""

    def __init__(self, model: ArchitectureModel, graph: Optional[DependencyGraph] = None):
        self.model = model
        self.graph = graph or DependencyGraph(model)

    def evaluate_scenario(self, scenario: Scenario) -> ScenarioResult:
        """
        Evaluate an outage scenario across the entire architecture graph.
        Returns full scenario results including primary and backup arrangement outcomes,
        causal paths, and component states.
        """
        # Step 1: Determine initial active faults
        active_failed_components: Set[str] = set()

        # Direct component failures
        for cid in scenario.failed_component_ids:
            if cid in self.graph.graph:
                active_failed_components.add(cid)

        # Failure domain failures
        if scenario.failed_failure_domain_ids:
            failed_domains_set = set(scenario.failed_failure_domain_ids)
            for cid in self.graph.node_ids:
                comp = self.graph.get_component(cid)
                if comp and any(fd in failed_domains_set for fd in comp.failure_domains):
                    active_failed_components.add(cid)

        # Step 2: Initialize component states
        # States: UP, DOWN, UNKNOWN
        component_states: Dict[str, ComponentState] = {}
        for cid in self.graph.node_ids:
            if cid in active_failed_components:
                component_states[cid] = ComponentState.DOWN
            elif cid in scenario.assumed_behavior:
                component_states[cid] = scenario.assumed_behavior[cid]
            else:
                component_states[cid] = ComponentState.UP

        # Track causal explanation for each component
        causal_reasons: Dict[str, Tuple[str, List[str], DependencyRule]] = {}
        for cid in active_failed_components:
            causal_reasons[cid] = ("Directly triggered scenario fault / failure domain outage", [], DependencyRule.ALL)

        # Step 3: Fixed-point monotone iteration
        # Deterministic node ordering: sorted node IDs
        sorted_nodes = self.graph.node_ids
        max_iterations = max(20, 2 * len(sorted_nodes))
        iteration = 0

        # Degradation flags for components whose mandatory deps are UP but optional deps are DOWN
        degraded_components: Set[str] = set()

        while iteration < max_iterations:
            iteration += 1
            changed = False

            for cid in sorted_nodes:
                # Active root faults never recover
                if cid in active_failed_components:
                    continue

                old_state = component_states[cid]
                new_state, is_degraded, reason, failed_deps, rule_used = self._evaluate_component_state(
                    cid, component_states
                )

                if is_degraded:
                    degraded_components.add(cid)
                elif cid in degraded_components and not is_degraded:
                    degraded_components.remove(cid)

                if new_state != old_state:
                    component_states[cid] = new_state
                    causal_reasons[cid] = (reason, failed_deps, rule_used)
                    changed = True

            if not changed:
                break

        # Step 4: Evaluate arrangement outcomes (Primary & Backup)
        primary_result = self._evaluate_arrangement(
            self.model.service.primary_arrangement.name,
            self.model.service.primary_arrangement.root_component_id,
            component_states,
            degraded_components,
            causal_reasons,
            active_failed_components,
        )

        backup_result = self._evaluate_arrangement(
            self.model.service.backup_arrangement.name,
            self.model.service.backup_arrangement.root_component_id,
            component_states,
            degraded_components,
            causal_reasons,
            active_failed_components,
        )

        both_unavailable = (
            primary_result.outcome == ServiceOutcome.UNAVAILABLE
            and backup_result.outcome == ServiceOutcome.UNAVAILABLE
        )

        joint_degraded = (
            primary_result.outcome in (ServiceOutcome.UNAVAILABLE, ServiceOutcome.DEGRADED)
            and backup_result.outcome in (ServiceOutcome.UNAVAILABLE, ServiceOutcome.DEGRADED)
        )

        return ScenarioResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            primary_result=primary_result,
            backup_result=backup_result,
            both_unavailable=both_unavailable,
            joint_degraded=joint_degraded,
            component_states=component_states,
            active_failed_components=sorted(list(active_failed_components)),
            assumptions=sorted(scenario.assumptions),
        )

    def _evaluate_component_state(
        self,
        component_id: str,
        current_states: Dict[str, ComponentState],
    ) -> Tuple[ComponentState, bool, str, List[str], DependencyRule]:
        """
        Evaluate component state based on dependencies and groups.
        Returns: (state, is_degraded, reason, failed_dep_ids, dominant_rule)
        """
        # Collect groups
        groups = self.graph.groups_by_dependent.get(component_id, [])
        grouped_targets: Set[str] = set()
        for g in groups:
            grouped_targets.update(g.member_target_ids)

        # Collect standalone dependencies (outgoing edges u -> v not in any group)
        standalone_deps = []
        for target_id in self.graph.get_required_dependencies(component_id):
            edge = (component_id, target_id)
            dep = self.graph.dependencies_by_edge.get(edge)
            if dep and dep.group_id is None:
                standalone_deps.append(dep)

        mandatory_failed = False
        mandatory_unknown = False
        optional_failed = False
        optional_unknown = False
        failed_dependencies: List[str] = []
        unknown_dependencies: List[str] = []
        dominant_rule = DependencyRule.ALL

        # Evaluate groups first
        for g in sorted(groups, key=lambda x: x.id):
            g_rule = g.rule
            members = sorted(g.member_target_ids)
            member_states = [current_states.get(m, ComponentState.UNKNOWN) for m in members]

            if g_rule == DependencyRule.ALL:
                # Down if any member Down; Up if all Up; otherwise Unknown
                down_members = [m for m in members if current_states.get(m) == ComponentState.DOWN]
                unknown_members = [m for m in members if current_states.get(m) == ComponentState.UNKNOWN]
                if down_members:
                    mandatory_failed = True
                    failed_dependencies.extend(down_members)
                    dominant_rule = DependencyRule.ALL
                elif unknown_members:
                    mandatory_unknown = True
                    unknown_dependencies.extend(unknown_members)
            elif g_rule == DependencyRule.ANY:
                # Up if any member Up; Down if all Down; otherwise Unknown
                up_members = [m for m in members if current_states.get(m) == ComponentState.UP]
                down_members = [m for m in members if current_states.get(m) == ComponentState.DOWN]
                unknown_members = [m for m in members if current_states.get(m) == ComponentState.UNKNOWN]

                if up_members:
                    # Satisfied
                    pass
                elif len(down_members) == len(members) and len(members) > 0:
                    # All alternatives Down
                    mandatory_failed = True
                    failed_dependencies.extend(down_members)
                    dominant_rule = DependencyRule.ANY
                else:
                    mandatory_unknown = True
                    unknown_dependencies.extend(unknown_members)
            elif g_rule == DependencyRule.OPTIONAL:
                # Member Down yields Degraded, not Unavailable
                down_members = [m for m in members if current_states.get(m) == ComponentState.DOWN]
                unknown_members = [m for m in members if current_states.get(m) == ComponentState.UNKNOWN]
                if down_members:
                    optional_failed = True
                    failed_dependencies.extend(down_members)
                elif unknown_members:
                    optional_unknown = True
            elif g_rule == DependencyRule.UNKNOWN:
                mandatory_unknown = True
                unknown_dependencies.extend(members)

        # Evaluate standalone dependencies
        for dep in sorted(standalone_deps, key=lambda d: d.id):
            t_state = current_states.get(dep.target_component_id, ComponentState.UNKNOWN)
            r = dep.rule

            if r == DependencyRule.ALL:
                if t_state == ComponentState.DOWN:
                    mandatory_failed = True
                    failed_dependencies.append(dep.target_component_id)
                    dominant_rule = DependencyRule.ALL
                elif t_state == ComponentState.UNKNOWN:
                    mandatory_unknown = True
                    unknown_dependencies.append(dep.target_component_id)
            elif r == DependencyRule.ANY:
                # Single ANY behaves like ALL for 1 item
                if t_state == ComponentState.DOWN:
                    mandatory_failed = True
                    failed_dependencies.append(dep.target_component_id)
                    dominant_rule = DependencyRule.ANY
                elif t_state == ComponentState.UNKNOWN:
                    mandatory_unknown = True
                    unknown_dependencies.append(dep.target_component_id)
            elif r == DependencyRule.OPTIONAL:
                if t_state == ComponentState.DOWN:
                    optional_failed = True
                    failed_dependencies.append(dep.target_component_id)
                elif t_state == ComponentState.UNKNOWN:
                    optional_unknown = True
            elif r == DependencyRule.UNKNOWN:
                mandatory_unknown = True
                unknown_dependencies.append(dep.target_component_id)

        # Combine results with strict rules:
        # A failed mandatory dependency establishes Unavailable even if other relationships are unknown.
        if mandatory_failed:
            reason = f"Mandatory upstream dependency failed: {', '.join(sorted(set(failed_dependencies)))}"
            return ComponentState.DOWN, False, reason, sorted(set(failed_dependencies)), dominant_rule

        # If unknown behavior could change the result, report Unknown/Indeterminate
        if mandatory_unknown:
            reason = f"Undocumented or unknown behavior in upstream dependencies: {', '.join(sorted(set(unknown_dependencies)))}"
            return ComponentState.UNKNOWN, False, reason, sorted(set(unknown_dependencies)), DependencyRule.UNKNOWN

        # If mandatory is intact, check optional degradation
        if optional_failed:
            reason = f"Operational but degraded due to optional component failure: {', '.join(sorted(set(failed_dependencies)))}"
            return ComponentState.UP, True, reason, sorted(set(failed_dependencies)), DependencyRule.OPTIONAL

        return ComponentState.UP, False, "All required dependencies operational", [], DependencyRule.ALL

    def _evaluate_arrangement(
        self,
        name: str,
        root_id: str,
        states: Dict[str, ComponentState],
        degraded_set: Set[str],
        causal_reasons: Dict[str, Tuple[str, List[str], DependencyRule]],
        active_failed_components: Set[str],
    ) -> ArrangementResult:
        """Evaluate arrangement outcome (AVAILABLE, DEGRADED, UNAVAILABLE, INDETERMINATE) and trace causal path."""
        root_state = states.get(root_id, ComponentState.UNKNOWN)

        # Check if root or any reachable upstream mandatory node failed
        if root_state == ComponentState.DOWN:
            outcome = ServiceOutcome.UNAVAILABLE
            causal_path, causal_steps = self._build_causal_path(root_id, states, causal_reasons, active_failed_components)
            primary_reason = f"Arrangement {name} is UNAVAILABLE because root component '{root_id}' is DOWN."
            if len(causal_path) > 1:
                primary_reason += f" Root failure propagated from upstream: {' -> '.join(causal_path)}"
        elif root_state == ComponentState.UNKNOWN:
            outcome = ServiceOutcome.INDETERMINATE
            causal_path, causal_steps = self._build_causal_path(root_id, states, causal_reasons, active_failed_components)
            primary_reason = f"Arrangement {name} outcome is INDETERMINATE because upstream dependencies contain UNKNOWN behavior."
        else:
            # Root is UP. Check if any upstream component in its operational path is degraded
            upstream_nodes = self.graph.get_upstream_components(root_id)
            degraded_upstream = [n for n in upstream_nodes if n in degraded_set or (states.get(n) == ComponentState.DOWN and self._is_only_optional(root_id, n))]

            if degraded_upstream or root_id in degraded_set:
                outcome = ServiceOutcome.DEGRADED
                causal_path = [root_id] + sorted(degraded_upstream)
                causal_steps = [
                    CausalStep(
                        component_id=root_id,
                        component_name=self.graph.get_component(root_id).name if self.graph.get_component(root_id) else root_id,
                        state=ComponentState.UP,
                        rule=DependencyRule.OPTIONAL,
                        reason="Primary flow functional, but non-critical optional dependencies are degraded.",
                        failed_dependencies=sorted(degraded_upstream),
                    )
                ]
                primary_reason = f"Arrangement {name} is DEGRADED. Core dependencies are UP, but optional components have failed: {', '.join(sorted(degraded_upstream))}"
            else:
                outcome = ServiceOutcome.AVAILABLE
                causal_path = [root_id]
                causal_steps = [
                    CausalStep(
                        component_id=root_id,
                        component_name=self.graph.get_component(root_id).name if self.graph.get_component(root_id) else root_id,
                        state=ComponentState.UP,
                        rule=DependencyRule.ALL,
                        reason="All required upstream dependencies are confirmed UP.",
                        failed_dependencies=[],
                    )
                ]
                primary_reason = f"Arrangement {name} is AVAILABLE. All required dependencies verified UP."

        return ArrangementResult(
            arrangement_name=name,
            root_component_id=root_id,
            outcome=outcome,
            causal_path=causal_path,
            causal_steps=causal_steps,
            primary_failure_reason=primary_reason,
        )

    def _is_only_optional(self, root_id: str, target_id: str) -> bool:
        """Check if target_id connects to root_id only via OPTIONAL relationships."""
        paths = self.graph.find_all_paths_to_target(root_id, target_id)
        if not paths:
            return False
        for path in paths:
            # Check edges along path
            is_optional_path = False
            for i in range(len(path) - 1):
                edge = (path[i], path[i + 1])
                dep = self.graph.dependencies_by_edge.get(edge)
                if dep and dep.rule == DependencyRule.OPTIONAL:
                    is_optional_path = True
                    break
            if not is_optional_path:
                return False
        return True

    def _build_causal_path(
        self,
        root_id: str,
        states: Dict[str, ComponentState],
        causal_reasons: Dict[str, Tuple[str, List[str], DependencyRule]],
        active_failed_components: Set[str],
    ) -> Tuple[List[str], List[CausalStep]]:
        """Trace deterministic causal failure path from root down to origin fault(s)."""
        visited: Set[str] = set()
        path: List[str] = []
        steps: List[CausalStep] = []

        curr = root_id
        while curr and curr not in visited:
            visited.add(curr)
            path.append(curr)

            reason, failed_deps, rule = causal_reasons.get(
                curr, ("Component failed", [], DependencyRule.ALL)
            )

            comp = self.graph.get_component(curr)
            comp_name = comp.name if comp else curr

            steps.append(
                CausalStep(
                    component_id=curr,
                    component_name=comp_name,
                    state=states.get(curr, ComponentState.UNKNOWN),
                    rule=rule,
                    reason=reason,
                    failed_dependencies=sorted(failed_deps),
                )
            )

            # If curr is an active root-cause fault, we reached the origin!
            if curr in active_failed_components or not failed_deps:
                break

            # Choose the next failed dependency deterministically (first alphabetically)
            # Prioritize one that is active root fault if present
            next_step = None
            for fd in sorted(failed_deps):
                if fd in active_failed_components:
                    next_step = fd
                    break
            if not next_step and failed_deps:
                next_step = sorted(failed_deps)[0]

            curr = next_step

        return path, steps
