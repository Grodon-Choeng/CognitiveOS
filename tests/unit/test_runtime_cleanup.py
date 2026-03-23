import asyncio
from types import SimpleNamespace

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

    async def fake_run_listener() -> None:
        calls.append("start")

    monkeypatch.setattr(
        feishu_long_connection,
        "run_feishu_long_connection_listener",
        fake_run_listener,
    )
    monkeypatch.setattr(
        feishu_long_connection,
        "asyncio",
        SimpleNamespace(run=asyncio.run),
    )

    feishu_long_connection.main()

    assert calls == ["start"]


@pytest.mark.asyncio
async def test_run_feishu_long_connection_listener_cleans_up_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeListener:
        def start(self) -> None:
            calls.append("start")

    async def fake_cleanup(container: object) -> None:
        _ = container
        calls.append("cleanup")

    class FakeContainer:
        async def get(self, dependency: object) -> object:
            assert dependency is feishu_long_connection.FeishuLongConnectionListener
            return FakeListener()

    monkeypatch.setattr(feishu_long_connection, "get_settings", lambda: SimpleNamespace())
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
    monkeypatch.setattr(feishu_long_connection, "cleanup_runtime_resources", fake_cleanup)

    await feishu_long_connection.run_feishu_long_connection_listener()

    assert calls == ["logging", "start", "cleanup"]
