from typing import Any

_app_container: Any | None = None


def set_app_container(container: Any) -> None:
    global _app_container
    _app_container = container


def get_app_container() -> Any | None:
    return _app_container
