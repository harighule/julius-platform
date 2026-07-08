import torch
import torch.nn as nn
import numpy as np
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass
import math
from torch.utils.data import DataLoader

from dataclasses import dataclass

@dataclass
class ScalingConfig:
    initial_params: int = 13_000_000_000
    target_params: int = 10_000_000_000_000
    scaling_phases: int = 4
    gradient_rank_threshold: float = 0.82
    mic_pool_size: int = 50000
    mic_selection_ratio: float = 0.1
    regression_budget: float = 1e-4
    verify_after_scale: bool = True
    distributed: bool = True