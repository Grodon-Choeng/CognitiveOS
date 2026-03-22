from types import SimpleNamespace

import pytest

from app.bootstrap import feishu_long_connection, runtime, temporal


@pytest.mark.asyncio
async def test_cleanup_runtime_resources_resets_container_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_reset_container() -> None:
        calls.append("reset")

    async def fake_dispose_engine() -> None:
        calls.append("dispose")

    monkeypatch.setattr(runtime, "reset_container", fake_reset_container)
    monkeypatch.setattr(runtime, "dispose_engine", fake_dispose_engine)

    await runtime.cleanup_runtime_resources()

    assert calls == ["reset", "dispose"]


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

    async def fake_cleanup() -> None:
        calls.append("cleanup")

    fake_container = SimpleNamespace(
        session_factory=object(),
        build_messaging_adapter=lambda: object(),
        build_workflow_event_recorder=lambda: object(),
    )

    monkeypatch.setattr(temporal, "create_temporal_client", fake_create_temporal_client)
    monkeypatch.setattr(temporal, "cleanup_runtime_resources", fake_cleanup)
    monkeypatch.setattr(temporal, "get_container", lambda: fake_container)
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

    async def fake_cleanup() -> None:
        calls.append("cleanup")

    monkeypatch.setattr(feishu_long_connection, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(
        feishu_long_connection,
        "configure_logging",
        lambda settings: calls.append("logging"),
    )
    monkeypatch.setattr(
        feishu_long_connection,
        "get_container",
        lambda: SimpleNamespace(build_feishu_long_connection_listener=lambda: FakeListener()),
    )
    monkeypatch.setattr(feishu_long_connection, "cleanup_runtime_resources", fake_cleanup)

    feishu_long_connection.main()

    assert calls == ["logging", "start", "cleanup"]
