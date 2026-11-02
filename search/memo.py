# SPDX-License-Identifier: Apache-2.0
"""SHA-256 memo for official verifier results (research report §6.4 / IBM hash set), persisted per run.

Keys bind every input that can change the verification result: task, verification
mode (smoke vs full), verifier settings, shot count, optional submission identity,
and the circuit fingerprint. Smoke and full results live in separate namespaces so
a smoke pass can never satisfy a later full-verification request.

Two key namespaces share one store:

``verification_key``  one official verifier run on one circuit family (the ``.kmb``/``.npz`` bytes).
``program_key``       one evaluated program source (its SHA-256 plus the evaluator settings), so an
                      identical program is answered from the memo before any build or verifier run.

Persistence. Entries are appended as JSON lines to one file: the explicit ``path`` given to the
constructor, else ``$SEARCH_MEMO_PATH``, else ``$SEARCH_RUN_DIR/verifier_memo.jsonl`` (beside the
``evals/`` records), else nowhere (in-process only, as before). The path is resolved on every access,
so a memo created at import time follows the run directory search/run.py sets later, and the worker
processes of one run share the file: each write is one appended line, a miss re-reads the lines other
workers appended since the last read, and the first writer of a key wins. Negative outcomes (a
verifier FAIL, a timeout, a crashed child) are stored like any other value so they are never re-run;
``negative_hits`` counts them. ``SEARCH_MEMO_DISABLE=1`` turns the memo off entirely.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

MEMO_FILENAME = "verifier_memo.jsonl"


def code_fingerprint(files: Iterable[str | Path] = (), modules: Iterable[str] = ()) -> str:
    """Short digest of source files and of importable modules' origin files; missing ones are skipped.

    Bound into memo keys so that a change to the scoring, verifier or proxy code misses the memo
    instead of returning a stale result.
    """
    digest = hashlib.sha256()
    for path in files:
        try:
            digest.update(Path(path).read_bytes())
        except OSError:
            pass
    for name in modules:
        try:
            spec = importlib.util.find_spec(name)
            origin = getattr(spec, "origin", None)
            if origin and origin not in ("built-in", "frozen"):
                digest.update(name.encode("utf-8") + b"\0" + Path(origin).read_bytes())
        except (ImportError, OSError, ValueError, AttributeError):
            pass
    return digest.hexdigest()[:16]


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


def program_sha256(path: str | Path) -> str | None:
    """Hex SHA-256 of a program file's bytes, or ``None`` when it cannot be read."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def sibling_sources_digest(path: str | Path) -> str:
    """Digest of the other ``.py`` files beside ``path`` (name and content), or ``""`` when there are none.

    A script's own directory is first on ``sys.path``, so sibling modules are the one input a program's
    text does not capture; the evaluators bind this into the program memo key. OpenEvolve writes each
    program alone into a temp directory, so the loop pays nothing for it.
    """
    program = Path(path)
    digest = hashlib.sha256()
    found = False
    try:
        for sibling in sorted(program.parent.glob("*.py")):
            if sibling.name == program.name or not sibling.is_file():
                continue
            digest.update(sibling.name.encode("utf-8") + b"\0" + sibling.read_bytes() + b"\0")
            found = True
    except OSError:
        return ""
    return digest.hexdigest()[:16] if found else ""


def program_key(*, task: str, mode: str, program_sha256: str, settings: str = "") -> bytes:
    """Memo key for the whole evaluation of one program source.

    Binds the task, the smoke/full namespace, the SHA-256 of the program text and a digest of every
    evaluator setting that changes the outcome (declared input, shots, salt, caps, scoring code). The
    ``kind=program`` prefix keeps it apart from ``verification_key`` material.
    """
    if not mode:
        raise ValueError("program memo mode must be non-empty")
    if not program_sha256:
        raise ValueError("program_sha256 must be non-empty")
    parts = [
        b"kind=program",
        b"task=" + str(task).encode("utf-8"),
        b"mode=" + str(mode).encode("utf-8"),
        b"program=" + str(program_sha256).encode("ascii"),
        b"settings=" + str(settings).encode("utf-8"),
    ]
    return b"\0".join(parts)


def is_negative(value: Any) -> bool:
    """True for a stored outcome that is a verifier rejection, timeout or crash rather than a result."""
    if not isinstance(value, Mapping):
        return False
    status = str(value.get("status") or "").upper()
    if status.startswith(("FAIL", "ERROR", "TIMEOUT")):
        return True
    return status != "PASS" and bool(value.get("error"))


def memo_disabled() -> bool:
    return os.environ.get("SEARCH_MEMO_DISABLE") == "1"


class VerifierMemo:
    """Memo keyed by a verification or program identity, persisted as JSON lines.

    ``get`` / ``set`` / ``get_or_set`` accept either a prebuilt key (``bytes``) or
    legacy raw circuit bytes; callers that care about correctness must pass a
    ``verification_key(...)`` or ``program_key(...)`` result. ``path`` fixes the file;
    without it the environment decides (see the module docstring).
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._explicit_path = Path(path) if path else None
        self._store: dict[str, Any] = {}
        self._negative: set[str] = set()
        self._persisted: set[str] = set()
        self._loaded_path: Path | None = None
        self._offset = 0
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0
        self.negative_hits = 0

    # --- persistence ---------------------------------------------------------------------------

    @property
    def path(self) -> Path | None:
        """Where entries are persisted now, or ``None`` for an in-process memo."""
        if memo_disabled():
            return None
        if self._explicit_path is not None:
            return self._explicit_path
        explicit = os.environ.get("SEARCH_MEMO_PATH")
        if explicit:
            return Path(explicit)
        run_dir = os.environ.get("SEARCH_RUN_DIR")
        if run_dir:
            return Path(run_dir) / MEMO_FILENAME
        return None

    def _refresh(self) -> None:
        """Read lines appended to the file since the last read (our own and other workers')."""
        path = self.path
        if path is None:
            return
        if path != self._loaded_path:
            self._loaded_path = path
            self._offset = 0
        try:
            with path.open("rb") as stream:
                stream.seek(self._offset)
                data = stream.read()
        except OSError:
            return
        end = data.rfind(b"\n")
        if end < 0:
            return
        chunk = data[:end + 1]  # a line another worker is still writing waits for the next read
        self._offset += len(chunk)
        for line in chunk.splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict) or not isinstance(record.get("key"), str) or "value" not in record:
                continue
            key = record["key"]
            self._persisted.add(key)
            self._store.setdefault(key, record["value"])
            if record.get("negative"):
                self._negative.add(key)

    def _append(self, key: str, value: Any, negative: bool) -> None:
        path = self.path
        if path is None or key in self._persisted:
            return
        try:
            line = json.dumps({"key": key, "value": value, "negative": bool(negative), "ts": round(time.time(), 3)},
                              default=str, separators=(",", ":")) + "\n"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(line)
            self._persisted.add(key)
        except (OSError, TypeError, ValueError):
            pass

    def _put(self, key: str, value: Any, negative: bool | None) -> None:
        negative = is_negative(value) if negative is None else bool(negative)
        self._store[key] = value
        if negative:
            self._negative.add(key)
        self._append(key, value, negative)

    # --- API -----------------------------------------------------------------------------------

    def get(self, key_material: bytes) -> Any | None:
        """Return a cached value for ``key_material``, or ``None`` on a miss."""
        if memo_disabled():
            return None
        key = circuit_digest(key_material)
        with self._lock:
            if key not in self._store:
                self._refresh()
            if key in self._store:
                self.hits += 1
                if key in self._negative:
                    self.negative_hits += 1
                return self._store[key]
        return None

    def set(self, key_material: bytes, value: Any, *, negative: bool | None = None) -> Any:
        """Store ``value`` under ``key_material`` and return the stored value.

        The first writer wins, in this process and on disk, exactly as in ``get_or_set``: when another
        worker already persisted the key, its value is kept and returned instead of ``value``.
        ``negative`` marks a verifier rejection, timeout or crash; left ``None`` it is inferred from
        the value's ``status`` / ``error`` fields.
        """
        if memo_disabled():
            return value
        key = circuit_digest(key_material)
        with self._lock:
            self._refresh()
            if key in self._store:
                return self._store[key]
            self._put(key, value, negative)
            return value

    def get_or_set(self, key_material: bytes, factory: Callable[[], Any]) -> Any:
        """Return a cached value, or call ``factory`` once and store the result."""
        cached = self.get(key_material)
        if cached is not None:
            return cached
        with self._lock:
            self.misses += 1
        value = factory()
        if memo_disabled():
            return value
        key = circuit_digest(key_material)
        with self._lock:
            self._refresh()
            if key in self._store:  # another worker filled it meanwhile; prefer the first writer
                return self._store[key]
            self._put(key, value, None)
            return value

    def clear(self, *, persistent: bool = False) -> None:
        """Drop every in-memory entry and reset the counters; ``persistent`` also truncates the file."""
        with self._lock:
            self._store.clear()
            self._negative.clear()
            self._persisted.clear()
            self.hits = 0
            self.misses = 0
            self.negative_hits = 0
            self._offset = 0  # the next miss re-reads the whole file, as the docstring promises
            self._loaded_path = None
            path = self.path
            if persistent and path is not None:
                try:
                    path.write_text("", encoding="utf-8")
                except OSError:
                    pass
