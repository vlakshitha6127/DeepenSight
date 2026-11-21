"""Propagation engine implementing three-valued logic, monotone fixed-point iteration, and causal path tracing.

========================================================================================
FORMAL FIXED-POINT SEMANTICS & TERMINATION PROOF (CYCLES)
========================================================================================
1. State Space and Complete Semi-Lattice:
   Let V be the finite set of components with |V| = n.
   Define the complete finite semi-lattice L = (S, <=) on S = {UP, UNKNOWN, DOWN}
   under the failure-severity / information-loss partial order:
       UP < UNKNOWN < DOWN
   with join operator:
       x v y = max(x, y) under the partial order.
   The product lattice L^n = S^n has finite height H = 2 * n.

2. State Transition Operator:
   Define T: S^n -> S^n where for each component c in V:
       T(s)_c = s_c v g_c(s)
   where g_c(s) evaluates c's incoming dependency rules over state vector s.
   Active root faults are clamped at DOWN (s_c = DOWN).

3. Monotonicity:
   For all rules R in {ALL, ANY, OPTIONAL, UNKNOWN}:
   If s <= s' elementwise, then g_c(s) <= g_c(s').
   - For ALL: A degradation of any child from UP to UNKNOWN or DOWN monotonically
     increases the severity from UP -> UNKNOWN -> DOWN.
   - For ANY: A degradation of alternatives reduces available operational paths. If all
     alternatives become DOWN, g_c(s) reaches DOWN.
   Thus, T is monotone: s <= s' implies T(s) <= T(s').

4. Termination and Correctness (Knaster-Tarski / Kleene Fixed-Point Theorem):
   Beginning at initial state s^(0) (where active scenario faults are DOWN and unfailed
   nodes are UP), the sequence:
       s^(0) <= s^(1) <= s^(2) <= ... <= s^(k)
   forms a monotonically non-decreasing chain in a lattice of finite height 2n.
   Therefore, there exists a k <= 2n such that s^(k) = s^(k+1) = s*, the unique
   least fixed point satisfying T(s*) = s*.
   Termination is guaranteed by the finite height of the lattice, NOT by an arbitrary
   iteration cap. The cap 2n is the theoretical upper bound on chain length.
"""

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

# Partial order rank on S: UP (0) < UNKNOWN (1) < DOWN (2)
_LATTICE_RANK: Dict[ComponentState, int] = {
    ComponentState.UP: 0,
    ComponentState.UNKNOWN: 1,
    ComponentState.DOWN: 2,
}

_RANK_TO_STATE: Dict[int, ComponentState] = {
    0: ComponentState.UP,
    1: ComponentState.UNKNOWN,
    2: ComponentState.DOWN,
}


def lattice_join(a: ComponentState, b: ComponentState) -> ComponentState:
    """Least upper bound (join) in the complete semi-lattice UP < UNKNOWN < DOWN."""
    rank = max(_LATTICE_RANK[a], _LATTICE_RANK[b])
    return _RANK_TO_STATE[rank]


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

        for cid in scenario.failed_component_ids:
            if cid in self.graph.graph:
                active_failed_components.add(cid)

        if scenario.failed_failure_domain_ids:
            failed_domains_set = set(scenario.failed_failure_domain_ids)
            for cid in self.graph.node_ids:
                comp = self.graph.get_component(cid)
                if comp and any(fd in failed_domains_set for fd in comp.failure_domains):
                    active_failed_components.add(cid)

        # Step 2: Initialize component state vector s^(0)
        component_states: Dict[str, ComponentState] = {}
        for cid in self.graph.node_ids:
            if cid in active_failed_components:
                component_states[cid] = ComponentState.DOWN
            elif cid in scenario.assumed_behavior:
                component_states[cid] = scenario.assumed_behavior[cid]
            else:
                component_states[cid] = ComponentState.UP

        # Causal explanations
        causal_reasons: Dict[str, Tuple[str, List[str], DependencyRule]] = {}
        for cid in active_failed_components:
            causal_reasons[cid] = ("Directly triggered scenario fault / failure domain outage", [], DependencyRule.ALL)

        # Step 3: Fixed-point monotone iteration (Kleene iteration)
        # Lattice height is 2 * n where n = |V|
        sorted_nodes = self.graph.node_ids
        theoretical_bound = max(1, 2 * len(sorted_nodes))
        degraded_components: Set[str] = set()

        for iteration in range(1, theoretical_bound + 1):
            changed = False

            for cid in sorted_nodes:
                if cid in active_failed_components:
                    continue

                curr_state = component_states[cid]
                # Compute g_c(s)
                eval_state, is_degraded, reason, failed_deps, rule_used = self._evaluate_component_state(
                    cid, component_states
                )

                if is_degraded:
                    degraded_components.add(cid)
                elif cid in degraded_components and not is_degraded:
                    degraded_components.remove(cid)

                # Monotone update: T(s)_c = s_c v g_c(s)
                new_state = lattice_join(curr_state, eval_state)

                if new_state != curr_state:
                    component_states[cid] = new_state
                    causal_reasons[cid] = (reason, failed_deps, rule_used)
                    changed = True

            if not changed:
                # Least fixed point s* reached!
                break

        # Step 4: Evaluate arrangement outcomes (Primary & Backup) independently
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
        Evaluate node-level state g_c(s) based on incoming dependencies and groups.
        Independent of arrangement-level service outcomes.
        Returns: (state, is_degraded, reason, failed_dep_ids, dominant_rule)
        """
        groups = self.graph.groups_by_dependent.get(component_id, [])
        grouped_targets: Set[str] = set()
        for g in groups:
            grouped_targets.update(g.member_target_ids)

        standalone_deps = []
        for target_id in self.graph.get_required_dependencies(component_id):
            edge = (component_id, target_id)
            dep = self.graph.dependencies_by_edge.get(edge)
            if dep and dep.group_id is None:
                standalone_deps.append(dep)

        mandatory_failed = False
        mandatory_unknown = False
        optional_failed = False
        failed_dependencies: List[str] = []
        unknown_dependencies: List[str] = []
        dominant_rule = DependencyRule.ALL

        # Evaluate groups
        for g in sorted(groups, key=lambda x: x.id):
            members = sorted(g.member_target_ids)
            g_rule = g.rule

            if g_rule == DependencyRule.ALL:
                down_m = [m for m in members if current_states.get(m) == ComponentState.DOWN]
                unknown_m = [m for m in members if current_states.get(m) == ComponentState.UNKNOWN]
                if down_m:
                    mandatory_failed = True
                    failed_dependencies.extend(down_m)
                    dominant_rule = DependencyRule.ALL
                elif unknown_m:
                    mandatory_unknown = True
                    unknown_dependencies.extend(unknown_m)
            elif g_rule == DependencyRule.ANY:
                up_m = [m for m in members if current_states.get(m) == ComponentState.UP]
                down_m = [m for m in members if current_states.get(m) == ComponentState.DOWN]
                unknown_m = [m for m in members if current_states.get(m) == ComponentState.UNKNOWN]

                if up_m:
                    pass
                elif len(down_m) == len(members) and len(members) > 0:
                    mandatory_failed = True
                    failed_dependencies.extend(down_m)
                    dominant_rule = DependencyRule.ANY
                else:
                    mandatory_unknown = True
                    unknown_dependencies.extend(unknown_m)
            elif g_rule == DependencyRule.OPTIONAL:
                down_m = [m for m in members if current_states.get(m) == ComponentState.DOWN]
                if down_m:
                    optional_failed = True
                    failed_dependencies.extend(down_m)
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
            elif r == DependencyRule.UNKNOWN:
                mandatory_unknown = True
                unknown_dependencies.append(dep.target_component_id)

        # Semantics:
        # Mandatory failure overrides any unknowns
        if mandatory_failed:
            reason = f"Mandatory upstream dependency failed: {', '.join(sorted(set(failed_dependencies)))}"
            return ComponentState.DOWN, False, reason, sorted(set(failed_dependencies)), dominant_rule

        # If mandatory is not failed, but has unknown dependencies
        if mandatory_unknown:
            reason = f"Undocumented or unknown upstream behavior: {', '.join(sorted(set(unknown_dependencies)))}"
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
        """
        Evaluate arrangement-level outcome independently from component states:
        - UNAVAILABLE if root is DOWN.
        - INDETERMINATE if root is UNKNOWN.
        - DEGRADED if root is UP and an optional dependency in its active path failed.
        - AVAILABLE if root is UP and all required/optional dependencies are UP.
        """
        root_state = states.get(root_id, ComponentState.UNKNOWN)

        if root_state == ComponentState.DOWN:
            outcome = ServiceOutcome.UNAVAILABLE
            causal_path, causal_steps = self._build_causal_path(root_id, states, causal_reasons, active_failed_components)
            primary_reason = f"Arrangement '{name}' is UNAVAILABLE because root component '{root_id}' is DOWN."
            if len(causal_path) > 1:
                primary_reason += f" Root failure propagated from upstream: {' -> '.join(causal_path)}"
        elif root_state == ComponentState.UNKNOWN:
            outcome = ServiceOutcome.INDETERMINATE
            causal_path, causal_steps = self._build_causal_path(root_id, states, causal_reasons, active_failed_components)
            primary_reason = f"Arrangement '{name}' outcome is INDETERMINATE because upstream dependencies contain UNKNOWN behavior."
        else:
            # Root is UP. Inspect whether any component in its operational tree is degraded
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
                primary_reason = f"Arrangement '{name}' is DEGRADED. Core dependencies are UP, but optional components have failed: {', '.join(sorted(degraded_upstream))}"
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
                primary_reason = f"Arrangement '{name}' is AVAILABLE. All required dependencies verified UP."

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

            if curr in active_failed_components or not failed_deps:
                break

            # Deterministic next step (prefer active root fault, then lexicographical)
            next_step = None
            for fd in sorted(failed_deps):
                if fd in active_failed_components:
                    next_step = fd
                    break
            if not next_step and failed_deps:
                next_step = sorted(failed_deps)[0]

            curr = next_step

        return path, steps
