# SPDX-License-Identifier: Apache-2.0
"""SHA-256 memo for official verifier results (research report §6.4 / IBM hash set)."""
from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from typing import Any


def circuit_digest(circuit_bytes: bytes) -> str:
    return hashlib.sha256(circuit_bytes).hexdigest()


class VerifierMemo:
    """Process-local memo keyed by the SHA-256 of the circuit bytes."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, circuit_bytes: bytes) -> Any | None:
        key = circuit_digest(circuit_bytes)
        with self._lock:
            if key in self._store:
                self.hits += 1
                return self._store[key]
        return None

    def set(self, circuit_bytes: bytes, value: Any) -> Any:
        key = circuit_digest(circuit_bytes)
        with self._lock:
            self._store[key] = value
            return value

    def get_or_set(self, circuit_bytes: bytes, factory: Callable[[], Any]) -> Any:
        key = circuit_digest(circuit_bytes)
        with self._lock:
            if key in self._store:
                self.hits += 1
                return self._store[key]
            self.misses += 1
        value = factory()
        with self._lock:
            # Another worker may have filled it; prefer the first writer.
            return self._store.setdefault(key, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0
