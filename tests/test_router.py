"""Tests for the model router."""
import json
from types import SimpleNamespace

import pytest

import gsheets_agent.router as router_mod


def _resp(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_router_picks_light(monkeypatch, fake_openai_client):
    monkeypatch.setattr(router_mod, "FORCE_TIER", None)
    monkeypatch.setattr(router_mod, "LIGHT_MODEL", "light-x")
    monkeypatch.setattr(router_mod, "COMPLEX_MODEL", "complex-x")

    fake_openai_client.chat.completions.create.return_value = _resp(
        json.dumps({"tier": "light", "reason": "single read"})
    )
    tier, model, reason = router_mod.pick_tier("read A1:B2", fake_openai_client)
    assert tier == "light"
    assert model == "light-x"
    assert "single read" in reason


def test_router_picks_complex(monkeypatch, fake_openai_client):
    monkeypatch.setattr(router_mod, "FORCE_TIER", None)
    monkeypatch.setattr(router_mod, "LIGHT_MODEL", "light-x")
    monkeypatch.setattr(router_mod, "COMPLEX_MODEL", "complex-x")

    fake_openai_client.chat.completions.create.return_value = _resp(
        json.dumps({"tier": "complex", "reason": "multi-step"})
    )
    tier, model, _ = router_mod.pick_tier("dedupe and summarize", fake_openai_client)
    assert tier == "complex"
    assert model == "complex-x"


def test_router_defaults_to_complex_on_error(monkeypatch, fake_openai_client):
    monkeypatch.setattr(router_mod, "FORCE_TIER", None)
    monkeypatch.setattr(router_mod, "COMPLEX_MODEL", "complex-x")

    fake_openai_client.chat.completions.create.side_effect = RuntimeError("api down")
    tier, model, reason = router_mod.pick_tier("anything", fake_openai_client)
    assert tier == "complex"
    assert model == "complex-x"
    assert "router_error" in reason


def test_router_defaults_to_complex_on_garbage_response(monkeypatch, fake_openai_client):
    monkeypatch.setattr(router_mod, "FORCE_TIER", None)
    monkeypatch.setattr(router_mod, "COMPLEX_MODEL", "complex-x")
    monkeypatch.setattr(router_mod, "LIGHT_MODEL", "light-x")

    fake_openai_client.chat.completions.create.return_value = _resp("not json")
    tier, _, _ = router_mod.pick_tier("anything", fake_openai_client)
    assert tier == "complex"  # safer default


def test_force_tier_overrides_router(monkeypatch, fake_openai_client):
    monkeypatch.setattr(router_mod, "FORCE_TIER", "light")
    monkeypatch.setattr(router_mod, "LIGHT_MODEL", "light-x")
    tier, model, reason = router_mod.pick_tier("anything", fake_openai_client)
    assert tier == "light"
    assert model == "light-x"
    assert "FORCE_TIER" in reason
    fake_openai_client.chat.completions.create.assert_not_called()
