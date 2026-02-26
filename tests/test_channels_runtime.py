from types import SimpleNamespace

from app.channels import runtime
from app.enums import IMProvider


def test_get_default_provider_uses_first_enabled_config(monkeypatch):
    cfg = SimpleNamespace(provider=SimpleNamespace(value="feishu"), enabled=True)
    monkeypatch.setattr(runtime.settings, "get_im_configs", lambda: [cfg])

    provider = runtime.get_default_provider()
    assert provider == IMProvider.FEISHU


def test_get_default_provider_falls_back_to_discord(monkeypatch):
    monkeypatch.setattr(runtime.settings, "get_im_configs", lambda: [])

    provider = runtime.get_default_provider()
    assert provider == IMProvider.DISCORD
