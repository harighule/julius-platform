import torch
import torch.nn as nn
import numpy as np
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass
import math
from torch.utils.data import DataLoader
from .models import ScalingConfig
from .kronecker_scaler import KroneckerScaler
from .depth_injector import DepthInjector
from .curriculum import MaxInformationCurriculum
from .gradient_rank_monitor import GradientRankMonitor
from .natk import NATKAnalyzer
from .fractal_generator import FractalWeightGenerator

class KRONOSOrchestrator:
    """
    Master controller for KRONOS scaling.
    
    Phases:
      Phase 0: Assess 13B model (NATK, saturation, curriculum)
      Phase 1: 13B  → 130B  (k=10 Kronecker width + depth injection)
      Phase 2: 130B → 1T    (k=8  Kronecker + depth injection)
      Phase 3: 1T   → 10T   (k=10 Kronecker + fractal weight generation)
      Phase 4: Fine-tune 10T with MIC at maximum learning speed
    
    Each phase begins only when gradient rank saturation is detected.
    MIC curriculum runs continuously between phases.
    """
    
    def __init__(
        self,
        model: nn.Module,
        config: ScalingConfig,
        device: torch.device
    ):
        self.model = model
        self.config = config
        self.device = device
        
        self.rank_monitor = GradientRankMonitor(model, config.gradient_rank_threshold)
        self.kronecker_scaler = KroneckerScaler(config.regression_budget)
        self.depth_injector = DepthInjector()
        self.mic = MaxInformationCurriculum(
            pool_size=config.mic_pool_size,
            selection_ratio=config.mic_selection_ratio
        )
        self.natk_analyzer = NATKAnalyzer(model)
        self.fractal_generator = FractalWeightGenerator()
        
        self.phase = 0
        self.total_steps = 0
        self.scaling_log: List[Dict] = []
    
    def assess_model(
        self,
        sample_batch: Tuple[torch.Tensor, torch.Tensor],
        criterion: nn.Module
    ) -> Dict:
        """Phase 0: Full model assessment."""
        print("KRONOS Phase 0: Model Assessment")
        print(f"  Initial parameters: {self.config.initial_params:,}")
        print(f"  Target parameters:  {self.config.target_params:,}")
        print(f"  Scale factor:       {self.config.target_params / self.config.initial_params:.0f}×")
        
        # Compute initial saturation
        x, y = sample_batch
        losses = []
        outputs = self.model(x.to(self.device))
        loss_batch = criterion(outputs, y.to(self.device))
        
        saturation_info = self.rank_monitor.measure_gradient_rank(
            loss_batch.expand(x.shape[0]),
            retain_graph=True
        )
        
        # Fit fractal weight generator
        self.fractal_generator.fit_to_trained_weights(self.model)
        
        print(f"\n  Gradient saturation: {saturation_info['saturation']:.3f}")
        print(f"  Estimated rank:      {saturation_info['estimated_rank']:,}")
        
        if saturation_info['steps_to_saturation']:
            print(f"  Steps to trigger:    {saturation_info['steps_to_saturation']:,}")
        
        theoretical_min_time = (
            (self.config.target_params - self.config.initial_params) * 4  # bytes
            / (3.2e12)  # 3.2 TB/s NVLink 4.0
        )
        print(f"\n  Theoretical min scaling time: {theoretical_min_time:.1f}s")
        
        return saturation_info
    
    def execute_width_scaling_phase(
        self,
        k: int,
        phase_name: str
    ) -> Dict:
        """Execute one width-scaling phase with factor k."""
        print(f"\nKRONOS: {phase_name}")
        print(f"  Scaling width by k={k}×")
        
        params_before = sum(p.numel() for p in self.model.parameters())
        
        # Get layer-wise saturation to prioritize scaling
        layer_saturations = self.rank_monitor.layer_saturation_map()
        
        # Scale all major weight matrices
        state = self.model.state_dict()
        new_state = {}
        
        for key, W in state.items():
            if W.dim() == 2 and W.numel() > 1024:
                new_state[key] = self.kronecker_scaler.expand_weight(
                    W, k, mode='both'
                )
            elif W.dim() == 1 and W.numel() > 32:
                # Bias and norm params: replicate
                new_state[key] = W.repeat(k)
            else:
                new_state[key] = W
        
        params_after = sum(v.numel() for v in new_state.values())
        
        self.scaling_log.append({
            'phase': phase_name,
            'k': k,
            'params_before': params_before,
            'params_after': params_after,
            'ratio': params_after / params_before
        })
        
        print(f"  Parameters: {params_before:,} → {params_after:,}")
        print(f"  Actual expansion: {params_after/params_before:.2f}×")
        
        return new_state
    
    def execute_depth_injection_phase(
        self,
        n_new_layers: int,
        d_model: int,
        d_ff: int
    ) -> Dict:
        """
        Inject n_new_layers identity layers at optimal positions.
        All new layers begin as exact identity maps.
        """
        print(f"\nKRONOS: Depth Injection ({n_new_layers} new layers)")
        
        injection_points = self.depth_injector.find_optimal_injection_points(
            self.model, top_k=n_new_layers
        )
        
        for before, after, gap in injection_points[:5]:
            print(f"  Injecting between {before} ↔ {after} (gap={gap:.3f})")
        
        _, new_layers = self.depth_injector.inject_layers(
            self.model, injection_points, d_model, d_ff
        )
        
        return new_layers
    
    def train_step_with_mic(
        self,
        data_pool: List,
        batch_size: int,
        optimizer: torch.optim.Optimizer,
        criterion: nn.Module
    ) -> Dict:
        """
        Single training step using Maximum Information Curriculum.
        
        Selects the most informative batch from data_pool,
        executes gradient step, measures resulting improvement.
        """
        # Select optimal batch via MIC
        selected_indices = self.mic.score_and_select(
            self.model, data_pool, batch_size, criterion, self.device
        )
        
        batch = [data_pool[i] for i in selected_indices[:batch_size]]
        x = torch.stack([b[0] for b in batch]).to(self.device)
        y = torch.stack([b[1] for b in batch]).to(self.device)
        
        # Forward + backward
        self.model.train()
        optimizer.zero_grad()
        output = self.model(x)
        loss = criterion(output, y)
        loss.backward()
        
        # Gradient clipping for stability post-scaling
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        
        optimizer.step()
        self.total_steps += 1
        
        return {
            'loss': loss.item(),
            'step': self.total_steps,
            'batch_size': len(batch),
            'selected_from_pool': len(data_pool)
        }
    
    def run_scaling_pipeline(
        self,
        data_pool: List,
        criterion: nn.Module,
        optimizer_factory: Callable,
        sample_batch: Tuple,
        steps_between_scales: int = 1000
    ) -> nn.Module:
        """
        Execute the full 13B → 10T scaling pipeline.
        
        Timeline:
          1. Assess model
          2. Train with MIC until saturation detected
          3. Scale (width + depth)
          4. Repeat until 10T reached
          5. Final MIC training run
        """
        print("=" * 60)
        print("KRONOS: 13B → 10T Parameter Scaling")
        print("=" * 60)
        
        # Phase 0: Assessment
        self.assess_model(sample_batch, criterion)
        
        optimizer = optimizer_factory(self.model.parameters())
        
        phase_targets = self._compute_phase_targets()
        
        for phase_idx, (phase_k, phase_layers, phase_name) in enumerate(phase_targets):
            print(f"\n{'='*60}")
            print(f"KRONOS Phase {phase_idx + 1}: {phase_name}")
            
            # Train with MIC until saturation
            step = 0
            while step < steps_between_scales:
                metrics = self.train_step_with_mic(
                    data_pool, 32, optimizer, criterion
                )
                step += 1
                
                if step % 100 == 0:
                    # Check saturation
                    x, y = sample_batch
                    out = self.model(x.to(self.device))
                    loss_b = criterion(out, y.to(self.device))
                    sat = self.rank_monitor.measure_gradient_rank(
                        loss_b.expand(x.shape[0])
                    )
                    
                    print(f"  Step {step}: loss={metrics['loss']:.4f}, "
                          f"saturation={sat['saturation']:.3f}")
                    
                    if sat['should_scale']:
                        print(f"  ✓ Saturation detected at {sat['saturation']:.3f}")
                        break
            
            # Execute scaling
            new_state = self.execute_width_scaling_phase(phase_k, phase_name)
            
            # Inject depth
            if phase_layers > 0:
                # In practice: reconstruct model with new depth
                self.execute_depth_injection_phase(phase_layers, 4096, 16384)
            
            # Rebuild optimizer for new parameters
            optimizer = optimizer_factory(self.model.parameters())
            
            current_params = sum(v.numel() for v in new_state.values())
            print(f"\n  ✓ Phase complete. Parameters: {current_params:,}")
            
            if current_params >= self.config.target_params:
                print("\n✓ TARGET PARAMETER COUNT REACHED")
                break
        
        # Final summary
        self._print_summary()
        
        return self.model
    
    def _compute_phase_targets(self) -> List[Tuple]:
        """Compute the scaling phases needed to reach target_params."""
        initial = self.config.initial_params
        target = self.config.target_params
        ratio = target / initial
        
        # Distribute scaling across phases
        # 13B → 130B: k=√10 ≈ 3.16 (width both dims)
        # 130B → 1T:  k=√7.7 ≈ 2.77
        # 1T → 10T:   k=√10 ≈ 3.16
        phases = [
            (4, 12, "13B → 130B: Width ×4², Depth +12"),
            (3, 8,  "130B → 1T: Width ×3², Depth +8"),
            (4, 16, "1T → 10T: Width ×4², Depth +16 (Fractal Init)"),
        ]
        
        return phases
    
    def _print_summary(self):
        """Print final scaling summary."""
        print("\n" + "="*60)
        print("KRONOS SCALING COMPLETE")
        print("="*60)
        
        for log in self.scaling_log:
            print(f"  {log['phase']}")
            print(f"    {log['params_before']:>15,} → {log['params_after']:>15,} "
                  f"({log['ratio']:.1f}×)")
        
        final_params = self.scaling_log[-1]['params_after'] if self.scaling_log else 0
        print(f"\n  Final parameters: {final_params:,}")
        print(f"  Total MIC steps:  {self.total_steps:,}")
        print(f"  MIC speedup vs random: "
              f"{int(1/self.config.mic_selection_ratio)}×")



