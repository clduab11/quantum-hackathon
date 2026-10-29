# SPDX-License-Identifier: Apache-2.0
"""SHA-256 memo for official verifier results (research report §6.4 / IBM hash set).

Keys bind every input that can change the verification result: task, verification
mode (smoke vs full), verifier settings, shot count, optional submission identity,
and the circuit fingerprint. Smoke and full results live in separate namespaces so
a smoke pass can never satisfy a later full-verification request.
"""
from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Mapping
from typing import Any


def circuit_digest(circuit_bytes: bytes) -> str:
    """Return the hex SHA-256 of raw circuit (or composite key) bytes."""
    return hashlib.sha256(circuit_bytes).hexdigest()


def verification_key(
    *,
    task: str,
    mode: str,
    circuit_fingerprint: bytes,
    shots: int | None = None,
    verifier_settings: str = "",
    submission_id: str = "",
) -> bytes:
    """Build a memo key that misses the cache when any verification input changes.

    ``mode`` must be ``\"smoke\"`` or ``\"full\"`` (or another caller-defined
    namespace). Smoke and full never share entries.
    """
    if mode not in {"smoke", "full"} and not mode:
        raise ValueError(f"verification mode must be non-empty, got {mode!r}")
    parts = [
        b"task=" + str(task).encode("utf-8"),
        b"mode=" + str(mode).encode("utf-8"),
        b"shots=" + (b"none" if shots is None else str(int(shots)).encode("ascii")),
        b"settings=" + str(verifier_settings).encode("utf-8"),
        b"submission=" + str(submission_id).encode("utf-8"),
        b"circuits=" + circuit_fingerprint,
    ]
    return b"\0".join(parts)


def settings_digest(settings: Mapping[str, Any] | None) -> str:
    """Stable short digest of verifier settings (salt, workers, flags, …)."""
    if not settings:
        return ""
    payload = "|".join(f"{k}={settings[k]!r}" for k in sorted(settings))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class VerifierMemo:
    """Process-local memo keyed by a verification identity (see ``verification_key``).

    ``get`` / ``set`` / ``get_or_set`` accept either a prebuilt key (``bytes``) or
    legacy raw circuit bytes; callers that care about correctness must pass a
    ``verification_key(...)`` result.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key_material: bytes) -> Any | None:
        """Return a cached value for ``key_material``, or ``None`` on a miss."""
        key = circuit_digest(key_material)
        with self._lock:
            if key in self._store:
                self.hits += 1
                return self._store[key]
        return None

    def set(self, key_material: bytes, value: Any) -> Any:
        """Store ``value`` under ``key_material`` and return it."""
        key = circuit_digest(key_material)
        with self._lock:
            self._store[key] = value
            return value

    def get_or_set(self, key_material: bytes, factory: Callable[[], Any]) -> Any:
        """Return a cached value, or call ``factory`` once and store the result."""
        key = circuit_digest(key_material)
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
        """Drop every cached entry and reset hit/miss counters."""
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0
