# SPDX-License-Identifier: Apache-2.0
"""Subscription-backed LLM providers for the search loop. No API keys, no API spend.

claude_code
    One ``claude -p`` call per generation on the Claude Max OAuth session, stripped of tools, settings,
    hooks, MCP servers and skills so a call costs the prompt and nothing else. (OpenEvolve's stock
    provider loads the user's whole Claude Code context, about 80k tokens, on every call.) Cost and
    tokens come from the CLI's JSON result.

codex_app_server
    One ``codex app-server`` JSON-RPC session per generation on the ChatGPT (Codex) login: ephemeral
    thread, read-only sandbox, approvals never, an empty working directory, the system message as
    developer instructions. Tokens come from ``thread/tokenUsage/updated``; the account's rate-limit
    use from ``account/rateLimits/updated``. The client speaks the protocol published by
    ``codex app-server generate-json-schema`` (0.158.0); OpenEvolve's unreleased adapter informed the
    method names (notices/40-search.txt).

search/run.py installs these through ``LLMModelConfig.init_client``, which OpenEvolve pickles into its
worker processes, so the YAML keeps ``provider: claude_code`` / ``provider: codex_app_server``. Every
call appends one line to ``$SEARCH_RUN_DIR/llm_calls.jsonl`` for search/stats.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import subprocess
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from openevolve.llm.base import LLMInterface

logger = logging.getLogger(__name__)

RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "ratelimit", "usage limit", "usage_limit", "limit reached",
                      "429", "too many requests", "overloaded", "quota", "capacity")


class RateLimited(RuntimeError):
    """The subscription is throttled; wait SEARCH_RATE_LIMIT_BACKOFF seconds before the next attempt."""


class NoRetry(RuntimeError):
    """Retrying the same prompt cannot help (budget cap hit, not logged in)."""


def _cfg(model_cfg: Any, attr: str, default: Any) -> Any:
    value = getattr(model_cfg, attr, None)
    return default if value is None else value


def looks_rate_limited(message: str) -> bool:
    text = (message or "").lower()
    return any(marker in text for marker in RATE_LIMIT_MARKERS)


def record_call(entry: dict[str, Any]) -> None:
    run_dir = os.environ.get("SEARCH_RUN_DIR")
    if not run_dir:
        return
    try:
        path = Path(run_dir) / "llm_calls.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


class _SubscriptionLLM(LLMInterface):
    provider = "subscription"
    default_model = ""

    def __init__(self, model_cfg: Any = None):
        self.model = _cfg(model_cfg, "name", self.default_model)
        self.system_message = getattr(model_cfg, "system_message", None)
        self.timeout = int(_cfg(model_cfg, "timeout", 600))
        self.retries = int(_cfg(model_cfg, "retries", 2))
        self.retry_delay = float(_cfg(model_cfg, "retry_delay", 20))
        self.weight = _cfg(model_cfg, "weight", 1.0)
        self.rate_limit_backoff = float(os.environ.get("SEARCH_RATE_LIMIT_BACKOFF", "300"))
        self.last_usage: dict[str, Any] | None = None
        logger.info(f"Initialized {self.provider} provider with model {self.model}")

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        system = kwargs.pop("system_message", self.system_message) or ""
        return await self.generate_with_context(system, [{"role": "user", "content": prompt}], **kwargs)

    async def generate_with_context(self, system_message: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        user = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
        timeout = int(kwargs.get("timeout", self.timeout))
        loop = asyncio.get_event_loop()
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            started = time.monotonic()
            entry: dict[str, Any] = {"timestamp": time.time(), "provider": self.provider, "model": self.model,
                                     "attempt": attempt + 1, "prompt_chars": len(system_message) + len(user)}
            try:
                text, usage = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: self._call(system_message or "", user, timeout)),
                    timeout=timeout + 60,
                )
                self.last_usage = usage
                # `model` stays the configured alias so stats.py groups successes and failures together;
                # the id the backend reports goes under resolved_model.
                record_call({**entry, "ok": True, "seconds": round(time.monotonic() - started, 1),
                             "response_chars": len(text), **{k: v for k, v in usage.items() if k != "model"},
                             "resolved_model": usage.get("model")})
                return text
            except NoRetry as exc:
                record_call({**entry, "ok": False, "seconds": round(time.monotonic() - started, 1), "error": str(exc)})
                logger.error(f"{self.provider} {self.model}: {exc}")
                raise
            except RateLimited as exc:
                last_error = exc
                record_call({**entry, "ok": False, "seconds": round(time.monotonic() - started, 1),
                             "error": str(exc), "rate_limited": True})
                if attempt < self.retries:
                    logger.warning(f"{self.provider} {self.model} throttled ({exc}); "
                                   f"sleeping {self.rate_limit_backoff:.0f} s before attempt {attempt + 2}")
                    await asyncio.sleep(self.rate_limit_backoff)
            except (asyncio.TimeoutError, Exception) as exc:
                last_error = exc
                record_call({**entry, "ok": False, "seconds": round(time.monotonic() - started, 1), "error": str(exc)})
                if attempt < self.retries:
                    logger.warning(f"{self.provider} {self.model} attempt {attempt + 1} failed ({exc}); retrying")
                    await asyncio.sleep(self.retry_delay)
        raise RuntimeError(f"{self.provider} {self.model}: all {self.retries + 1} attempts failed: {last_error}")

    def _call(self, system: str, user: str, timeout: int) -> tuple[str, dict[str, Any]]:
        raise NotImplementedError


# --- claude -p -----------------------------------------------------------------------------------


def _last_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except ValueError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    return payload
            except ValueError:
                continue
    return None


class LeanClaudeCodeLLM(_SubscriptionLLM):
    provider = "claude_code"
    default_model = "sonnet"

    def __init__(self, model_cfg: Any = None):
        super().__init__(model_cfg)
        self.max_budget_usd = float(_cfg(model_cfg, "max_budget_usd", 2.0))
        self.claude_bin = os.environ.get("SEARCH_CLAUDE_BIN", "claude")

    def command(self, system: str) -> list[str]:
        cmd = [self.claude_bin, "-p", "--model", self.model, "--output-format", "json",
               "--no-session-persistence", "--tools", "", "--setting-sources", "", "--disable-slash-commands",
               "--strict-mcp-config", "--max-budget-usd", f"{self.max_budget_usd:.2f}"]
        if system:
            cmd += ["--system-prompt", system]
        return cmd

    def _call(self, system: str, user: str, timeout: int) -> tuple[str, dict[str, Any]]:
        if len(system.encode("utf-8")) > 120_000:  # Linux caps one argv element at 128 KiB (MAX_ARG_STRLEN)
            raise NoRetry("the system prompt no longer fits one argv element; trim search/DISCOVERY.md")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDECODE", "CLAUDE_CODE"))}
        try:
            proc = subprocess.run(self.command(system), input=user, capture_output=True, text=True,
                                  timeout=timeout, env=env, cwd=tempfile.gettempdir())
        except subprocess.TimeoutExpired:
            raise asyncio.TimeoutError(f"claude -p exceeded {timeout} s")
        payload = _last_json_object(proc.stdout)
        if payload is None:
            tail = (proc.stderr or proc.stdout or "").strip()[-600:]
            raise RateLimited(tail) if looks_rate_limited(tail) else RuntimeError(
                f"claude -p returned no JSON (exit {proc.returncode}): {tail}")
        text = payload.get("result") or ""
        usage = payload.get("usage") or {}
        prompt_tokens = int(usage.get("input_tokens", 0) or 0) + int(usage.get("cache_creation_input_tokens", 0) or 0) \
            + int(usage.get("cache_read_input_tokens", 0) or 0)
        completion_tokens = int(usage.get("output_tokens", 0) or 0)
        model_usage = payload.get("modelUsage") or {}
        last_usage = {
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cached_input_tokens": int(usage.get("cache_read_input_tokens", 0) or 0),
            "model": next(iter(model_usage), self.model), "cost_usd": payload.get("total_cost_usd"),
            "duration_api_ms": payload.get("duration_api_ms"),
        }
        subtype = str(payload.get("subtype") or "")
        if payload.get("is_error") or (subtype and subtype != "success"):
            message = f"claude -p {subtype or 'error'}: {(text or proc.stderr or '').strip()[:600]}"
            if "budget" in subtype:
                raise NoRetry(message)
            raise RateLimited(message) if looks_rate_limited(message) else RuntimeError(message)
        if not text.strip():
            raise RuntimeError(f"claude -p returned an empty result: {(proc.stderr or '')[-400:]}")
        return text, last_usage


# --- codex app-server ----------------------------------------------------------------------------


class _JsonRpcProcess:
    """Newline-delimited JSON-RPC over the stdio of one ``codex app-server`` process."""

    def __init__(self, argv: list[str], cwd: str | None):
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, cwd=cwd)
        self._next_id = 0
        self._messages: "queue.Queue[Any]" = queue.Queue()
        self._pending: deque = deque()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self) -> None:
        try:
            for line in self.proc.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if not line:
                    continue
                try:
                    self._messages.put(json.loads(line))
                except ValueError:
                    logger.debug(f"non-JSON line from codex app-server: {line[:200]}")
        except (ValueError, OSError):
            pass
        finally:
            self._messages.put(None)

    def stderr_tail(self) -> str:
        """The end of stderr, for error messages. Only called on failure paths, so the process is stopped
        first: reading stderr of a live process blocks until it exits."""
        try:
            if self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait(timeout=5)
            return ((self.proc.stderr.read() if self.proc.stderr else "") or "").strip()[-600:]
        except (ValueError, OSError, subprocess.TimeoutExpired):
            return ""

    def _send(self, payload: dict[str, Any]) -> None:
        try:
            self.proc.stdin.write(json.dumps(payload) + "\n")  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]
        except (ValueError, OSError) as exc:
            raise RuntimeError(f"cannot write to codex app-server: {exc}; {self.stderr_tail()}")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"method": method, "params": params or {}})

    def request(self, method: str, params: dict[str, Any] | None, deadline: float) -> Any:
        """Send a request; park every other message (notifications, server requests) for next_message."""
        self._next_id += 1
        request_id = self._next_id
        self._send({"id": request_id, "method": method, "params": params or {}})
        while True:
            message = self._read(deadline)
            if message.get("id") != request_id or "method" in message:
                self._pending.append(message)
                continue
            if "error" in message:
                error = message["error"] or {}
                raise RuntimeError(f"codex app-server rejected {method}: {error.get('code')}: {error.get('message')}")
            return message.get("result")

    def reply_error(self, request_id: Any, message: str) -> None:
        """Answer a server-to-client request we do not support, so the turn fails fast instead of waiting."""
        self._send({"id": request_id, "error": {"code": -32601, "message": message}})

    def next_message(self, deadline: float) -> dict[str, Any]:
        if self._pending:
            return self._pending.popleft()
        return self._read(deadline)

    def _read(self, deadline: float) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError("codex app-server did not finish in time")
        try:
            message = self._messages.get(timeout=remaining)
        except queue.Empty:
            raise asyncio.TimeoutError("codex app-server did not finish in time")
        if message is None:
            raise RuntimeError(f"codex app-server exited: {self.stderr_tail()}")
        return message

    def close(self) -> None:
        # Stop the process first: closing a pipe another thread is blocked reading deadlocks in CPython,
        # and the reader thread only returns once the process exits.
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
                self.proc.wait(timeout=5)
            except Exception:
                pass
        self._reader.join(timeout=5)
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                if stream:
                    stream.close()
            except (OSError, ValueError):
                pass


class CodexAppServerLLM(_SubscriptionLLM):
    provider = "codex_app_server"
    default_model = "gpt-6-sol"
    client_info = {"name": "quantum-hackathon-search", "title": "quantum-hackathon dfthcsos search loop",
                   "version": "0.1.0"}

    def __init__(self, model_cfg: Any = None):
        super().__init__(model_cfg)
        self.reasoning_effort = getattr(model_cfg, "reasoning_effort", None) or "medium"
        self.codex_bin = os.environ.get("SEARCH_CODEX_BIN", "codex")
        self._cwd: str | None = None

    @property
    def cwd(self) -> str:
        if self._cwd is None or not Path(self._cwd).is_dir():
            self._cwd = tempfile.mkdtemp(prefix="codex-empty-")
        return self._cwd

    def _call(self, system: str, user: str, timeout: int) -> tuple[str, dict[str, Any]]:
        deadline = time.monotonic() + timeout
        try:
            session = _JsonRpcProcess([self.codex_bin, "app-server"], cwd=self.cwd)
        except FileNotFoundError:
            raise NoRetry("the `codex` CLI is not on PATH; install it and run `codex login`")
        try:
            session.request("initialize", {"clientInfo": self.client_info}, deadline)
            session.notify("initialized")
            account = session.request("account/read", {}, deadline) or {}
            if (account.get("account") or {}).get("type") != "chatgpt":
                raise NoRetry("codex is not logged in with a ChatGPT account; run `codex login` in WSL")
            thread_params: dict[str, Any] = {"model": self.model, "approvalPolicy": "never", "sandbox": "read-only",
                                             "cwd": self.cwd, "ephemeral": True}
            if system:
                thread_params["developerInstructions"] = system
            thread = session.request("thread/start", thread_params, deadline) or {}
            thread_id = (thread.get("thread") or {}).get("id")
            if not thread_id:
                raise RuntimeError(f"codex app-server returned no thread id: {thread}")
            session.request("turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": user}],
                                           "effort": self.reasoning_effort}, deadline)
            texts: list[str] = []
            usage: dict[str, Any] = {}
            used_percent = None
            reported_error = None
            while True:
                message = session.next_message(deadline)
                method = message.get("method")
                params = message.get("params") or {}
                if message.get("id") is not None:
                    if method:  # a server-to-client request (approval, user input, tool call): decline it
                        logger.warning(f"codex app-server asked {method}; declining (non-interactive loop)")
                        session.reply_error(message["id"], f"{method} is not available in the search loop")
                    continue
                if method == "item/completed":
                    item = params.get("item") or {}
                    if item.get("type") == "agentMessage" and item.get("text"):
                        texts.append(str(item["text"]))
                elif method == "thread/tokenUsage/updated":
                    # the thread is fresh and ephemeral, so `total` is this generation; `last` would be
                    # only the final model response of a multi-step turn
                    token_usage = params.get("tokenUsage") or {}
                    usage = token_usage.get("total") or token_usage.get("last") or usage
                elif method == "account/rateLimits/updated":
                    primary = (params.get("rateLimits") or {}).get("primary") or {}
                    used_percent = primary.get("usedPercent", used_percent)
                elif method == "error":
                    reported_error = (params.get("error") or {}).get("message") or json.dumps(params)[:300]
                elif method == "turn/completed":
                    turn = params.get("turn") or {}
                    if turn.get("status") != "completed":
                        detail = (turn.get("error") or {}).get("message") or reported_error or turn.get("status")
                        message_text = f"codex turn {turn.get('status')}: {detail}"
                        raise RateLimited(message_text) if looks_rate_limited(str(detail)) else RuntimeError(message_text)
                    break
            text = "\n\n".join(texts).strip()
            if not text:
                raise RuntimeError(f"codex app-server returned no agent message; {session.stderr_tail()}")
            prompt_tokens = int(usage.get("inputTokens", 0) or 0)
            completion_tokens = int(usage.get("outputTokens", 0) or 0)
            last_usage = {
                "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                "total_tokens": int(usage.get("totalTokens", 0) or (prompt_tokens + completion_tokens)),
                "cached_input_tokens": int(usage.get("cachedInputTokens", 0) or 0),
                "reasoning_tokens": int(usage.get("reasoningOutputTokens", 0) or 0),
                "model": (thread.get("model") or self.model), "rate_limit_used_percent": used_percent,
                "reasoning_effort": self.reasoning_effort,
            }
            return text, last_usage
        finally:
            session.close()


# --- wiring --------------------------------------------------------------------------------------


def init_claude_code_client(model_cfg: Any) -> LLMInterface:
    return LeanClaudeCodeLLM(model_cfg)


def init_codex_app_server_client(model_cfg: Any) -> LLMInterface:
    return CodexAppServerLLM(model_cfg)


PROVIDERS = {"claude_code": init_claude_code_client, "codex_app_server": init_codex_app_server_client}


def install(config: Any) -> list[str]:
    """Point every model whose ``provider`` we implement at our factory; returns what was installed."""
    installed: list[str] = []
    seen: set[int] = set()
    for model in list(config.llm.models) + list(config.llm.evaluator_models):
        if id(model) in seen:
            continue
        seen.add(id(model))
        factory = PROVIDERS.get(getattr(model, "provider", None) or "")
        if factory is not None and getattr(model, "init_client", None) is None:
            model.init_client = factory
            installed.append(f"{model.provider}:{model.name}")
    return installed
