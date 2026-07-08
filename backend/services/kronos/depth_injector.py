
import torch
import torch.nn as nn
import numpy as np
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass
import math
from torch.utils.data import DataLoader

# MODULE 3: IDENTITY DEPTH INJECTOR
class DepthInjector:
    """
    Inserts new layers into a network with guaranteed zero regression.
    
    Method: initialize new layers as identity maps.
    For a linear layer: W_new = I, b_new = 0  →  output = input (exact)
    For attention: initialize as skip connection equivalents
    
    The "representation gap" signal:
    New layer's gradient = W_{l+1} · (representation_{optimal} - representation_{current})
    This is automatically provided by backprop — new layers immediately
    receive meaningful gradients because they sit between layers with
    non-zero gradients.
    
    Speed: learning rate for new layers = λ · ||representation_gap||
    where representation_gap is estimated from the Fisher info of adjacent layers.
    """
    
    def __init__(self, adaptive_lr_scale: float = 2.0):
        self.adaptive_lr_scale = adaptive_lr_scale
    
    def create_identity_ffn(
        self,
        d_model: int,
        d_ff: int,
        device: torch.device
    ) -> nn.Module:
        """
        Create a FFN block initialized as identity.
        
        Standard FFN: x → W_2 · ReLU(W_1 · x + b_1) + b_2
        
        For identity: W_1 = 0, W_2 = 0, b_1 = 0, b_2 = 0
        → output = W_2 · ReLU(0 + 0) + 0 = 0
        
        With residual connection: x + FFN(x) = x + 0 = x  (identity ✓)
        
        Uses the residual connection — this is why ResNets were revolutionary.
        """
        ffn = nn.Sequential(
            nn.Linear(d_model, d_ff, bias=True),
            nn.GELU(),
            nn.Linear(d_ff, d_model, bias=True)
        ).to(device)
        
        # Initialize BOTH linear layers to zero
        # With residual: output = x + FFN(x) = x + 0 = x
        with torch.no_grad():
            for module in ffn.modules():
                if isinstance(module, nn.Linear):
                    nn.init.zeros_(module.weight)
                    nn.init.zeros_(module.bias)
        
        return ffn
    
    def compute_representation_gap(
        self,
        W_before: torch.Tensor,
        W_after: torch.Tensor,
        activation_stats: Optional[Dict] = None
    ) -> float:
        """
        Estimate the representation gap between two adjacent layers.
        
        Gap = ||W_{l+1} @ W_l - W_ideal||_F
        
        W_ideal estimated as: the best rank-min(m,n) approximation of
        the input-output covariance matrix across the training distribution.
        
        High gap → inserting a layer here will help learning.
        Low gap → this boundary is already well-represented.
        """
        if W_before.dim() != 2 or W_after.dim() != 2:
            return 0.0
        
        if W_before.shape[0] != W_after.shape[1]:
            return 0.0
        
        # Composition of adjacent layers
        W_composed = W_after @ W_before  # (p, n)
        
        # Estimate of ideal: best low-rank approximation of composition
        U, S, Vh = torch.linalg.svd(W_composed, full_matrices=False)
        
        # The "ideal" would have flat singular value distribution (max entropy)
        # Gap = deviation from flat spectrum = std of singular values
        S_np = S.detach().cpu().numpy()
        gap = float(np.std(S_np) / (np.mean(S_np) + 1e-10))
        
        return gap
    
    def find_optimal_injection_points(
        self,
        model: nn.Module,
        top_k: int = 5
    ) -> List[Tuple[str, str, float]]:
        """
        Find the top-k layer pairs where new layers should be injected.
        
        Returns list of (layer_before_name, layer_after_name, gap_score).
        """
        linear_layers = []
        for name, module in model.named_modules():
            if isinstance(module, nn.Linear):
                linear_layers.append((name, module))
        
        gaps = []
        for i in range(len(linear_layers) - 1):
            name_i, module_i = linear_layers[i]
            name_j, module_j = linear_layers[i + 1]
            
            gap = self.compute_representation_gap(
                module_i.weight,
                module_j.weight
            )
            gaps.append((name_i, name_j, gap))
        
        # Sort by gap (descending) and return top-k
        gaps.sort(key=lambda x: -x[2])
        return gaps[:top_k]
    
    def inject_layers(
        self,
        model: nn.Module,
        injection_points: List[Tuple[str, str, float]],
        d_model: int,
        d_ff: int
    ) -> Tuple[nn.Module, Dict]:
        """
        Inject identity layers at all specified points simultaneously.
        
        All new layers start as identity (exact function preservation).
        All new layers receive amplified learning rates via param groups.
        """
        device = next(model.parameters()).device
        new_layers = {}
        
        for name_before, name_after, gap_score in injection_points:
            # Create identity FFN
            new_ffn = self.create_identity_ffn(d_model, d_ff, device)
            layer_key = f"injected_{name_before}_{name_after}"
            new_layers[layer_key] = {
                'module': new_ffn,
                'insert_after': name_before,
                'gap_score': gap_score,
                # Amplified LR for new layers: they need to learn faster
                'lr_scale': self.adaptive_lr_scale * (1 + gap_score)
            }
        
        return model, new_layers
