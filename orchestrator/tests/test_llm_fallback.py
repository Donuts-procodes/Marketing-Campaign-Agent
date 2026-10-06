"""
The chat model falls back to the small model (settings.llm_fallback_model) when the main one fails.
"""

import json

import httpx
import pytest

from orchestrator.core.config import get_settings
from orchestrator.core.llm import build_chat_model
from orchestrator.schemas.api import BYOKConfig
from orchestrator.schemas.research import DynamicParameterTaxonomy


def _completion(content: str, model: str) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@pytest.mark.asyncio
async def test_structured_call_falls_back_to_small_model(monkeypatch):
    import langchain_openai

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_model", "gpt-4o")
    monkeypatch.setattr(settings, "llm_fallback_model", "gpt-4o-mini")

    models_called: list[str] = []
    taxonomy = {"critical_jtbd_drivers": ["price"], "minor_attributes": ["sso"]}

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        models_called.append(model)
        if model == "gpt-4o":
            return httpx.Response(404, json={"error": {"message": "model not found", "type": "invalid_request_error"}})
        return httpx.Response(200, json=_completion(json.dumps(taxonomy), model))

    real_chat_openai = langchain_openai.ChatOpenAI

    class MockedChatOpenAI(real_chat_openai):  # type: ignore[misc, valid-type]
        def __init__(self, **kwargs):
            super().__init__(http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kwargs)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", MockedChatOpenAI)

    llm = build_chat_model()
    result = await llm.with_structured_output(DynamicParameterTaxonomy).ainvoke("build the taxonomy")

    assert models_called == ["gpt-4o", "gpt-4o-mini"]
    assert isinstance(result, DynamicParameterTaxonomy) and result.critical_jtbd_drivers == ["price"]


def test_no_fallback_when_disabled_or_same_model(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_model", "gpt-4o")

    monkeypatch.setattr(settings, "llm_fallback_model", "")
    assert not hasattr(build_chat_model(), "fallbacks")

    monkeypatch.setattr(settings, "llm_fallback_model", "gpt-4o")
    assert not hasattr(build_chat_model(), "fallbacks")


def test_byok_openai_fallback_uses_the_users_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "llm_fallback_model", "gpt-4o-mini")

    llm = build_chat_model(BYOKConfig(provider="openai", model="o3-mini", api_key="sk-user"))

    fallback = llm.fallbacks[0]
    assert fallback.model_name == "gpt-4o-mini"
    assert fallback.openai_api_key.get_secret_value() == "sk-user"
