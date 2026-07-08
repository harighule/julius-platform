"""STRATUM OMNIS architecture services.

Exports are intentionally lazy so low-level helpers can be imported by
collectors without triggering blueprint imports that reference the collector.
"""

from __future__ import annotations

from typing import Any


def apply_canonical_resolution(profile: dict[str, Any]) -> dict[str, Any]:
    from .entity_resolution_engine import apply_canonical_resolution as _impl

    return _impl(profile)


def resolve_profile(profile: dict[str, Any]):
    from .entity_resolution_engine import resolve_profile as _impl

    return _impl(profile)


def get_csie_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .csie import get_csie_snapshot as _impl

    return _impl(*args, **kwargs)


def get_feature_store_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .feature_store import get_feature_store_snapshot as _impl

    return _impl(*args, **kwargs)


def get_identity_resolution_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .identity_resolution import get_identity_resolution_snapshot as _impl

    return _impl(*args, **kwargs)


def get_model_hub_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .model_hub import get_model_hub_snapshot as _impl

    return _impl(*args, **kwargs)


def get_oracle_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .oracle import get_oracle_snapshot as _impl

    return _impl(*args, **kwargs)


def get_stratum_blueprint(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .blueprint import get_stratum_blueprint as _impl

    return _impl(*args, **kwargs)


def get_stratum_runtime(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .blueprint import get_stratum_runtime as _impl

    return _impl(*args, **kwargs)


def get_stream_processing_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .stream_processing import get_stream_processing_snapshot as _impl

    return _impl(*args, **kwargs)


__all__ = [
    "apply_canonical_resolution",
    "get_csie_snapshot",
    "get_feature_store_snapshot",
    "get_identity_resolution_snapshot",
    "get_model_hub_snapshot",
    "get_oracle_snapshot",
    "get_stratum_blueprint",
    "get_stratum_runtime",
    "get_stream_processing_snapshot",
    "resolve_profile",
]
