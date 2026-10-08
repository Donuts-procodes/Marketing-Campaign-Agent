from orchestrator.core.config import get_settings
from orchestrator.core.llm import build_chat_model
from orchestrator.schemas.api import BYOKConfig


def _model(llm):
    primary = getattr(llm, "runnable", llm)  # unwrap with_fallbacks
    return primary.model_name


def test_fast_flag_picks_the_light_model_and_main_stays_heavy(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "openai_api_key", "sk-test")
    monkeypatch.setattr(s, "llm_model", "gpt-4o")
    monkeypatch.setattr(s, "llm_fast_model", "gpt-4o-mini")
    assert _model(build_chat_model()) == "gpt-4o"
    assert _model(build_chat_model(fast=True)) == "gpt-4o-mini"

    monkeypatch.setattr(s, "llm_fast_model", "")
    assert _model(build_chat_model(fast=True)) == "gpt-4o", "empty fast model falls back to the main one"


def test_users_own_model_choice_is_never_swapped(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_fast_model", "gpt-4o-mini")
    byok = BYOKConfig(provider="openai", model="gpt-4o", api_key="sk-user")
    assert _model(build_chat_model(byok, fast=True)) == "gpt-4o"
