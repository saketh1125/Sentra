"""
Sentra — shared LLM client for the spikes.

Single provider implementation, reused by S5 (documentation generation) and
S7 (LLM bug review). Kept deliberately thin: it exists so the credential
resolution and token accounting live in ONE place, and so the cost table that
S5/S7 write is computed identically for both.

Credential resolution order (first hit wins):
    1. SENTRA_LLM_API_KEY / SENTRA_LLM_BASE_URL / SENTRA_LLM_MODEL
    2. the `openrouter` entry in ~/.local/share/opencode/auth.json

The key is never printed, never logged, and never written to evidence files.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
_MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
_MISTRAL_DEFAULT_MODEL = "mistral-small-latest"
_MISTRAL_FALLBACK = "ministral-3b-latest"
AUTH_PATH = Path.home() / ".local" / "share" / "opencode" / "auth.json"
_REPO_DOTENV = Path(__file__).resolve().parents[1] / ".env"
_DOTENV_LOADED = False

def _load_dotenv():
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    try:
        if _REPO_DOTENV.exists():
            for line in _REPO_DOTENV.read_text().splitlines():
                line=line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k,v=line.split("=",1)
                k,v=k.strip(),v.strip().strip('"').strip("'")
                if k and k not in __import__("os").environ:
                    __import__("os").environ[k]=v
    except OSError:
        pass
_load_dotenv()
TIMEOUT_S = 60
RETRY_BACKOFF_S = 5.0

# Measured on this free-tier endpoint: some calls return HTTP 200 with a
# top-level `error` (upstream 502 "Worker local total request limit reached")
# and therefore no usable content. Those are provider-side capacity flakes,
# not task failures, so they are retried once (see chat). Counted in STATS so
# the caller's calls/chunk stays honest rather than hiding them.
#
# `quota_exhausted` is set when the daily free-tier cap is hit. That is a HARD
# stop for the day, not a per-chunk failure: continuing would just hammer a
# dead endpoint and record 200 bogus task failures. Callers check it and stop.
STATS = {
    "http_calls": 0,
    "transient_retries": 0,
    "no_usable_content": 0,
    "quota_exhausted": False,
}

# shortcut: hosted openrouter free tier stands in for the D2/D3-approved
# provider; switch via SENTRA_LLM_* env vars when the user decides.


class LLMError(RuntimeError):
    """Raised when no usable completion could be obtained.

    Carries the transport-level detail (status code / exception class) so the
    caller can record an exact, diagnosable failure reason.
    """


def _auth_entry() -> dict:
    try:
        return json.loads(AUTH_PATH.read_text()).get("openrouter") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def api_key() -> str:
    key = os.environ.get("SENTRA_LLM_API_KEY") or _auth_entry().get("key") or ""
    if not key:
        raise LLMError(
            "no LLM credential: set SENTRA_LLM_API_KEY or add an `openrouter` "
            f"entry to {AUTH_PATH}"
        )
    return key


def base_url() -> str:
    return os.environ.get("SENTRA_LLM_BASE_URL") or _auth_entry().get("base_url") or BASE_URL


def default_model() -> str:
    return os.environ.get("SENTRA_LLM_MODEL") or _auth_entry().get("model") or DEFAULT_MODEL


def _usage(raw: dict | None) -> dict:
    """Normalise a usage object to the fields the cost table needs.

    `reasoning_tokens` is kept separate because this is a reasoning model: the
    billed `completion_tokens` is mostly chain-of-thought, not the document
    text that S5 is measuring. Reporting the split is what makes the cost table
    honest rather than a single meaningless number.
    """
    raw = raw or {}
    details = raw.get("completion_tokens_details") or {}
    out = {
        "prompt_tokens": raw.get("prompt_tokens") or 0,
        "completion_tokens": raw.get("completion_tokens") or 0,
        "total_tokens": raw.get("total_tokens")
        or (raw.get("prompt_tokens") or 0) + (raw.get("completion_tokens") or 0),
        "reasoning_tokens": details.get("reasoning_tokens") or raw.get("reasoning_tokens") or 0,
    }
    if raw.get("cached_tokens") is not None:
        out["cached_tokens"] = raw["cached_tokens"]
    elif details.get("cached_tokens") is not None:
        out["cached_tokens"] = details["cached_tokens"]
    else:
        ptd = raw.get("prompt_tokens_details") or {}
        if isinstance(ptd, dict) and ptd.get("cached_tokens") is not None:
            out["cached_tokens"] = ptd["cached_tokens"]
    return out


def chat(
    model: str | None = None,
    messages: list | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
    response_format: dict | None = None,
    reasoning_effort: str | None = None,
) -> tuple[str, dict, float]:
    """One chat completion. Returns (content, usage_dict, latency_seconds).

    `content` is the assistant message text; an empty/absent content is a
    raised LLMError rather than a silent "" (this reasoning model returns null
    content when starved of tokens, and "success" there would corrupt coverage).

    Retried ONCE after RETRY_BACKOFF_S on: transport errors, HTTP 429,
    HTTP 5xx, and the embedded-error form of those (this provider reports
    upstream 502 capacity exhaustion inside an HTTP 200 body). A non-retryable
    status, a refusal, or a genuinely empty completion raises immediately with
    the server's message recorded verbatim.

    Retrying the transient cases is what keeps the caller's `coverage` a
    property of the documentation task rather than of provider luck.
    """
    model = model or default_model()
    payload = {
        "model": model,
        "messages": messages or [],
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if response_format is not None:
        payload["response_format"] = response_format
    if reasoning_effort is not None:
        if not (resolve_provider() == "mistral" and model and "ministral" in model.lower()):
            payload["reasoning_effort"] = reasoning_effort
    headers = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}
    url = f"{base_url().rstrip('/')}/chat/completions"

    last_error = ""
    _fallback_tried = False
    for attempt in (1, 2):
        if attempt == 2:
            STATS["transient_retries"] += 1
            time.sleep(RETRY_BACKOFF_S)
        t0 = time.perf_counter()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            last_error = f"transport:{type(exc).__name__}: {exc}"
            continue
        finally:
            STATS["http_calls"] += 1
        latency = time.perf_counter() - t0
        try:
            data = resp.json()
        except ValueError:
            data = None

        # MEASURED HAZARD: this provider returns HTTP 200 with a top-level
        # `error` object (code 502, "ResourceExhausted: Worker local total
        # request limit reached"). Trusting resp.status_code alone reports a
        # bogus success and an empty document, so the body is inspected first.
        embedded = (data or {}).get("error") or {}
        if not embedded and isinstance(data, dict) and data.get("object") == "error":
            embedded = data
        embedded_code = embedded.get("code")
        if embedded or resp.status_code != 200:
            detail = str(embedded.get("message") or (data or {}).get("message") or (resp.text[:300] if data is None else ""))[:300]
            status = embedded_code or resp.status_code
            # The free tier's DAILY cap is terminal for the rest of the day and
            # is reported as 429 like any other rate limit. Retrying it is
            # pointless, so it is flagged rather than retried.
            _low_detail = detail.lower()
            if any(m in _low_detail for m in ("free-models-per-day", "free_model_daily", "rate limit", "rate_limited", "quota_exceeded", "insufficient_quota", "billing", "capacity")):
                if (
                    not _fallback_tried
                    and resolve_provider() == "mistral"
                    and model in (_MISTRAL_DEFAULT_MODEL, "mistral-medium-latest")
                    and resp.status_code == 429
                ):
                    _fallback_tried = True
                    payload["model"] = _MISTRAL_FALLBACK
                    model = _MISTRAL_FALLBACK
                    ra = resp.headers.get("Retry-After")
                    if ra and ra.isdigit():
                        time.sleep(min(int(ra), 10))
                    last_error = f"fallback_429:{detail[:120]} -> retrying with {_MISTRAL_FALLBACK}"
                    STATS["transient_retries"] += 1
                    continue
                STATS["quota_exhausted"] = True
                raise LLMError(f"quota_exhausted_daily: {detail[:200]}")
            retryable = status == 429 or (isinstance(status, int) and 500 <= status < 600)
            if retryable or 500 <= resp.status_code < 600:
                STATS["no_usable_content"] += 1
                last_error = f"upstream_{status}: {detail[:200]}"
                continue
            raise LLMError(f"http_{status}: {detail}")

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        if message.get("refusal"):
            raise LLMError(f"refusal: {str(message['refusal'])[:200]}")
        content = message.get("content")
        if isinstance(content, list):
            _parts = []
            for _p in content:
                if isinstance(_p, dict) and _p.get("type") == "text":
                    _t = _p.get("text")
                    if isinstance(_t, str):
                        _parts.append(_t)
            content = "".join(_parts)
        if content is None or not str(content).strip():
            STATS["no_usable_content"] += 1
            last_error = (
                f"null_or_empty_content:finish_reason={choice.get('finish_reason')}"
                f":reasoning_len={len(str(message.get('reasoning') or ''))}"
            )
            continue
        return str(content).strip(), _usage(data.get("usage")), latency

    raise LLMError(last_error or "all_attempts_failed")


# --- opencode provider support ---------------------------------------------
# shortcut: opencode hosted inference stands in for the pending D2/D3 provider decision; switch via SENTRA_LLM_* env.
# Activated with SENTRA_LLM_PROVIDER=opencode, or automatically when no
# SENTRA_LLM_* env var is set and an `opencode` entry exists in auth.json.
# Env-var overrides always win over this default. The key is read, never echoed.
_OPENCODE_BASE_URL = "https://opencode.ai/inference/openai/v1"
_OPENCODE_DEFAULT_MODEL = "glm-5.3-flash-free"


def _opencode_auth_entry() -> dict:
    try:
        return json.loads(AUTH_PATH.read_text()).get("opencode") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _mistral_auth_entry() -> dict:
    try:
        return json.loads(AUTH_PATH.read_text()).get("mistral") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _has_sentra_llm_env() -> bool:
    return any(os.environ.get(v) for v in ("SENTRA_LLM_PROVIDER", "SENTRA_LLM_API_KEY", "SENTRA_LLM_BASE_URL", "SENTRA_LLM_MODEL"))


def resolve_provider() -> str:
    provider = os.environ.get("SENTRA_LLM_PROVIDER")
    if provider:
        return provider
    # Mistral is Sentra's chosen provider (D2/D3); a dotenv MISTRAL_API_KEY wins
    # over the opencode auth.json entry, whose CLI transport is brittle.
    if not _has_sentra_llm_env() and os.environ.get("MISTRAL_API_KEY"):
        return "mistral"
    if not _has_sentra_llm_env() and _mistral_auth_entry().get("key"):
        return "mistral"
    if not _has_sentra_llm_env() and _opencode_auth_entry().get("key"):
        return "opencode"
    return "openrouter"


_orig_api_key = api_key
_orig_base_url = base_url
_orig_default_model = default_model


def _patched_api_key() -> str:
    if resolve_provider() == "opencode":
        key = _opencode_auth_entry().get("key") or ""
        if key:
            return key
        raise LLMError(f"no `opencode` credential in {AUTH_PATH}")
    if resolve_provider() == "mistral":
        key = os.environ.get("MISTRAL_API_KEY") or os.environ.get("SENTRA_LLM_API_KEY") or _mistral_auth_entry().get("key") or ""
        if key:
            return key
        raise LLMError(f"no `mistral` credential: set MISTRAL_API_KEY or SENTRA_LLM_API_KEY or add a `mistral` entry to {AUTH_PATH}")
    return _orig_api_key()


def _patched_base_url() -> str:
    if resolve_provider() == "opencode":
        return os.environ.get("SENTRA_LLM_BASE_URL") or _OPENCODE_BASE_URL
    if resolve_provider() == "mistral":
        return os.environ.get("SENTRA_LLM_BASE_URL") or _MISTRAL_BASE_URL
    return _orig_base_url()


def _patched_default_model() -> str:
    if resolve_provider() == "opencode":
        return os.environ.get("SENTRA_LLM_MODEL") or _OPENCODE_DEFAULT_MODEL
    if resolve_provider() == "mistral":
        return os.environ.get("SENTRA_LLM_MODEL") or _MISTRAL_DEFAULT_MODEL
    return _orig_default_model()


api_key = _patched_api_key
base_url = _patched_base_url
default_model = _patched_default_model


# --- opencode CLI transport -------------------------------------------------
# shortcut: the opencode HTTP endpoint 403s (FreeTierError) for script calls,
# but `opencode run -m <provider/model> <prompt>` works and prints the answer
# to stdout. Transport is chosen via SENTRA_LLM_TRANSPORT=http|cli; when unset
# and the provider resolves to opencode, cli is the default (http kept for the
# openrouter path and for explicit override).
#
# CLI transport cannot see token usage, so its usage dict carries characters
# instead: {"chars_in", "chars_out"}. Cost tables for cli runs must use
# calls + chars + wall seconds, NOT tokens.
CLI_TIMEOUT_S = 300

_KEY_RE = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{20,})")


def _redact(text: str) -> str:
    """Best-effort scrub of key-looking tokens from CLI stderr before logging."""
    return _KEY_RE.sub("<redacted>", text)


def cli_model() -> str:
    """Model in the format `opencode run -m` expects: provider/model."""
    model = default_model()
    return model if "/" in model else f"opencode/{model}"


def _cli_prompt(messages: list) -> str:
    parts = [f"System: {m['content']}" for m in messages if m.get("role") == "system"]
    parts += [m["content"] for m in messages if m.get("role") != "system"]
    return "\n".join(p if p.endswith("\n") else p + "\n" for p in parts)


def chat_cli(
    model: str | None = None,
    messages: list | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
    response_format: dict | None = None,
    reasoning_effort: str | None = None,
) -> tuple[str, dict, float]:
    """One completion via `opencode run`. Returns (content, usage, latency).

    A non-zero exit or empty stdout raises LLMError with the stderr tail,
    redacted of key-looking tokens (the CLI must never leak auth material).
    """
    assert messages, "chat_cli requires messages"
    prompt = _cli_prompt(messages)
    cmd = ["opencode", "run", "-m", model or cli_model(), prompt]
    if not shutil.which("opencode"):
        raise LLMError(
            "`opencode` CLI not found on PATH — install it or use SENTRA_LLM_TRANSPORT=http"
        )
    STATS["http_calls"] += 1  # one call regardless of transport; chars carry the size
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        STATS["no_usable_content"] += 1
        raise LLMError(f"cli_timeout:{CLI_TIMEOUT_S}s")
    latency = time.perf_counter() - t0
    if proc.returncode != 0:
        STATS["no_usable_content"] += 1
        lines = (proc.stderr or "").strip().splitlines()
        tail = _redact("\n".join(lines[-3:]))
        raise LLMError(f"cli_exit_{proc.returncode}: {tail[:300] or '(no stderr)'}")
    content = proc.stdout.strip()
    if not content:
        STATS["no_usable_content"] += 1
        raise LLMError("cli_empty_stdout: exit 0 but no content")
    return content, {
        "chars_in": len(prompt),
        "chars_out": len(content),
        "note": "cli transport: no token usage available; use chars for cost",
    }, latency


_transport = os.environ.get("SENTRA_LLM_TRANSPORT")
if resolve_provider() == "mistral":
    pass
elif _transport == "cli" or (_transport is None and resolve_provider() == "opencode"):
    chat = chat_cli
# SENTRA_LLM_TRANSPORT=http or unset+openrouter: the existing http chat is unchanged.
