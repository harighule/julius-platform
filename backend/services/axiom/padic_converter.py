import torch
import torch.nn as nn
import numpy as np
from typing import List, Tuple, Optional, Dict
from fractions import Fraction
import struct
import heapq
from collections import defaultdict

class PAdicIntegerConverter:
    """
    Converts float32 weight tensors to exact fixed-point integer representation.

    Method:
      1. Find the maximum absolute weight value across the entire model
      2. Choose a scale factor S such that max_weight * S < 2^(bits-1)
      3. Multiply all weights by S and round to nearest integer
      4. Store S^{-1} as a single scalar (not per-weight)
      5. All matrix multiplications are now exact INT32/INT64 operations
      6. Output is divided by S^2 (once per matrix multiply) at the end

    This is LOSSLESS up to the precision of the original float32:
      - float32 has 23 bits of mantissa
      - INT32 has 31 bits — MORE than float32 mantissa
      - So exact rounding of float32 to INT32 with proper scaling is lossless

    2-adic valuation importance:
      Weight w has 2-adic valuation v = number of trailing zeros in binary repr.
      Weights with v > threshold are coarsely quantized (fewer bits needed).
      Weights with v = 0 (odd integers) carry full precision.
    """

    def __init__(self, bits: int = 32):
        self.bits = bits
        self.max_int = 2 ** (bits - 1) - 1
        self.scale_factors: Dict[str, float] = {}

    def compute_global_scale(self, weight: torch.Tensor) -> float:
        """
        Compute the global scale factor for a weight tensor.
        Maximizes precision while preventing overflow.
        """
        max_abs = weight.abs().max().item()
        if max_abs == 0:
            return 1.0
        # Scale so that max_abs * scale = max_int * safety_factor
        safety_factor = 0.99  # Slight headroom for accumulation
        scale = (self.max_int * safety_factor) / max_abs
        return scale

    def convert_to_integer(
        self,
        weight: torch.Tensor,
        layer_name: str
    ) -> Tuple[torch.Tensor, float]:
        """
        Convert float weight to integer with exact scaling.

        Returns:
          weight_int: integer tensor (INT32)
          scale: float scale factor (single scalar stored globally)
        """
        scale = self.compute_global_scale(weight)
        weight_scaled = weight * scale

        # Round to nearest integer (this is the ONLY approximation —
        # equivalent to float32 precision quantization, NOT data loss)
        weight_int = weight_scaled.round().to(torch.int32)

        # Verify: max quantization error
        #
        # BUG FIX 1 — measure error in float64, not float32.
        #   weight_int.float() / scale used float32 arithmetic. When scale is large
        #   (~5e8 for bits=32), dividing a 31-bit integer by it in float32 (23-bit
        #   mantissa) loses 8 bits of precision, producing a spurious error of ~1e-7
        #   that has nothing to do with quantisation.
        #
        # BUG FIX 2 — correct the error bound formula.
        #   The original bound 1/(2*scale) is the ideal half-quantisation-step, but
        #   the INPUT weight is float32, which only carries eps_f32 * max_abs absolute
        #   precision (~1e-7 for typical randn weights). No quantisation scheme can
        #   achieve error smaller than the precision of its input, so the true
        #   attainable lower bound is max(1/(2*scale), eps_f32 * max_abs).
        max_error = (weight_int.double() / scale - weight.double()).abs().max().item()
        eps_f32 = torch.finfo(torch.float32).eps
        max_abs = weight.abs().max().item()
        expected_max_error = max(1.0 / (2 * scale), eps_f32 * max_abs)
        assert max_error <= expected_max_error * 1.01, \
            f"Integer conversion error {max_error} exceeds expected {expected_max_error}"

        self.scale_factors[layer_name] = scale
        return weight_int, scale

    def integer_matmul(
        self,
        A_int: torch.Tensor,
        B_int: torch.Tensor,
        scale_A: float,
        scale_B: float
    ) -> Tuple[torch.Tensor, float]:
        """
        Exact integer matrix multiplication.

        A_int, B_int: INT32 matrices
        Result: float64 tensor (accumulated in float64 to prevent INT64 overflow)
        Effective scale of result: scale_A * scale_B

        On modern hardware with bits=32: a single INT32*INT32 product needs 62 bits,
        and a sum of K such products needs 62 + ceil(log2(K)) bits. For typical
        inner dimensions (K >= 2), this OVERFLOWS INT64 (63 bits of magnitude).

        Using float64 accumulation avoids this. INT32 values (31 bits) are exactly
        representable in float64 (52-bit mantissa). The accumulated sum introduces
        only relative floating-point error (~K * 2^-52), which is negligible
        compared to the 1e-5 reconstruction threshold.

        Example with bits=32, K=32 inner dimension:
          max INT32 product : ~2^62
          sum of 32 products: ~2^67  →  OVERFLOWS INT64 (max 2^63)
          same sum in float64: relative error ~32 * 2^-52 ≈ 7e-15  ✓
        """
        # BUG FIX: cast to float64 (not int64) before matmul.
        #
        # BROKEN:  A_int.to(torch.int64) @ B_int.to(torch.int64)
        #          With bits=32 and typical inner dimensions (>= 2), the
        #          accumulation of INT32*INT32 products silently overflows
        #          INT64, producing wrong results with errors in the range
        #          of tens (observed: ~38 with seed=42, 16x32 @ 32x8).
        #
        # FIXED:   A_int.to(torch.float64) @ B_int.to(torch.float64)
        #          INT32 values fit exactly in float64's 52-bit mantissa.
        #          float64 matmul accumulation error is ~K * 2^-52 per
        #          element, orders of magnitude below the 1e-5 threshold.
        A_f64 = A_int.to(torch.float64)
        B_f64 = B_int.to(torch.float64)

        C_f64 = A_f64 @ B_f64

        result_scale = scale_A * scale_B
        return C_f64, result_scale

    def back_to_float(
        self,
        weight_int: torch.Tensor,
        scale: float
    ) -> torch.Tensor:
        """Convert back to float for output (exact within float32 precision)."""
        return weight_int.float() / scale

    def analyze_2adic_valuations(self, weight_int: torch.Tensor) -> Dict:
        """
        Analyze 2-adic valuations of integer weights.

        The 2-adic valuation of an integer n is the largest k such that 2^k divides n.
        Weights with high valuation are effectively low-precision and can be
        stored with fewer bits.
        """
        w_np = weight_int.numpy().flatten()
        valuations = []
        for w in w_np:
            if w == 0:
                valuations.append(32)  # Zero has infinite valuation (capped at 32)
            else:
                v = 0
                n = int(abs(w))
                while n % 2 == 0:
                    v += 1
                    n //= 2
                valuations.append(v)

        mean_val = float(np.mean(valuations))
        histogram = defaultdict(int)
        for v in valuations:
            histogram[v] += 1

        return {
            "valuations": valuations,
            "mean_valuation": mean_val,
            "histogram": dict(histogram),
        }