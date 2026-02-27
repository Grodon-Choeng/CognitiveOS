from collections.abc import Callable
from typing import Any

from app.channels import (
    get_discord_bot_status,
    get_feishu_bot_status,
    start_discord_bot,
    start_feishu_bot,
    stop_discord_bot,
    stop_feishu_bot,
)

StartFn = Callable[..., Any]
StopFn = Callable[[], Any]

CHANNEL_STARTERS: dict[str, StartFn] = {
    "discord": start_discord_bot,
    "feishu": start_feishu_bot,
}

CHANNEL_STOPPERS: dict[str, StopFn] = {
    "discord": stop_discord_bot,
    "feishu": stop_feishu_bot,
}

CHANNEL_STATUS_GETTERS: dict[str, Callable[[], Any]] = {
    "discord": get_discord_bot_status,
    "feishu": get_feishu_bot_status,
}
