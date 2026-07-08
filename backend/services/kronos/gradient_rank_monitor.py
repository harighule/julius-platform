
import torch
import torch.nn as nn
import numpy as np
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass
import math
from torch.utils.data import DataLoader

# ─────────────────────────────────────────────────────────────────
# MODULE 1: GRADIENT RANK MONITOR
# Detects saturation and triggers scaling automatically.
# The model knows when it needs to grow.
# ─────────────────────────────────────────────────────────────────

class GradientRankMonitor:
    """
    Monitors the rank of the per-sample gradient matrix across batches.
    
    The per-sample gradient matrix G ∈ ℝ^{B × N} (batch × params) has rank
    r ≤ min(B, N). When r/N → threshold, the model parameter space is
    becoming saturated relative to the gradient information in the data.
    
    This is the theoretically correct signal for when to scale:
    - Too early (low ρ): new params get no gradient signal → wasted
    - Too late (ρ → 1): model already saturated → loss stalled
    - At ρ = threshold: new params immediately receive rich gradient signal
    """
    
    def __init__(
        self,
        model: nn.Module,
        threshold: float = 0.82,
        measurement_layers: Optional[List[str]] = None,
        ema_alpha: float = 0.95
    ):
        self.model = model
        self.threshold = threshold
        self.measurement_layers = measurement_layers
        self.ema_alpha = ema_alpha
        
        self.saturation_history: List[float] = []
        self.ema_saturation: float = 0.0
        self.tau_estimate: Optional[float] = None  # Saturation time constant
        self.step: int = 0
        
        # Hook storage for per-sample gradients
        self.grad_buffers: Dict[str, List[torch.Tensor]] = {}
        self._hooks = []
        
    def _register_hooks(self):
        """Register forward hooks to capture per-sample gradients."""
        def make_hook(name):
            def hook(module, grad_input, grad_output):
                if grad_output[0] is not None:
                    # Store per-sample gradient norms
                    g = grad_output[0]
                    if name not in self.grad_buffers:
                        self.grad_buffers[name] = []
                    self.grad_buffers[name].append(g.detach())
            return hook
        
        for name, module in self.model.named_modules():
            if isinstance(module, nn.Linear):
                if (self.measurement_layers is None or 
                        name in self.measurement_layers):
                    h = module.register_full_backward_hook(make_hook(name))
                    self._hooks.append(h)
    
    def measure_gradient_rank(
        self,
        loss_batch: torch.Tensor,  # Per-sample losses (B,)
        retain_graph: bool = True
    ) -> Dict[str, float]:
        """
        Measure gradient rank for the current batch.
        
        Uses randomized SVD for efficiency on large parameter spaces.
        Rank is estimated via the numerical rank of the gradient covariance
        matrix: Cov_G = G^T @ G / B
        
        The rank of Cov_G = rank of G (always).
        Estimated rank via stable rank: ||G||_F^2 / ||G||_2^2
        """
        self.grad_buffers.clear()
        
        # Compute per-sample gradients for a representative parameter block
        # We use the last linear layer as a proxy (computationally cheapest)
        target_layer = None
        for name, module in self.model.named_modules():
            if isinstance(module, nn.Linear):
                target_layer = (name, module)
        
        if target_layer is None:
            return {'saturation': 0.0, 'estimated_rank': 0, 'should_scale': False}
        
        layer_name, layer = target_layer
        W = layer.weight  # (out_features, in_features)
        
        # Compute per-sample gradient using vmap (PyTorch functional)
        # Per-sample grad of loss w.r.t. W for each sample in batch
        # G: (B, out_features, in_features) → reshape to (B, out*in)
        per_sample_grads = self._compute_per_sample_grads(
            loss_batch, W, retain_graph
        )  # (B, out*in)
        
        if per_sample_grads is None:
            return {'saturation': 0.0, 'estimated_rank': 0, 'should_scale': False}
        
        B, N = per_sample_grads.shape
        
        # Stable rank: ||G||_F^2 / ||G||_2^2 (fast approximation to true rank)
        # True rank requires full SVD. Stable rank is a smooth surrogate.
        frob_sq = (per_sample_grads ** 2).sum().item()
        
        # Approximate spectral norm via power iteration (10 steps)
        v = torch.randn(N, device=per_sample_grads.device)
        v = v / v.norm()
        for _ in range(10):
            u = per_sample_grads @ v
            u = u / (u.norm() + 1e-10)
            v = per_sample_grads.T @ u
            v = v / (v.norm() + 1e-10)
        spectral_sq = (per_sample_grads @ v).norm().item() ** 2
        
        stable_rank = frob_sq / (spectral_sq + 1e-10)
        saturation = min(stable_rank / min(B, N), 1.0)
        
        # EMA smoothing
        self.ema_saturation = (
            self.ema_alpha * self.ema_saturation + 
            (1 - self.ema_alpha) * saturation
        )
        self.saturation_history.append(self.ema_saturation)
        self.step += 1
        
        # Estimate saturation time constant τ
        if len(self.saturation_history) > 20:
            self.tau_estimate = self._estimate_tau()
        
        # Predict when saturation will be reached
        steps_to_saturation = None
        if self.tau_estimate is not None and self.ema_saturation < self.threshold:
            # ρ(t) = 1 - exp(-t/τ) → t = -τ · ln(1 - ρ)
            current_t = len(self.saturation_history)
            target_rho = self.threshold
            t_target = -self.tau_estimate * math.log(1 - target_rho + 1e-10)
            steps_to_saturation = max(0, int(t_target - current_t))
        
        return {
            'saturation': self.ema_saturation,
            'stable_rank': stable_rank,
            'estimated_rank': int(stable_rank),
            'param_count': N,
            'should_scale': self.ema_saturation >= self.threshold,
            'steps_to_saturation': steps_to_saturation,
            'tau': self.tau_estimate
        }
    
    def _compute_per_sample_grads(
        self,
        loss_batch: torch.Tensor,
        W: torch.Tensor,
        retain_graph: bool
    ) -> Optional[torch.Tensor]:
        """Compute per-sample gradients w.r.t. weight W."""
        try:
            grads = []
            for i in range(loss_batch.shape[0]):
                g = torch.autograd.grad(
                    loss_batch[i],
                    W,
                    retain_graph=True,
                    create_graph=False
                )[0]
                grads.append(g.flatten())
            return torch.stack(grads)  # (B, N)
        except Exception:
            return None
    
    def _estimate_tau(self) -> float:
        """Estimate saturation time constant τ from history."""
        history = np.array(self.saturation_history[-50:])  # Last 50 points
        t = np.arange(len(history), dtype=float)
        
        # Fit ρ(t) = 1 - exp(-t/τ) via log-linear regression
        # ln(1 - ρ) = -t/τ
        eps = 1e-6
        y = np.log(1 - history.clip(0, 1 - eps) + eps)
        
        # Linear regression: y = -t/τ
        tau = -np.dot(t, t) / (np.dot(t, y) + eps)
        return abs(tau)
    
    def layer_saturation_map(self) -> Dict[str, float]:
        """
        Compute per-layer saturation to identify bottlenecks.
        Returns saturation ratio for each linear layer.
        """
        layer_saturations = {}
        for name, module in self.model.named_modules():
            if isinstance(module, nn.Linear) and module.weight.grad is not None:
                W_grad = module.weight.grad  # (out, in)
                # Per-layer stable rank as proxy for saturation
                if W_grad.numel() > 0:
                    frob_sq = (W_grad ** 2).sum().item()
                    spectral = torch.linalg.norm(W_grad, ord=2).item() ** 2
                    layer_saturations[name] = frob_sq / (spectral + 1e-10)
        return layer_saturations
