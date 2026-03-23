from types import SimpleNamespace
from typing import Any

import pytest

from app.bootstrap import feishu_long_connection, runtime, temporal


@pytest.mark.asyncio
async def test_cleanup_runtime_resources_resets_container_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeContainer:
        async def close(self) -> None:
            calls.append("close")

    async def fake_dispose_engine() -> None:
        calls.append("dispose")

    monkeypatch.setattr(runtime, "dispose_engine", fake_dispose_engine)

    await runtime.cleanup_runtime_resources(FakeContainer())  # type: ignore[arg-type]

    assert calls == ["close", "dispose"]


@pytest.mark.asyncio
async def test_run_temporal_worker_cleans_up_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeWorker:
        async def run(self) -> None:
            calls.append("worker_run")

    monkeypatch.setattr(temporal, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(temporal, "configure_logging", lambda settings: calls.append("logging"))
    monkeypatch.setattr(temporal, "configure_tracing", lambda settings: calls.append("tracing"))

    async def fake_create_temporal_client(settings: object) -> object:
        calls.append("client")
        return object()

    async def fake_cleanup(container: object) -> None:
        _ = container
        calls.append("cleanup")

    class FakeContainer:
        async def get(self, dependency: object) -> object:
            if dependency is temporal.MessagingAdapter:
                return object()
            if dependency is temporal.AsyncSessionFactory:
                return object()
            if dependency is temporal.MultiWorkflowEventRecorder:
                return object()
            raise AssertionError(f"unexpected dependency: {dependency}")

    monkeypatch.setattr(temporal, "create_temporal_client", fake_create_temporal_client)
    monkeypatch.setattr(temporal, "cleanup_runtime_resources", fake_cleanup)
    monkeypatch.setattr(temporal, "create_runtime_container", lambda settings: FakeContainer())
    monkeypatch.setattr(temporal, "create_worker", lambda **kwargs: FakeWorker())

    await temporal.run_temporal_worker()

    assert calls == ["logging", "tracing", "client", "worker_run", "cleanup"]


def test_feishu_long_connection_main_cleans_up_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeListener:
        def start(self) -> None:
            calls.append("start")

        async def stop(self) -> None:
            calls.append("stop")

    class FakeContainer:
        pass

    class FakeLoop:
        def __init__(self) -> None:
            self.closed = False

        def run_until_complete(self, coro: Any) -> Any:
            return asyncio_run(coro)

        def shutdown_asyncgens(self) -> Any:
            async def _noop() -> None:
                return None

            return _noop()

        def close(self) -> None:
            self.closed = True

    async def fake_resolve_listener(container: object) -> FakeListener:
        _ = container
        return FakeListener()

    async def fake_cleanup(container: object) -> None:
        _ = container
        calls.append("cleanup")

    monkeypatch.setattr(
        feishu_long_connection,
        "get_settings",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        feishu_long_connection,
        "configure_logging",
        lambda settings: calls.append("logging"),
    )
    monkeypatch.setattr(
        feishu_long_connection,
        "create_runtime_container",
        lambda settings: FakeContainer(),
    )
    fake_loop = FakeLoop()
    monkeypatch.setattr(
        feishu_long_connection,
        "_bind_feishu_ws_client_loop",
        lambda loop: calls.append("bind"),
    )
    monkeypatch.setattr(
        feishu_long_connection.asyncio,
        "new_event_loop",
        lambda: fake_loop,
    )
    monkeypatch.setattr(
        feishu_long_connection.asyncio,
        "set_event_loop",
        lambda loop: calls.append("set_loop" if loop is not None else "clear_loop"),
    )
    monkeypatch.setattr(
        feishu_long_connection,
        "_resolve_listener",
        fake_resolve_listener,
    )
    monkeypatch.setattr(
        feishu_long_connection,
        "cleanup_runtime_resources",
        fake_cleanup,
    )
    monkeypatch.setattr(
        feishu_long_connection,
        "_drain_pending_tasks",
        lambda loop: calls.append("drain"),
    )

    feishu_long_connection.main()

    assert calls == [
        "logging",
        "set_loop",
        "bind",
        "bind",
        "start",
        "stop",
        "cleanup",
        "drain",
        "clear_loop",
    ]
    assert fake_loop.closed is True


@pytest.mark.asyncio
async def test_resolve_feishu_long_connection_listener_from_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = object()

    class FakeContainer:
        async def get(self, dependency: object) -> object:
            assert dependency is feishu_long_connection.FeishuLongConnectionListener
            return listener

    resolved = await feishu_long_connection._resolve_listener(FakeContainer())  # type: ignore[arg-type]

    assert resolved is listener


def asyncio_run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


def test_bind_feishu_ws_client_loop_updates_sdk_global_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = SimpleNamespace(loop=None)
    fake_loop = object()

    monkeypatch.setattr(
        feishu_long_connection,
        "import_module",
        lambda module_name: fake_module,
    )

    feishu_long_connection._bind_feishu_ws_client_loop(fake_loop)  # type: ignore[arg-type]

    assert fake_module.loop is fake_loop
