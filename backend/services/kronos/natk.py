
import torch
import torch.nn as nn
import numpy as np
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass
import math
from torch.utils.data import DataLoader
from collections import defaultdict
import heapq

class NATKAnalyzer:
    """
    Computes the Neural Architecture Tangent Kernel (NATK).
    
    NATK_l = ∂L/∂n_l = trace(F_l) / n_l
    
    where F_l is the per-layer Fisher Information Matrix.
    
    High NATK eigenvalue → this layer is a capacity bottleneck.
    
    Also computes:
      - Optimal scaling factor k_l* for each layer
      - Expected loss reduction from scaling layer l by k_l
      - Optimal depth injection points (representation gap)
    """
    
    def __init__(self, model: nn.Module):
        self.model = model
        self.natk_history: List[Dict] = []
    
    def compute_per_layer_fisher_trace(
        self,
        dataloader_sample: List[Tuple],
        criterion: nn.Module,
        device: torch.device,
        n_samples: int = 100
    ) -> Dict[str, float]:
        """
        Compute trace(F_l) / n_l for each layer.
        
        trace(F_l) = E[||∇_{W_l} L||_F²]
        
        This is computed via Monte Carlo: average gradient squared norm
        over n_samples data points.
        """
        fisher_traces = defaultdict(float)
        param_counts = {}
        
        for name, module in self.model.named_modules():
            if isinstance(module, nn.Linear):
                param_counts[name] = module.weight.numel()
        
        # Accumulate gradient squared over samples
        for i, (x, y) in enumerate(dataloader_sample[:n_samples]):
            if isinstance(x, torch.Tensor):
                x = x.unsqueeze(0).to(device)
            if isinstance(y, torch.Tensor):
                y = y.unsqueeze(0).to(device)
            
            self.model.zero_grad()
            out = self.model(x)
            loss = criterion(out, y)
            loss.backward()
            
            for name, module in self.model.named_modules():
                if isinstance(module, nn.Linear) and module.weight.grad is not None:
                    fisher_traces[name] += (module.weight.grad ** 2).sum().item()
        
        # Normalize by n_samples and n_params
        natk_values = {}
        for name in fisher_traces:
            n_params = param_counts.get(name, 1)
            natk_values[name] = fisher_traces[name] / (n_samples * n_params)
        
        self.natk_history.append(natk_values)
        return natk_values
    
    def recommend_scaling_plan(
        self,
        natk_values: Dict[str, float],
        current_params: int,
        target_params: int,
        budget_per_step: int
    ) -> List[Dict]:
        """
        Generate optimal scaling plan from current to target parameter count.
        
        Strategy: always scale the highest-NATK layer first.
        This is provably optimal: gradient of loss w.r.t. capacity
        is highest for the highest-NATK layer.
        
        Returns ordered list of scaling actions.
        """
        plan = []
        remaining_budget = target_params - current_params
        
        # Priority queue: (negative NATK, layer_name)
        layer_queue = []
        layer_params = {}
        
        for name, module in self.model.named_modules():
            if isinstance(module, nn.Linear) and name in natk_values:
                natk = natk_values[name]
                n_params = module.weight.numel()
                layer_params[name] = n_params
                heapq.heappush(layer_queue, (-natk, name))
        
        while remaining_budget > 0 and layer_queue:
            neg_natk, name = heapq.heappop(layer_queue)
            natk = -neg_natk
            n_params = layer_params[name]
            
            # Optimal k: scale so that new params ≤ budget_per_step
            k = min(
                int(math.sqrt(budget_per_step / (n_params + 1))),
                int(math.sqrt(remaining_budget / (n_params + 1))),
                10  # Cap at 10× per step for stability
            )
            k = max(k, 2)  # At least double
            
            new_params = n_params * k * k  # Both dimensions scale by k
            
            plan.append({
                'layer': name,
                'scale_factor': k,
                'natk_value': natk,
                'original_params': n_params,
                'new_params': new_params,
                'expected_loss_reduction': natk * (k - 1),
                'action': 'width_expansion'
            })
            
            remaining_budget -= (new_params - n_params)
            
            # Re-insert with reduced NATK (scaling reduces bottleneck)
            new_natk = natk / k
            heapq.heappush(layer_queue, (-new_natk, name))
        
        return plan
    
    def estimate_loss_after_scaling(
        self,
        current_loss: float,
        natk_values: Dict[str, float],
        scaling_plan: List[Dict],
        n_training_steps: int
    ) -> float:
        """
        Estimate the loss after scaling and n_training_steps of MIC training.
        
        Uses linearized NATK dynamics:
        ΔL ≈ -η · Σ_l NATK_l · (k_l - 1) · n_training_steps
        """
        total_natk_gain = sum(
            action['expected_loss_reduction'] 
            for action in scaling_plan
        )
        
        # Learning dynamics: loss decreases exponentially with gradient info
        eta = 0.01  # Effective learning rate
        predicted_loss = current_loss * math.exp(
            -eta * total_natk_gain * n_training_steps
        )
        
        return max(predicted_loss, 0.0)

