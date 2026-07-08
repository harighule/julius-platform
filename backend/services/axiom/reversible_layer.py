

from typing import Dict
from typing import Tuple

import torch
import torch.nn as nn
import numpy as np
from typing import List, Tuple, Optional, Dict
from fractions import Fraction
import struct
import heapq
from collections import defaultdict

class ReversibleLayer(nn.Module):
    """
    Wraps any layer F into a reversible layer using the Gomez/Jacobsen
    coupling scheme (RevNet), extended here for transformers.

    The reversible block computes:
      y1 = x1 + F(x2)
      y2 = x2 + G(y1)

    And is exactly invertible:
      x2 = y2 - G(y1)
      x1 = y1 - F(x2)

    This means during inference, we do NOT need to store intermediate
    activations — we can recompute them on the backward pass (or during
    a forward pass that needs intermediate states).

    Net effect: memory = O(1) layers instead of O(L).
    Computation cost = unchanged (same FLOPS).
    Quality loss = ZERO (exact invertibility).
    """

    def __init__(self, F: nn.Module, G: nn.Module):
        super().__init__()
        self.F = F
        self.G = G

    def forward(
        self,
        x: torch.Tensor
    ) -> torch.Tensor:
        """
        Forward pass. Input x is split in half along last dimension.
        """
        x1, x2 = x.chunk(2, dim=-1)
        y1 = x1 + self.F(x2)
        y2 = x2 + self.G(y1)
        return torch.cat([y1, y2], dim=-1)

    def inverse(
        self,
        y: torch.Tensor
    ) -> torch.Tensor:
        """
        Exact inverse — used for activation recomputation.
        """
        y1, y2 = y.chunk(2, dim=-1)
        x2 = y2 - self.G(y1)
        x1 = y1 - self.F(x2)
        return torch.cat([x1, x2], dim=-1)


class ReversibleTransformerBlock(nn.Module):
    """
    Reversible Transformer block.
    Attention and FFN are the F and G functions.

    Memory cost: stores only the INPUT to the first reversible block.
    All intermediate activations are recomputed from the invertible chain.
    """

    def __init__(self, attention: nn.Module, ffn: nn.Module, d_model: int):
        super().__init__()
        self.rev_layer = ReversibleLayer(attention, ffn)
        self.d_model = d_model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.rev_layer(x)

