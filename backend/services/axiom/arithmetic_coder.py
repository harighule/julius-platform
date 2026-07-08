
import torch
import torch.nn as nn
import numpy as np
from typing import List, Tuple, Optional, Dict
from fractions import Fraction
import struct
import heapq
from collections import defaultdict

class ArithmeticCoder:
    """
    Lossless arithmetic coding of integer weight arrays.

    Arithmetic coding achieves entropy H(X) bits per symbol — the
    theoretical minimum for lossless compression. For integer weights
    of trained models, empirical entropy is typically 2–4 bits per weight
    despite 32-bit storage = 8–16× compression from coding alone.

    This is Shannon's source coding theorem applied exactly.
    """

    def __init__(self):
        self.PRECISION = 64
        self.FULL = 1 << self.PRECISION
        self.HALF = 1 << (self.PRECISION - 1)
        self.QUARTER = 1 << (self.PRECISION - 2)

    def _build_frequency_table(
        self,
        data: np.ndarray
    ) -> Tuple[Dict, Dict, Dict]:
        """Build frequency, CDF, and probability tables for arithmetic coding."""
        unique, counts = np.unique(data, return_counts=True)
        total = len(data)

        # Laplace smoothing to handle unseen symbols
        freq = {int(sym): int(cnt) for sym, cnt in zip(unique, counts)}
        symbols = sorted(freq.keys())

        # Build cumulative distribution
        cumulative = {}
        running = 0
        for sym in symbols:
            cumulative[sym] = running
            running += freq[sym]
        cumulative['total'] = running

        prob = {sym: freq[sym] / total for sym in symbols}

        return freq, cumulative, prob

    def encode(self, data: np.ndarray) -> Tuple[bytes, Dict]:
        """
        Arithmetic encode an integer array.
        Returns: compressed bytes + metadata for decoding
        """
        freq, cumulative, prob = self._build_frequency_table(data)
        total = cumulative['total']
        symbols = sorted(freq.keys())

        # Arithmetic coding
        low = 0
        high = self.FULL
        bits_written = []
        pending_bits = 0

        def write_bit(bit):
            bits_written.append(bit)
            nonlocal pending_bits
            for _ in range(pending_bits):
                bits_written.append(1 - bit)
            pending_bits = 0

        for symbol in data:
            sym = int(symbol)
            range_size = high - low
            sym_low = cumulative[sym]
            sym_high = sym_low + freq[sym]

            high = low + (range_size * sym_high) // total
            low = low + (range_size * sym_low) // total

            while True:
                if high <= self.HALF:
                    write_bit(0)
                    low *= 2
                    high *= 2
                elif low >= self.HALF:
                    write_bit(1)
                    low = 2 * (low - self.HALF)
                    high = 2 * (high - self.HALF)
                elif low >= self.QUARTER and high <= 3 * self.QUARTER:
                    pending_bits += 1
                    low = 2 * (low - self.QUARTER)
                    high = 2 * (high - self.QUARTER)
                else:
                    break

        # Flush remaining bits
        pending_bits += 1
        if low < self.QUARTER:
            write_bit(0)
        else:
            write_bit(1)

        # Pack bits into bytes
        bit_string = ''.join(map(str, bits_written))
        # Pad to byte boundary
        pad = (8 - len(bit_string) % 8) % 8
        bit_string += '0' * pad

        compressed = bytes(
            int(bit_string[i:i+8], 2)
            for i in range(0, len(bit_string), 8)
        )

        metadata = {
            'freq': freq,
            'cumulative': cumulative,
            'total': total,
            'n_symbols': len(data),
            'pad_bits': pad,
            'original_entropy_bits': sum(
                -p * np.log2(p) * len(data)
                for p in prob.values() if p > 0
            )
        }

        return compressed, metadata

    def compute_entropy(self, data: np.ndarray) -> float:
        """Compute Shannon entropy of the weight distribution."""
        _, counts = np.unique(data, return_counts=True)
        probs = counts / len(data)
        return -np.sum(probs * np.log2(probs + 1e-10))


