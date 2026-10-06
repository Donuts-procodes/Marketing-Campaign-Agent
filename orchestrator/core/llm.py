"""
Chat model factory — resolves the LLM used by agents from a user-supplied BYOK
config or, failing that, the server's configured OpenAI credentials. The model is
wrapped with a smaller OpenAI fallback model (settings.llm_fallback_model) that is
tried when the main model call fails.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import SecretStr

from orchestrator.core.config import get_settings

if TYPE_CHECKING:
    from orchestrator.schemas.api import BYOKConfig


class LLMConfigurationError(Exception):
    """Raised when no usable LLM can be built for the requested configuration."""


def has_llm_credentials(byok: BYOKConfig | None) -> bool:
    return bool((byok and byok.api_key) or get_settings().openai_api_key)


def build_chat_model(byok: BYOKConfig | None = None) -> Any:
    """Builds a LangChain chat model, preferring the user's own key, with a small-model fallback."""
    primary, primary_model = _build_primary(byok)
    fallback = _build_fallback(byok, primary_model)
    return primary.with_fallbacks([fallback]) if fallback is not None else primary


def _build_fallback(byok: BYOKConfig | None, primary_model: str) -> Any | None:
    """
    The fallback is an OpenAI model: it uses the user's OpenAI key when they brought one,
    otherwise the server's key. None when no fallback is configured or no key is available.
    """
    settings = get_settings()
    model = settings.llm_fallback_model
    if not model or model == primary_model:
        return None
    key = byok.api_key if byok and byok.provider == "openai" and byok.api_key else settings.openai_api_key
    if not key:
        return None
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model, temperature=settings.llm_temperature, api_key=SecretStr(key))


def _build_primary(byok: BYOKConfig | None) -> tuple[Any, str]:
    settings = get_settings()

    if byok is None or not byok.api_key:
        if not settings.openai_api_key:
            raise LLMConfigurationError("No OpenAI API key configured on the server.")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=SecretStr(settings.openai_api_key),
        ), settings.llm_model

    # Custom endpoints make the server issue requests to arbitrary user-supplied hosts.
    base_url = byok.custom_endpoint if settings.allow_custom_llm_endpoints else None

    if byok.provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=byok.model,
            temperature=settings.llm_temperature,
            api_key=SecretStr(byok.api_key),
            base_url=base_url,
        ), byok.model

    if byok.provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise LLMConfigurationError(
                "Anthropic keys need the 'langchain-anthropic' package installed on the server."
            ) from exc
        kwargs: dict[str, Any] = {}
        if base_url:
            kwargs["base_url"] = base_url
        return ChatAnthropic(
            model=byok.model,
            temperature=settings.llm_temperature,
            api_key=SecretStr(byok.api_key),
            **kwargs,
        ), byok.model

    if byok.provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise LLMConfigurationError(
                "Gemini keys need the 'langchain-google-genai' package installed on the server."
            ) from exc
        return ChatGoogleGenerativeAI(
            model=byok.model,
            temperature=settings.llm_temperature,
            google_api_key=SecretStr(byok.api_key),
        ), byok.model

    raise LLMConfigurationError(f"Unsupported LLM provider: {byok.provider}")
