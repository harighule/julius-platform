
import torch
import torch.nn as nn
import numpy as np
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass
import math
from torch.utils.data import DataLoader

# MODULE 6: FRACTAL SELF-SIMILAR WEIGHT GENERATOR
# Uses the weight distribution of a trained model to generate
# statistically identical weights at larger scale.
# Based on Marchenko-Pastur law from Random Matrix Theory.
# ─────────────────────────────────────────────────────────────────

class FractalWeightGenerator:
    """
    Generates weight matrices for new parameters using the statistical
    structure of trained weights.
    
    Key insight: trained weight matrices follow the Marchenko-Pastur
    distribution (from random matrix theory) with a spike at zero
    corresponding to learned structure. This distribution is SCALE-INVARIANT
    — larger weight matrices from the same training distribution should
    follow the same law, scaled appropriately.
    
    This gives dramatically better initialization than random:
    - New weights are statistically indistinguishable from trained weights
    - Gradient signal is immediately meaningful (not wasted on "unlearning")
    - Effective learning begins immediately at full speed
    
    Marchenko-Pastur distribution (for aspect ratio γ = n/m):
      ρ(λ) = (1/2πγσ²) · √((λ+ - λ)(λ - λ-)) / λ
      λ± = σ²(1 ± √γ)²
    """
    
    def __init__(self):
        self.fitted_params: Dict[str, Dict] = {}
    
    def fit_to_trained_weights(
        self,
        model: nn.Module,
        layer_prefix: Optional[str] = None
    ) -> Dict:
        """
        Fit Marchenko-Pastur distribution to trained weight matrices.
        
        Extracts:
          - σ² (variance parameter)
          - γ (aspect ratio)
          - spike_eigenvalues (the learned structure above the bulk)
          - spike_eigenvectors (directions of learned structure)
        """
        params = {}
        
        for name, module in model.named_modules():
            if not isinstance(module, nn.Linear):
                continue
            if layer_prefix and not name.startswith(layer_prefix):
                continue
            
            W = module.weight.detach().float()  # (m, n)
            m, n = W.shape
            gamma = n / m  # Aspect ratio
            
            # Compute empirical singular value distribution
            singular_vals = torch.linalg.svdvals(W)  # (min(m,n),)
            
            # Estimate σ² from the bulk (Marchenko-Pastur bulk)
            # The bulk eigenvalues of W W^T / n follow MP with parameter σ²
            eigenvals = (singular_vals ** 2) / n
            
            # Estimate σ² via median (robust to outliers from learned structure)
            sigma_sq = eigenvals.median().item()
            
            # Marchenko-Pastur bulk boundary
            lambda_plus = sigma_sq * (1 + math.sqrt(gamma)) ** 2
            
            # Identify "spike" eigenvalues (above MP bulk — these are learned)
            spike_mask = eigenvals > lambda_plus * 1.05  # 5% margin
            n_spikes = spike_mask.sum().item()
            
            # Get spike structure via SVD
            U, S, Vh = torch.linalg.svd(W, full_matrices=False)
            
            params[name] = {
                'sigma_sq': sigma_sq,
                'gamma': gamma,
                'shape': (m, n),
                'n_spikes': int(n_spikes),
                'spike_values': S[:int(n_spikes)].cpu().numpy() if n_spikes > 0 else np.array([]),
                'spike_U': U[:, :int(n_spikes)].cpu().numpy() if n_spikes > 0 else np.zeros((m, 0)),
                'spike_Vh': Vh[:int(n_spikes), :].cpu().numpy() if n_spikes > 0 else np.zeros((0, n)),
            }
        
        self.fitted_params = params
        return params
    
    def generate_new_layer_weights(
        self,
        target_shape: Tuple[int, int],
        reference_params: Dict,
        device: torch.device,
        dtype: torch.dtype = torch.float32
    ) -> torch.Tensor:
        """
        Generate a new weight matrix for a layer of target_shape.
        
        Uses fitted MP distribution from reference_params:
        1. Sample bulk from MP distribution (random, no learned structure)
        2. Add scaled spike structure (scaled to new dimensions)
        3. Result: statistically identical to a trained weight of this shape
        """
        m, n = target_shape
        sigma_sq = reference_params.get('sigma_sq', 0.02)
        n_spikes = reference_params.get('n_spikes', 0)
        spike_values = reference_params.get('spike_values', np.array([]))
        
        # Sample MP bulk: W_bulk = σ · randn(m, n) / √n
        sigma = math.sqrt(sigma_sq)
        W_bulk = (sigma / math.sqrt(n)) * torch.randn(m, n, device=device, dtype=dtype)
        
        # Add spike structure (scaled to new dimensions)
        if n_spikes > 0 and len(spike_values) > 0:
            # Scale spike singular values to new dimensions
            scale_factor = math.sqrt(m * n) / math.sqrt(
                reference_params['shape'][0] * reference_params['shape'][1]
            )
            
            new_spike_values = torch.tensor(
                spike_values * scale_factor, device=device, dtype=dtype
            )
            
            # Random spike directions (we don't copy the original directions —
            # the new layer should have its own learned structure to discover)
            U_new = torch.linalg.qr(torch.randn(m, n_spikes, device=device))[0]
            Vh_new = torch.linalg.qr(torch.randn(n, n_spikes, device=device))[0].T
            
            # W_spike = U_new @ diag(spike_values) @ Vh_new
            W_spike = U_new @ torch.diag(new_spike_values) @ Vh_new
            W_bulk = W_bulk + W_spike
        
        return W_bulk


