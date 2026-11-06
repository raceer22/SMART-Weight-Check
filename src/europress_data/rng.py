"""Deterministic, order-independent random streams.

Every entity gets its own stream derived from (global seed, stream name, entity key), so results
do not depend on chunking, process count or generation order.
"""
from __future__ import annotations

import hashlib

import numpy as np


def _key_int(key: object) -> int:
    return int.from_bytes(hashlib.blake2b(str(key).encode(), digest_size=8).digest(), "little")


def rng_for(seed: int, *keys: object) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([int(seed)] + [_key_int(k) for k in keys]))


_M64 = (1 << 64) - 1


def _mix(x: int) -> int:
    """splitmix64 finaliser."""
    x = (x + 0x9E3779B97F4A7C15) & _M64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _M64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _M64
    return x ^ (x >> 31)


class KeyedRandom:
    """Counter-based random numbers keyed by (purpose, event key).

    The same physical event (e.g. 'the operator delay of a job scheduled at hour h') receives the same
    random draw in every policy simulated for the device. This gives true common random numbers across
    counterfactual actions and the realised history, independent of how many other draws happen.
    """

    def __init__(self, seed: int, *keys: object):
        self.base = _key_int((int(seed),) + tuple(keys))
        self._p = {}

    def u(self, purpose: str, *key: int) -> float:
        p = self._p.get(purpose)
        if p is None:
            p = self._p[purpose] = _key_int(purpose)
        x = _mix(self.base ^ p)
        for k in key:
            x = _mix(x ^ (int(k) & _M64))
        return (x >> 11) / float(1 << 53)

    def integers(self, lo: int, hi: int, purpose: str, *key) -> int:
        return lo + min(hi - lo - 1, int(self.u(purpose, *key) * (hi - lo)))

    def uniform(self, lo: float, hi: float, purpose: str, *key) -> float:
        return lo + (hi - lo) * self.u(purpose, *key)

    def random(self, purpose: str, *key) -> float:
        return self.u(purpose, *key)

    def poisson(self, lam: float, purpose: str, *key) -> int:
        u = self.u(purpose, *key)
        k, p = 0, np.exp(-lam)
        c = p
        while u > c and k < 50:
            k += 1
            p *= lam / k
            c += p
        return k

    def choice_p(self, p, purpose: str, *key) -> int:
        u = self.u(purpose, *key)
        c = np.cumsum(np.asarray(p, dtype=float) / np.sum(p))
        return int(min(np.searchsorted(c, u, side="right"), len(c) - 1))
