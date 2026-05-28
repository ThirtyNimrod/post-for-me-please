"""Central factory for LLM instances. All nodes call LLMManager — never instantiate directly."""

from __future__ import annotations

import os
from functools import lru_cache

from langchain_openai import AzureChatOpenAI


class MissingEnvError(RuntimeError):
    pass


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise MissingEnvError(f"Missing required env var: {name}")
    return val


@lru_cache(maxsize=8)
def _build(deployment: str, temperature: float, max_tokens: int) -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=deployment,
        api_version=_require("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=_require("AZURE_OPENAI_ENDPOINT"),
        api_key=_require("AZURE_OPENAI_API_KEY"),
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=60,
        max_retries=2,
    )


class LLMManager:
    """One place to configure model deployments + decoding params per purpose.

    Why centralize: swapping models (Azure → Anthropic, GPT-4o → GPT-4o-mini) should
    be a one-file change. Nodes ask for a purpose, not a model.
    """

    @staticmethod
    def _deployment() -> str:
        return os.environ.get("AZURE_OPENAI_DEPLOYMENT_GPT4O", "gpt-4o")

    @classmethod
    def for_split(cls) -> AzureChatOpenAI:
        # Low temp — output is structured JSON, no creativity wanted.
        return _build(cls._deployment(), temperature=0.1, max_tokens=4000)

    @classmethod
    def for_generate(cls) -> AzureChatOpenAI:
        # Higher temp — posts should vary in voice across the three angles.
        return _build(cls._deployment(), temperature=0.7, max_tokens=1500)

    @classmethod
    def for_docs_summary(cls) -> AzureChatOpenAI:
        return _build(cls._deployment(), temperature=0.2, max_tokens=300)
