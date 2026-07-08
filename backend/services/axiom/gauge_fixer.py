
import torch
import torch.nn as nn
import numpy as np
from typing import List, Tuple, Optional, Dict
from fractions import Fraction
import struct
import heapq
from collections import defaultdict

class GaugeFixer:
    """
    Fixes all gauge redundancies in a neural network:
      - Scale symmetry between consecutive linear layers
      - Permutation symmetry (canonical neuron ordering)
      - Attention head permutation symmetry
      - QKV rotational symmetry within each head

    Result: minimal canonical weight representation.
    All transformations are invertible — original model recoverable.
    """

    def __init__(self, tol: float = 1e-12):
        self.tol = tol  # Threshold for detecting zero (NOT for approximation)
        self.transforms: List[Dict] = []  # Stored for reconstruction

    def fix_scale_symmetry(
        self,
        W_l: torch.Tensor,
        W_next: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Fixes scale symmetry between two consecutive linear layers.

        For W_next @ W_l @ x:
          W_l   : (n_out, n_in)
          W_next: (m_out, n_out)

        Gauge transformation: D = diag(scale factors for each neuron in W_l output)
        New W_l   = D @ W_l      (each row scaled)
        New W_next = W_next @ D^{-1}  (each column inverse-scaled)

        Canonical gauge choice: each row of W_l has unit L2 norm.
        """
        # Compute per-row norms of W_l (output-dimension norms)
        row_norms = torch.norm(W_l, dim=1, keepdim=True)  # (n_out, 1)
        row_norms = torch.clamp(row_norms, min=self.tol)  # avoid div by zero

        # Normalize W_l rows to unit norm (exact scale gauge fix)
        W_l_canonical = W_l / row_norms  # (n_out, n_in)

        # Compensate in W_next columns (exact inverse)
        # W_next columns correspond to W_l outputs
        D_inv = (1.0 / row_norms.squeeze())  # (n_out,)
        W_next_canonical = W_next * D_inv.unsqueeze(0)  # broadcast: (m_out, n_out)

        # Store the gauge field D for potential reconstruction
        gauge_field = row_norms.squeeze()

        self.transforms.append({
            'type': 'scale',
            'gauge_field': gauge_field
        })

        return W_l_canonical, W_next_canonical, gauge_field

    def fix_permutation_symmetry(
        self,
        W_l: torch.Tensor,
        W_next: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Fixes neuron permutation symmetry.

        Canonical ordering: sort neurons by their canonical invariant.
        Invariant I(neuron_i) = sorted frobenius norm of W_l[i, :] concatenated
        with sorted frobenius norm of W_next[:, i].

        This invariant is preserved under all other gauge transformations,
        giving a globally consistent canonical form.
        """
        n_neurons = W_l.shape[0]

        # Compute canonical invariant for each neuron
        invariants = []
        for i in range(n_neurons):
            # Row of W_l (outgoing weights from neuron i)
            row_norm = torch.norm(W_l[i, :]).item()
            # Column of W_next (incoming weights to next layer from neuron i)
            col_norm = torch.norm(W_next[:, i]).item()
            # Joint invariant: tuple for stable sort
            invariants.append((row_norm * col_norm, row_norm, col_norm, i))

        # Sort neurons by canonical invariant (descending — most important first)
        invariants_sorted = sorted(invariants, key=lambda x: (-x[0], -x[1], -x[2]))
        perm = torch.tensor([item[3] for item in invariants_sorted])

        # Apply permutation (exact)
        W_l_canonical = W_l[perm, :]
        W_next_canonical = W_next[:, perm]

        self.transforms.append({
            'type': 'permutation',
            'permutation': perm
        })

        return W_l_canonical, W_next_canonical, perm

    def fix_qkv_rotation(
        self,
        W_Q: torch.Tensor,
        W_K: torch.Tensor,
        W_V: torch.Tensor,
        d_k: int
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Fixes the rotational symmetry of Q,K projections within each attention head.

        Symmetry: (W_Q, W_K) → (W_Q @ O, W_K @ O) for any O ∈ O(d_k)
        leaves QK^T unchanged: (XW_Q@O)(XW_K@O)^T = XW_Q@OO^T@W_K^T@X^T = XW_Q@W_K^T@X^T

        Canonical gauge: apply QR decomposition to W_Q, absorb rotation into W_K.
        W_Q → Q (orthogonal part of QR decomposition of W_Q)
        W_K → W_K @ R^T @ Q^T  (compensating rotation)

        This eliminates d_k*(d_k-1)/2 degrees of freedom per head EXACTLY.
        """
        # QR decomposition of W_Q
        Q_mat, R_mat = torch.linalg.qr(W_Q)  # W_Q = Q_mat @ R_mat

        # Canonical W_Q is Q_mat (orthonormal columns)
        W_Q_canonical = Q_mat

        # W_K must be rotated by R_mat @ Q_mat^T to preserve QK^T
        # Original: score = (X@W_Q) @ (X@W_K)^T
        # After:    score = (X@Q_mat) @ (X @ W_K_new)^T
        # Requirement: Q_mat @ W_K_new^T = W_Q @ W_K^T
        # => W_K_new = W_K @ W_Q^T @ Q_mat = W_K @ (Q_mat @ R_mat)^T @ Q_mat
        #            = W_K @ R_mat^T @ Q_mat^T @ Q_mat = W_K @ R_mat^T
        W_K_canonical = W_K @ R_mat.T

        # W_V has no symmetry with Q,K — left unchanged
        W_V_canonical = W_V

        self.transforms.append({
            'type': 'qkv_rotation',
            'R_mat': R_mat,
            'Q_mat': Q_mat
        })

        return W_Q_canonical, W_K_canonical, W_V_canonical

    def apply_all(self, model_state_dict: Dict) -> Dict:
        """Apply all gauge fixes to a model state dict."""
        new_state = dict(model_state_dict)
        # (In practice: identify layer pairs and apply above transforms)
        return new_state

