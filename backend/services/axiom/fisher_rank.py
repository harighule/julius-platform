
import torch
import torch.nn as nn
import numpy as np
from typing import List, Tuple, Optional, Dict
from fractions import Fraction
import struct
import heapq
from collections import defaultdict

class FisherRankAnalyzer:
    """
    Phase 1: Fisher Rank Analysis

    Identifies the functional dimension of network parameters
    using Fisher Information approximations.

    This module does NOT modify weights.
    It only analyzes rank structure and produces metadata
    for downstream compression phases.
    """

    def __init__(self, rank_tol: float = 1e-8):
        self.rank_tol = rank_tol
        self.analysis_results = {}

    def compute_matrix_rank(
        self,
        weight: torch.Tensor
    ) -> Dict:
        """
        Compute effective rank statistics.
        """

        if weight.dim() != 2:
            raise ValueError(
                f"Expected 2D tensor, got {weight.dim()}D"
            )

        singular_values = torch.linalg.svdvals(weight)

        effective_rank = int(
            (singular_values > self.rank_tol).sum().item()
        )

        return {
            "shape": tuple(weight.shape),
            "rank": effective_rank,
            "max_rank": min(weight.shape),
            "compression_potential":
                min(weight.shape) - effective_rank,
            "singular_values": singular_values.cpu()
        }

    def analyze_state_dict(
        self,
        state_dict: Dict[str, torch.Tensor]
    ) -> Dict:
        """
        Analyze all linear layers in a model state dict.
        """

        results = {}

        for name, tensor in state_dict.items():

            if tensor.dim() == 2:

                results[name] = self.compute_matrix_rank(
                    tensor
                )

        self.analysis_results = results

        return results

    def summarize(self) -> Dict:

        total_rank = 0
        total_max_rank = 0

        for item in self.analysis_results.values():

            total_rank += item["rank"]
            total_max_rank += item["max_rank"]

        return {
            "total_rank": total_rank,
            "total_max_rank": total_max_rank,
            "rank_utilization":
                total_rank / max(total_max_rank, 1)
        }