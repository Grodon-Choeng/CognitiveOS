import re
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DAY_OFFSETS = {
    "今天": 0,
    "明天": 1,
    "后天": 2,
}
_PERIOD_DEFAULT_HOUR = {
    "早上": 9,
    "上午": 9,
    "中午": 12,
    "下午": 15,
    "晚上": 20,
}
_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_TIME_RE = re.compile(
    r"(?P<hour>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})点"
    r"(?:(?P<minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})分?)?"
)


def parse_natural_schedule(
    text: str,
    *,
    now_provider: Callable[[], datetime],
    default_timezone: str,
) -> tuple[datetime, str] | None:
    normalized = _normalize_time_text(text)
    day_offset = _extract_day_offset(normalized)
    period = _extract_period(normalized)
    hour, minute = _extract_hour_minute(normalized)
    if day_offset is None and period is None and hour is None:
        return None

    timezone = ZoneInfo(default_timezone)
    current_time = now_provider().astimezone(timezone)
    target_date = (current_time + timedelta(days=day_offset or 0)).date()

    if hour is None:
        hour = _PERIOD_DEFAULT_HOUR.get(period or "", 9)
    if minute is None:
        minute = 0
    if period in {"下午", "晚上"} and hour < 12:
        hour += 12
    if period == "中午" and hour < 11:
        hour += 12

    remind_at = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=timezone,
    )
    return remind_at, default_timezone


def default_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def _normalize_time_text(text: str) -> str:
    normalized = text.strip()
    normalized = normalized.replace("明早", "明天早上")
    normalized = normalized.replace("今早", "今天早上")
    normalized = normalized.replace("今晚", "今天晚上")
    return normalized


def _extract_day_offset(text: str) -> int | None:
    for token, offset in _DAY_OFFSETS.items():
        if token in text:
            return offset
    return 0 if any(token in text for token in _PERIOD_DEFAULT_HOUR) else None


def _extract_period(text: str) -> str | None:
    for token in _PERIOD_DEFAULT_HOUR:
        if token in text:
            return token
    return None


def _extract_hour_minute(text: str) -> tuple[int | None, int | None]:
    matched = _TIME_RE.search(text)
    if matched is None:
        return None, None
    hour = _parse_chinese_number(matched.group("hour"))
    minute_text = matched.group("minute")
    minute = _parse_chinese_number(minute_text) if minute_text else 0
    return hour, minute


def _parse_chinese_number(value: str | None) -> int | None:
    if value is None:
        return None
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if value.startswith("十"):
        return 10 + _CHINESE_DIGITS.get(value[1], 0)
    if value.endswith("十"):
        return _CHINESE_DIGITS.get(value[0], 0) * 10
    if "十" in value and len(value) == 3:
        return _CHINESE_DIGITS.get(value[0], 0) * 10 + _CHINESE_DIGITS.get(value[2], 0)
    if len(value) == 1:
        return _CHINESE_DIGITS.get(value)
    return None
