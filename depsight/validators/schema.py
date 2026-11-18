"""Schema validation and file loading for DepenSight architecture and scenario definitions."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Union, Dict, Any, List
import yaml
from pydantic import ValidationError

from depsight.engine.models import ArchitectureModel, Scenario


class SchemaValidationError(Exception):
    """Raised when architecture or scenario schema fails structural or referential validation."""
    def __init__(self, message: str, errors: List[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


def load_yaml_or_json(path: Union[str, Path]) -> Dict[str, Any]:
    """Deterministically parse a YAML or JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            raise SchemaValidationError(f"Expected root object in {p}, got {type(data).__name__}")
        return data
    except yaml.YAMLError as e:
        raise SchemaValidationError(f"Failed to parse YAML in {p}: {e}")


def validate_architecture_model(data: Dict[str, Any]) -> ArchitectureModel:
    """Validate raw dictionary against ArchitectureModel schema and referential integrity."""
    try:
        model = ArchitectureModel.model_validate(data)
    except ValidationError as e:
        error_msgs = []
        for err in e.errors():
            loc = " -> ".join(str(x) for x in err["loc"])
            error_msgs.append(f"At {loc}: {err['msg']}")
        raise SchemaValidationError(f"Architecture model validation failed:\n" + "\n".join(error_msgs), error_msgs)

    # Referential integrity checks
    errors: List[str] = []
    provider_ids = {p.id for p in model.providers}
    deployment_ids = {d.id for d in model.deployments}
    failure_domain_ids = {fd.id for fd in model.failure_domains}
    component_ids = {c.id for c in model.components}

    # Verify deployments point to valid providers
    for dep in model.deployments:
        if dep.provider_id not in provider_ids:
            errors.append(f"Deployment '{dep.id}' references unknown provider '{dep.provider_id}'")

    # Verify components point to valid provider/deployment/failure domains
    for comp in model.components:
        if comp.provider_id and comp.provider_id not in provider_ids:
            errors.append(f"Component '{comp.id}' references unknown provider '{comp.provider_id}'")
        if comp.deployment_id and comp.deployment_id not in deployment_ids:
            errors.append(f"Component '{comp.id}' references unknown deployment '{comp.deployment_id}'")
        for fd in comp.failure_domains:
            if fd not in failure_domain_ids:
                errors.append(f"Component '{comp.id}' references unknown failure domain '{fd}'")

    # Verify service roots exist
    if model.service.primary_arrangement.root_component_id not in component_ids:
        errors.append(f"Primary arrangement root '{model.service.primary_arrangement.root_component_id}' not found in components")
    if model.service.backup_arrangement.root_component_id not in component_ids:
        errors.append(f"Backup arrangement root '{model.service.backup_arrangement.root_component_id}' not found in components")

    # Verify dependencies
    for dep in model.dependencies:
        if dep.source_component_id not in component_ids:
            errors.append(f"Dependency '{dep.id}' source component '{dep.source_component_id}' not found")
        if dep.target_component_id not in component_ids:
            errors.append(f"Dependency '{dep.id}' target component '{dep.target_component_id}' not found")

    # Verify dependency groups
    group_ids = {g.id for g in model.dependency_groups}
    for g in model.dependency_groups:
        if g.dependent_component_id not in component_ids:
            errors.append(f"Dependency group '{g.id}' dependent component '{g.dependent_component_id}' not found")
        for member_id in g.member_target_ids:
            if member_id not in component_ids:
                errors.append(f"Dependency group '{g.id}' member target '{member_id}' not found")

    for dep in model.dependencies:
        if dep.group_id and dep.group_id not in group_ids:
            errors.append(f"Dependency '{dep.id}' references unknown group '{dep.group_id}'")

    if errors:
        raise SchemaValidationError(f"Referential integrity validation failed:\n" + "\n".join(errors), errors)

    return model


def validate_scenario(data: Dict[str, Any], model: ArchitectureModel | None = None) -> Scenario:
    """Validate raw scenario data against Scenario schema and optional model reference checks."""
    try:
        scenario = Scenario.model_validate(data)
    except ValidationError as e:
        error_msgs = []
        for err in e.errors():
            loc = " -> ".join(str(x) for x in err["loc"])
            error_msgs.append(f"At {loc}: {err['msg']}")
        raise SchemaValidationError(f"Scenario validation failed:\n" + "\n".join(error_msgs), error_msgs)

    if model:
        errors = []
        comp_ids = {c.id for c in model.components}
        fd_ids = {fd.id for fd in model.failure_domains}

        for cid in scenario.failed_component_ids:
            if cid not in comp_ids:
                errors.append(f"Scenario '{scenario.id}' specifies unknown failed component '{cid}'")

        for fdid in scenario.failed_failure_domain_ids:
            if fdid not in fd_ids:
                errors.append(f"Scenario '{scenario.id}' specifies unknown failed failure domain '{fdid}'")

        if errors:
            raise SchemaValidationError(f"Scenario reference validation failed:\n" + "\n".join(errors), errors)

    return scenario


def load_model_from_file(path: Union[str, Path]) -> ArchitectureModel:
    """Convenience loader from file path."""
    data = load_yaml_or_json(path)
    return validate_architecture_model(data)


def load_scenario_from_file(path: Union[str, Path], model: ArchitectureModel | None = None) -> Scenario:
    """Convenience scenario loader from file path."""
    data = load_yaml_or_json(path)
    return validate_scenario(data, model)
