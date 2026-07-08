import torch
import torch.nn as nn
import numpy as np
from typing import List, Tuple, Optional, Dict
from fractions import Fraction
import struct
import heapq
from collections import defaultdict


class NullSpaceCascadeCompressor:
    """
    Cascades null space elimination across all layers.

    For each consecutive pair (W_l, W_next):

      1. Compute SVD of W_next (in float64 for stability) and detect rank.
      2. Build V_row (rank × in_next) — the orthonormal row-space basis of W_next.
      3. Compress:
             W_l_compact    = V_row    @ W_l     (rank × in_l)
             W_next_compact = W_next   @ V_row.T (out_next × rank)
      4. The composed product is preserved up to the discarded singular values:
             W_next_compact @ W_l_compact
           = W_next @ (V_row.T @ V_row) @ W_l
           = W_next @ P_row             @ W_l
           ≈ W_next @ W_l
         Approximation error ≤ max_discarded_singular_value × ‖W_l‖.
         When rank_tol is at or below machine precision this is exact.

    Verification threshold
    ----------------------
    The lossless assertion uses a *scale-aware* bound so that it is tight
    regardless of the magnitude of the weight matrices:

        error < rank_tol × ‖W_next‖ × ‖W_l‖ × sqrt(shared_dim)  +  float64_eps_floor

    This bound comes directly from the Eckart–Young theorem: the truncation
    error equals ‖W_next @ (I − P_row) @ W_l‖_F ≤ σ_{rank+1}(W_next) × ‖W_l‖_F,
    and σ_{rank+1} ≤ rank_tol by construction.
    """

    def __init__(self, rank_tol: float = 1e-10):
        self.rank_tol   = rank_tol
        self.projections: List[Dict] = []

    # ------------------------------------------------------------------
    # Internal: SVD in float64 on CPU
    # ------------------------------------------------------------------

    def _svd_f64(
        self,
        W: torch.Tensor,
        full_matrices: bool = True,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        W64 = W.detach().to(dtype=torch.float64, device="cpu")
        U, S, Vh = torch.linalg.svd(W64, full_matrices=full_matrices)
        return U, S, Vh     # all float64, CPU

    # ------------------------------------------------------------------
    # Build the row-space basis of W_next
    # ------------------------------------------------------------------

    def _row_space_basis(
        self,
        W_next: torch.Tensor,   # (out_next, in_next)
    ) -> Tuple[torch.Tensor, int]:
        """
        Return V_row (rank × in_next, float64 CPU) and the numerical rank.

        V_row rows are the right-singular vectors of W_next whose singular
        values exceed rank_tol.  They span the subspace of R^{in_next} that
        W_next can "see"; everything orthogonal to this is W_next's null space.
        """
        _, S, Vh = self._svd_f64(W_next)
        rank  = int((S > self.rank_tol).sum().item())
        V_row = Vh[:rank, :]          # (rank, in_next)  float64
        return V_row, rank

    # ------------------------------------------------------------------
    # Layer-pair compression
    # ------------------------------------------------------------------

    def compress_layer_pair(
        self,
        W_l:    torch.Tensor,   # (out_l,    in_l)      e.g. (64, 32)
        W_next: torch.Tensor,   # (out_next, in_next)   e.g. (16, 64)
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Compress (W_l, W_next) by eliminating directions W_next ignores.

        The compressed pair satisfies (up to rank_tol accuracy):
            W_next_compact @ W_l_compact  ≈  W_next @ W_l

        Returns
        -------
        W_l_compact    : (rank, in_l)      — in original dtype/device
        W_next_compact : (out_next, rank)  — in original dtype/device
        V_row          : (rank, in_next)   — float64, kept for reconstruction
        """
        if W_l.shape[0] != W_next.shape[1]:
            raise ValueError(
                f"Shape mismatch: W_l outputs {W_l.shape[0]} dims "
                f"but W_next expects {W_next.shape[1]} inputs."
            )

        orig_dtype  = W_l.dtype
        orig_device = W_l.device

        # Work entirely in float64 to isolate floating-point noise from the
        # genuine approximation introduced by rank truncation.
        W_l_64    = W_l.detach().to(dtype=torch.float64, device="cpu")
        W_next_64 = W_next.detach().to(dtype=torch.float64, device="cpu")

        V_row, rank = self._row_space_basis(W_next)   # (rank, in_next) f64

        W_l_compact_64    = V_row     @ W_l_64        # (rank,     in_l)
        W_next_compact_64 = W_next_64 @ V_row.T       # (out_next, rank)

        # ── Lossless verification ────────────────────────────────────────
        # Error = ‖W_next @ (I − P) @ W_l‖  ≤  σ_{rank+1}(W_next) × ‖W_l‖
        # Upper-bound from Eckart–Young: σ_{rank+1} ≤ rank_tol by construction,
        # so the scale-aware tolerance is:
        #   tol = rank_tol × ‖W_next‖ × ‖W_l‖ × sqrt(shared_dim) + 1e-10
        # The 1e-10 floor covers float64 round-off when rank_tol is tiny.
        shared_dim = W_l_64.shape[0]
        scale_tol  = (
            self.rank_tol
            * float(torch.norm(W_next_64))
            * float(torch.norm(W_l_64))
            * (shared_dim ** 0.5)
            + 1e-10
        )

        orig_prod    = W_next_64           @ W_l_64
        compact_prod = W_next_compact_64   @ W_l_compact_64
        err = float(torch.norm(orig_prod - compact_prod))

        assert err <= scale_tol, (
            f"Null space compression exceeded expected error bound.\n"
            f"  error     = {err:.3e}\n"
            f"  tolerance = {scale_tol:.3e}  "
            f"(rank_tol={self.rank_tol} × ‖W_next‖ × ‖W_l‖ × √{shared_dim})\n"
            f"  W_l {tuple(W_l.shape)}, W_next {tuple(W_next.shape)}, rank={rank}\n"
            f"  This should never happen — file a bug."
        )

        # Cast back to original dtype + device for use in the model
        W_l_compact    = W_l_compact_64.to(dtype=orig_dtype, device=orig_device)
        W_next_compact = W_next_compact_64.to(dtype=orig_dtype, device=orig_device)

        self.projections.append({
            "V_row":           V_row,            # float64, for reconstruction
            "rank":            rank,
            "original_shape":  W_l.shape,
            "original_dtype":  orig_dtype,
            "original_device": orig_device,
            "error":           err,
        })

        return W_l_compact, W_next_compact, V_row

    # ------------------------------------------------------------------
    # Cascade over all layers
    # ------------------------------------------------------------------

    def cascade_compress(
        self,
        layers: List[torch.Tensor],
    ) -> List[torch.Tensor]:
        """
        Apply null space elimination cascading backward through all layers.

        Processes pairs (W_i, W_{i+1}) from the last pair to the first.
        Each step consistently shrinks W_curr's output dim and W_next's input
        dim to `rank`, so subsequent backward iterations see compatible shapes.

        Parameters
        ----------
        layers : list of 2-D tensors (out_i, in_i)  — PyTorch weight convention

        Returns
        -------
        compressed : list of 2-D tensors with reduced inner dimensions
        """
        compressed = list(layers)

        for i in range(len(compressed) - 2, -1, -1):
            W_curr = compressed[i]        # (out_curr, in_curr)
            W_next = compressed[i + 1]    # (out_next, in_next)

            # Skip non-matrix tensors (e.g. 1-D bias vectors)
            if W_curr.dim() != 2 or W_next.dim() != 2:
                continue

            # Compatibility: out_curr must equal in_next
            if W_curr.shape[0] != W_next.shape[1]:
                continue

            W_curr_c, W_next_c, _ = self.compress_layer_pair(W_curr, W_next)

            # W_curr_c : (rank, in_curr)    output dim reduced to rank
            # W_next_c : (out_next, rank)   input  dim reduced to rank
            compressed[i]     = W_curr_c
            compressed[i + 1] = W_next_c

        return compressed