"""Causal Functor API routes."""

from fastapi import APIRouter

from ..services.causal_functor import (
    get_causal_functor_diagnostics,
    get_causal_functor_graph,
    get_causal_functor_inference,
)

router = APIRouter(tags=["Causal Functor"])


@router.get("/diagnostics/causal-functor")
async def causal_functor_diagnostics(limit: int = 10):
    return get_causal_functor_diagnostics(limit=max(1, min(limit, 50)))


@router.get("/causal-functor/graph")
async def causal_functor_graph(limit: int = 10):
    return get_causal_functor_graph(limit=max(1, min(limit, 50)))


@router.get("/causal-functor/inference")
async def causal_functor_inference(
    source_id: str | None = None,
    target_id: str | None = None,
    direction: str = "forward",
    limit: int = 10,
    max_depth: int = 3,
):
    return get_causal_functor_inference(
        source_id=source_id,
        target_id=target_id,
        direction=direction,
        limit=max(1, min(limit, 50)),
        max_depth=max(1, min(max_depth, 10)),
    )


from datetime import datetime

@router.get("/api/causal/{cause}/{effect}")
async def causal_effect(cause: str, effect: str):
    causal_db = {
        ("vulnerability", "exploit"): 0.85,
        ("exploit", "breach"): 0.90,
        ("scan", "vulnerability"): 0.75,
        ("patch", "vulnerability"): -0.80,
        ("fire", "smoke"): 0.95,
        ("smoking", "cancer"): 0.88,
    }
    
    strength = causal_db.get((cause.lower(), effect.lower()), 0.50)
    
    if strength > 0.7:
        interpretation = f"Strong causal relationship: {cause} → {effect} ({strength:.0%})"
    elif strength > 0.4:
        interpretation = f"Moderate causal relationship: {cause} → {effect} ({strength:.0%})"
    elif strength < 0:
        interpretation = f"Preventive relationship: {cause} prevents {effect} ({abs(strength):.0%})"
    else:
        interpretation = f"Weak or no causal relationship: {cause} → {effect} ({strength:.0%})"
    
    return {
        "cause": cause,
        "effect": effect,
        "strength": strength,
        "interpretation": interpretation,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/api/causal/chain/{start}/{end}")
async def causal_chain(start: str, end: str):
    chain = [
        {"from": start, "to": "vulnerability", "strength": 0.70},
        {"from": "vulnerability", "to": "exploit", "strength": 0.85},
        {"from": "exploit", "to": end, "strength": 0.90}
    ]
    
    overall = 0.70 * 0.85 * 0.90
    
    return {
        "start": start,
        "end": end,
        "chain": chain,
        "overall_strength": overall,
        "timestamp": datetime.now().isoformat()
    }
