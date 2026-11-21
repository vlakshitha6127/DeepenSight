"""Byte-identical serialization, canonical hashing, and historical assessment persistence.

Guarantees deterministic serialization by:
- Recursively sorting dictionary keys.
- Applying fixed JSON separators and standard UTF-8 encoding.
- Excluded or normalized volatile metadata (such as execution timestamps) during byte-reproducibility checks.
"""

from __future__ import annotations
import json
import hashlib
from typing import Dict, Any, Union, Optional
from pydantic import BaseModel

from depsight.engine.models import AssessmentReport


def serialize_canonical_json(
    data: Union[BaseModel, Dict[str, Any]],
    exclude_volatile: bool = False,
) -> str:
    """
    Produce byte-identical canonical JSON string.
    Keys are recursively sorted; indentation and separators are fixed.
    If exclude_volatile is True, variable fields (generated_at) are normalized.
    """
    if isinstance(data, BaseModel):
        raw_dict = data.model_dump(mode="json")
    else:
        raw_dict = json.loads(json.dumps(data))

    if exclude_volatile and isinstance(raw_dict, dict):
        if "generated_at" in raw_dict:
            raw_dict["generated_at"] = "STATIC_REPRODUCIBILITY_TIMESTAMP"

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
    ignore_timestamps: bool = True,
) -> bool:
    """Check if two reports have identical canonical representation."""
    json_a = serialize_canonical_json(report_a, exclude_volatile=ignore_timestamps)
    json_b = serialize_canonical_json(report_b, exclude_volatile=ignore_timestamps)
    return json_a == json_b and compute_sha256(json_a) == compute_sha256(json_b)
