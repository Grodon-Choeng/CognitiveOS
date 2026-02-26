from types import SimpleNamespace

import pytest

import app.bot as bot_runtime


@pytest.mark.asyncio
async def test_start_bot_starts_enabled_providers(monkeypatch):
    started = []
    reminder_started = {"value": False}

    async def feishu_starter(**kwargs):
        started.append(("feishu", kwargs))

    async def discord_starter(**kwargs):
        started.append(("discord", kwargs))

    monkeypatch.setattr(bot_runtime.settings, "im_enabled", True)
    monkeypatch.setattr(
        bot_runtime.settings,
        "get_im_configs",
        lambda: [
            SimpleNamespace(provider=SimpleNamespace(value="feishu"), enabled=True),
            SimpleNamespace(provider=SimpleNamespace(value="discord"), enabled=False),
        ],
    )
    monkeypatch.setattr(
        bot_runtime,
        "CHANNEL_STARTERS",
        {"feishu": feishu_starter, "discord": discord_starter},
    )
    monkeypatch.setattr(
        bot_runtime,
        "start_reminder_checker",
        lambda: reminder_started.__setitem__("value", True),
    )

    await bot_runtime.start_bot()

    assert len(started) == 1
    assert started[0][0] == "feishu"
    assert "on_message_callback" in started[0][1]
    assert "on_alert_callback" in started[0][1]
    assert reminder_started["value"] is True


@pytest.mark.asyncio
async def test_stop_bot_stops_all_channels(monkeypatch):
    stopped = []
    reminder_stopped = {"value": False}

    async def stop_a():
        stopped.append("a")

    async def stop_b():
        stopped.append("b")

    monkeypatch.setattr(bot_runtime.settings, "im_enabled", True)
    monkeypatch.setattr(
        bot_runtime,
        "CHANNEL_STOPPERS",
        {"a": stop_a, "b": stop_b},
    )
    monkeypatch.setattr(
        bot_runtime,
        "stop_reminder_checker",
        lambda: reminder_stopped.__setitem__("value", True),
    )

    await bot_runtime.stop_bot()

    assert stopped == ["a", "b"]
    assert reminder_stopped["value"] is True
