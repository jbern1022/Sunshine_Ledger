"""Tests for the separate bill-layers model setting (OLLAMA_LAYERS_MODEL).

Layers (Bill Says / Interpretation / Expected Effect) can run a different,
larger model than summaries without an explicit override -- the setting
defaults to `ollama_model` so existing deployments that never set
OLLAMA_LAYERS_MODEL keep running layers on the same model as summaries.
"""

from app.config import Settings


def test_layers_model_defaults_to_ollama_model(monkeypatch):
    monkeypatch.delenv("OLLAMA_LAYERS_MODEL", raising=False)
    settings = Settings(ollama_model="llama3.1:8b")
    assert settings.ollama_layers_model == "llama3.1:8b"


def test_layers_model_env_override(monkeypatch):
    monkeypatch.setenv("OLLAMA_LAYERS_MODEL", "qwen2.5:14b")
    settings = Settings(ollama_model="llama3.1:8b")
    assert settings.ollama_layers_model == "qwen2.5:14b"
    monkeypatch.delenv("OLLAMA_LAYERS_MODEL", raising=False)
