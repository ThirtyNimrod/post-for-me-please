from __future__ import annotations

import os
from typing import Any

import litellm

DEFAULT_AZURE_DEPLOYMENT = "gpt-4o"

ENV_AZURE_API_KEY = "AZURE_OPENAI_API_KEY"
ENV_AZURE_ENDPOINT = "AZURE_OPENAI_ENDPOINT"
ENV_AZURE_API_BASE = "AZURE_OPENAI_API_BASE"
ENV_AZURE_API_VERSION = "AZURE_OPENAI_API_VERSION"
ENV_AZURE_DEPLOYMENT = "AZURE_OPENAI_DEPLOYMENT"


def _first_non_empty(*names: str) -> str:
    """Return the first non-empty environment variable value."""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _set_if_present(name: str, value: str) -> None:
    """Set env var only when value is non-empty."""
    if value:
        os.environ[name] = value


def _normalize_azure_env_aliases() -> None:
    """Normalize alternate env names into canonical Azure OpenAI env vars.

    Canonical names:
    - AZURE_OPENAI_API_KEY
    - AZURE_OPENAI_ENDPOINT
    - AZURE_OPENAI_API_VERSION
    - AZURE_OPENAI_DEPLOYMENT

    Supported aliases:
    - API_KEY / AZURE_OPENAI_KEY
    - AZURE_ENDPOINT / AZURE_OPENAI_API_BASE
    - API_VERSION
    - AZURE_DEPLOYMENT

    NOTE: We deliberately do NOT set AZURE_OPENAI_ENDPOINT. LiteLLM reads
    that env var and converts it to an `azure_endpoint` kwarg passed to the
    underlying OpenAI SDK, which then surfaces as an "Unknown parameter" error
    from the Azure API. We use AZURE_OPENAI_API_BASE (→ api_base) only.
    """
    api_key = _first_non_empty(ENV_AZURE_API_KEY, "API_KEY", "AZURE_OPENAI_KEY")
    endpoint = _first_non_empty("AZURE_ENDPOINT", ENV_AZURE_API_BASE, ENV_AZURE_ENDPOINT)
    api_version = _first_non_empty(ENV_AZURE_API_VERSION, "API_VERSION")
    deployment = _first_non_empty(ENV_AZURE_DEPLOYMENT, "AZURE_DEPLOYMENT")

    _set_if_present(ENV_AZURE_API_KEY, api_key)
    # Only set API_BASE — never AZURE_OPENAI_ENDPOINT (see note above).
    _set_if_present(ENV_AZURE_API_BASE, endpoint)
    _set_if_present(ENV_AZURE_API_VERSION, api_version)
    _set_if_present(ENV_AZURE_DEPLOYMENT, deployment)

    # Scrub AZURE_OPENAI_ENDPOINT if it leaked in from the shell. LiteLLM
    # converts it to azure_endpoint which the API rejects as unknown.
    os.environ.pop(ENV_AZURE_ENDPOINT, None)


def _resolve_model() -> str:
    """Resolve model string for LiteLLM.

    Rules:
    - If MODEL includes provider prefix (e.g. "azure/gpt-5.2"), use as-is.
    - Else treat MODEL or AZURE deployment as Azure deployment name.
    - Fallback to DEFAULT_AZURE_DEPLOYMENT.
    """
    explicit_model = os.environ.get("MODEL", "").strip()
    if explicit_model and "/" in explicit_model:
        return explicit_model

    deployment = (
        os.environ.get(ENV_AZURE_DEPLOYMENT)
        or explicit_model
        or DEFAULT_AZURE_DEPLOYMENT
    )
    return f"azure/{deployment}"


def _azure_runtime_config() -> tuple[str, str, str]:
    """Return Azure runtime tuple: (endpoint, api_key, api_version)."""
    endpoint = _first_non_empty("AZURE_ENDPOINT", ENV_AZURE_API_BASE, ENV_AZURE_ENDPOINT)
    api_key = _first_non_empty(ENV_AZURE_API_KEY, "API_KEY", "AZURE_OPENAI_KEY")
    api_version = _first_non_empty(ENV_AZURE_API_VERSION, "API_VERSION")
    return endpoint, api_key, api_version


_normalize_azure_env_aliases()
_MODEL = _resolve_model()


def call_llm(
    prompt: str,
    *,
    system: str = "You are a helpful assistant.",
    max_tokens: int = 2048,
    temperature: float = 0.4,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Call the LLM and return the response text.

    Uses LiteLLM so the underlying provider is swappable via env vars.
    Raises on API errors — callers should catch and handle as appropriate.

    Args:
        prompt: The user-turn message.
        system: System prompt string.
        max_tokens: Max tokens for the completion.
        temperature: Sampling temperature (lower = more deterministic).
        response_format: Optional dict, e.g. {"type": "json_object"} to
            request structured JSON output where supported.
    """
    kwargs: dict[str, Any] = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    # Be explicit for Azure to avoid env-name ambiguity across SDK versions.
    if _MODEL.startswith("azure/"):
        azure_endpoint, azure_api_key, azure_api_version = _azure_runtime_config()

        if not azure_endpoint:
            raise RuntimeError(
                "Azure endpoint is missing. Set one of: "
                "AZURE_OPENAI_ENDPOINT, AZURE_ENDPOINT, AZURE_OPENAI_API_BASE."
            )

        # LiteLLM Azure uses api_base, api_key, api_version as completion() kwargs.
        kwargs["api_base"] = azure_endpoint
        if azure_api_key:
            kwargs["api_key"] = azure_api_key
        if azure_api_version:
            kwargs["api_version"] = azure_api_version

    if response_format is not None:
        kwargs["response_format"] = response_format

    response = litellm.completion(**kwargs)
    return response.choices[0].message.content or ""
