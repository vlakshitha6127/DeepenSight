"""Byte-identical serialization, canonical hashing, and historical assessment persistence."""

from __future__ import annotations
import json
import hashlib
from typing import Dict, Any, Union
from pydantic import BaseModel

import depsight
from depsight.engine.models import ArchitectureModel, AssessmentReport


def serialize_canonical_json(data: Union[BaseModel, Dict[str, Any]]) -> str:
    """
    Produce byte-identical canonical JSON string.
    Keys are recursively sorted; indentation and separators are fixed.
    """
    if isinstance(data, BaseModel):
        raw_dict = data.model_dump(mode="json")
    else:
        raw_dict = data

    return json.dumps(
        raw_dict,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        separators=(",", ": "),
    )


def compute_sha256(canonical_content: str) -> str:
    """Calculate SHA-256 digest of canonical serialized content."""
    return hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()


def verify_reproducibility(
    report_a: AssessmentReport,
    report_b: AssessmentReport,
) -> bool:
    """Check if two reports have identical canonical representation."""
    json_a = serialize_canonical_json(report_a)
    json_b = serialize_canonical_json(report_b)
    return json_a == json_b and compute_sha256(json_a) == compute_sha256(json_b)
