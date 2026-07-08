# Causal Functor Core

## Scope

The Causal Functor Core is the next JULIUS layer after STRATUM and CSIE:

STRATUM -> CSIE -> CAUSAL FUNCTOR -> KRONOS -> AXIOM

This implementation is intentionally limited to the requested core. It does not implement KRONOS, AXIOM, APEX path integrals, self-modeling, model scaling, compression, or new storage systems.

## Repository Placement

The active JULIUS backend package is `backend`, so the service lives at:

`backend/services/causal_functor/`

This follows the existing service architecture instead of creating a new top-level package.

## Inputs

- STRATUM profiles from the existing profile store.
- CSIE runtime classifications from the existing CSIE service.
- Workflow result dictionaries supplied by existing workflow callers.
- Cognitive memory facts supplied by existing memory callers.

## Outputs

- `CausalGraph`
- Causal chains
- Inference results
- Human-readable explanations
- Diagnostics reports

## API Integration

The additive diagnostics endpoint is:

`GET /api/stratum/causal-functor/diagnostics`

It returns graph statistics, morphism statistics, inference metrics, validation reports, sample inferences, and an exported causal model.

## Design Notes

The Causal Functor Core imports upstream outputs as evidence. It does not re-run STRATUM identity resolution and does not recompute CSIE sheaf or Cech semantics. This preserves the dependency chain and avoids duplicated functionality.
