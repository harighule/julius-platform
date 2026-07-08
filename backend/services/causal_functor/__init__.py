"""Causal Functor core services.

This package sits after STRATUM and CSIE in the JULIUS manager chain:
STRATUM -> CSIE -> CAUSAL FUNCTOR -> KRONOS -> AXIOM.
"""

from .causal_models import build_causal_model, export_causal_model, update_causal_model
from .causal_objects import create_causal_object, link_objects, validate_object
from .diagnostics import (
    build_live_causal_graph,
    get_causal_functor_diagnostics,
    get_causal_functor_graph,
    get_causal_functor_inference,
    graph_statistics,
    inference_metrics,
    morphism_statistics,
    validation_reports,
)
from .inference import (
    backward_inference,
    causal_chain,
    explanation_generation,
    forward_inference,
)
from .models import (
    CausalEvidence,
    CausalGraph,
    CausalInferenceResult,
    CausalObject,
    CausalRelation,
)
from .morphisms import (
    IdentityMorphism,
    KMorphism,
    MorphismComposition,
    MorphismValidation,
)

__all__ = [
    "CausalEvidence",
    "CausalGraph",
    "CausalInferenceResult",
    "CausalObject",
    "CausalRelation",
    "IdentityMorphism",
    "KMorphism",
    "MorphismComposition",
    "MorphismValidation",
    "backward_inference",
    "build_live_causal_graph",
    "build_causal_model",
    "causal_chain",
    "create_causal_object",
    "explanation_generation",
    "export_causal_model",
    "forward_inference",
    "get_causal_functor_diagnostics",
    "get_causal_functor_graph",
    "get_causal_functor_inference",
    "graph_statistics",
    "inference_metrics",
    "link_objects",
    "morphism_statistics",
    "update_causal_model",
    "validate_object",
    "validation_reports",
]
