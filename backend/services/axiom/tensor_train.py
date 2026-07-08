
import torch
import torch.nn as nn
import numpy as np
from typing import List, Tuple, Optional, Dict
from fractions import Fraction
import struct
import heapq
from collections import defaultdict

class TensorTrainDecomposer:
    """
    Decomposes weight tensors into Tensor Train format.

    A weight tensor W of shape (n_1, n_2, ..., n_d) is represented as:
      W[i_1, i_2, ..., i_d] = A_1[i_1] @ A_2[i_2] @ ... @ A_d[i_d]

    where A_k[i_k] are matrices of shape (r_{k-1}, r_k).
    The bond dimensions r_k control the compression ratio.

    For EXACT decomposition: choose r_k = exact rank of unfolding matrix.
    This is lossless — the Tensor Train exactly represents W.

    For transformer weight matrices W ∈ ℝ^{d_model × d_model}:
      Reshape to (p, p, p, p, ...) where p = d_model^{1/d}
      Apply TT-SVD with EXACT rank (no truncation)
      Result: d cores of size (r, p, r) instead of one (d_model, d_model)
    """

    def __init__(self, exact: bool = True, max_rank: Optional[int] = None):
        self.exact = exact
        self.max_rank = max_rank

    def tt_svd(
        self,
        W: torch.Tensor,
        shape: Optional[Tuple] = None
    ) -> List[torch.Tensor]:
        """
        TT-SVD algorithm (Oseledets 2011) with exact rank.

        Args:
          W: weight tensor of arbitrary shape
          shape: target shape for reshaping (default: find natural factorization)

        Returns:
          cores: list of TT-core tensors
        """
        if shape is None:
            shape = self._find_balanced_shape(W)

        W_reshaped = W.reshape(shape)
        d = len(shape)
        cores = []

        C = W_reshaped.reshape(shape[0], -1)  # Unfold
        r_prev = 1

        for k in range(d - 1):
            n_k = shape[k]
            # Reshape for SVD
            C = C.reshape(r_prev * n_k, -1)

            # SVD with exact rank
            U, S, Vh = torch.linalg.svd(C, full_matrices=False)

            if self.exact:
                # Keep ALL non-zero singular values (exact rank)
                rank = (S > 1e-12).sum().item()
            else:
                rank = min(self.max_rank, len(S)) if self.max_rank else len(S)

            U = U[:, :rank]
            S = S[:rank]
            Vh = Vh[:rank, :]

            # Core k: shape (r_prev, n_k, rank)
            core = U.reshape(r_prev, n_k, rank)
            cores.append(core)

            # Continue with S @ Vh for next iteration
            C = torch.diag(S) @ Vh
            r_prev = rank

        # Last core
        cores.append(C.reshape(r_prev, shape[-1], 1))

        return cores

    def _find_balanced_shape(self, W: torch.Tensor) -> Tuple:
        """Find a balanced reshaping of W for optimal TT decomposition."""
        total_elements = W.numel()
        # Find prime factorization and balance
        # Target: roughly equal-sized dimensions
        d = max(2, int(np.log2(total_elements) / 4))  # target ~4 bits per dim
        p = int(round(total_elements ** (1.0 / d)))
        # Adjust p to make it exactly divisible
        while total_elements % (p ** d) != 0:
            p += 1
            if p > 64:
                d -= 1
                p = int(round(total_elements ** (1.0 / d)))
        return tuple([p] * d)

    def reconstruct(self, cores: List[torch.Tensor]) -> torch.Tensor:
        """
        Reconstruct weight matrix from TT-cores.
        Exact reconstruction — no approximation.
        """
        result = cores[0].squeeze(0)  # (n_1, r_1)
        for core in cores[1:]:
            # core: (r_k, n_k, r_{k+1})
            r_prev = result.shape[-1]
            n_k = core.shape[1]
            r_next = core.shape[2]
            # Contract: (... , r_prev) @ (r_prev, n_k, r_next) -> (... , n_k, r_next)
            result = torch.tensordot(result, core, dims=([[-1], [0]]))
        return result.squeeze(-1)

    def compression_ratio(self, original: torch.Tensor, cores: List[torch.Tensor]) -> float:
        original_params = original.numel()
        compressed_params = sum(c.numel() for c in cores)
        return original_params / compressed_params

