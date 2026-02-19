import datetime


def utc_time() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)
