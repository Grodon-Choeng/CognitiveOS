from dataclasses import dataclass
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings


@dataclass
class TaskResult:
    task_id: str
    status: str
    result: Any | None = None
    error: str | None = None


def get_redis_settings() -> RedisSettings:
    redis_url = settings.cache_url
    if redis_url.startswith("redis://"):
        parts = redis_url.replace("redis://", "").split("/")
        host_port = parts[0].split(":")
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 6379
        database = int(parts[1]) if len(parts) > 1 else 0
        return RedisSettings(host=host, port=port, database=database)
    return RedisSettings()


async def enqueue_task(func_name: str, *args, **kwargs) -> str:
    redis = await create_pool(get_redis_settings())
    job = await redis.enqueue_job(func_name, *args, **kwargs)
    await redis.close()
    return job.job_id


async def get_task_result(task_id: str) -> TaskResult | None:
    redis = await create_pool(get_redis_settings())
    job = await redis.get_job(task_id)

    if not job:
        await redis.close()
        return None

    result = TaskResult(task_id=task_id, status=job.status)

    if job.status == "complete":
        result.result = job.result
    elif job.status == "failed":
        result.error = str(job.result)

    await redis.close()
    return result
