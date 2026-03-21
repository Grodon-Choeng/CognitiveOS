from app.bootstrap.container import get_container
from app.config.settings import get_settings
from app.observability.logging import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    listener = get_container().build_feishu_long_connection_listener()
    listener.start()


if __name__ == "__main__":
    main()
