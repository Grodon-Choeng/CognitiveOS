import json
import subprocess
from pathlib import Path

import pytest

from app.bootstrap import services


class FakeProcess:
    def __init__(self, pid: int, poll_result: int | None = None) -> None:
        self.pid = pid
        self._poll_result = poll_result

    def poll(self) -> int | None:
        return self._poll_result


def test_resolve_services_supports_defaults_and_aliases() -> None:
    assert services.resolve_services(["all"], action="up") == ["infra", "migrate", "api", "worker"]
    assert services.resolve_services(["feishu_longconn,api"], action="up") == [
        "api",
        "feishu-longconn",
    ]
    assert services.resolve_services(["api,worker"], action="down") == ["worker", "api"]


def test_build_process_command_adds_reload_only_for_api() -> None:
    api_command = services.build_process_command("api", reload_api=True)
    worker_command = services.build_process_command("worker", reload_api=True)

    assert api_command[-1] == "--reload"
    assert worker_command == [services.sys.executable, "-m", "app.bootstrap.temporal"]


def test_up_starts_process_and_persists_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process_calls: list[list[str]] = []

    def fake_process_factory(command: list[str], **kwargs: object) -> FakeProcess:
        process_calls.append(command)
        process_env = kwargs.get("env")
        assert isinstance(process_env, dict)
        assert process_env["COGNITIVE_OS_PROCESS_ROLE"] == "api"
        assert process_env["COGNITIVE_OS_SERVICE_RUN_ID"].startswith("run-")
        return FakeProcess(pid=43210)

    monkeypatch.setattr(services, "_get_process_group_id", lambda pid: pid + 1)

    orchestrator = services.ServiceOrchestrator(
        project_root=tmp_path,
        runtime_root=tmp_path / ".runtime" / "services",
        process_factory=fake_process_factory,
        sleeper=lambda seconds: None,
    )

    reports = orchestrator.up(services=["api"], reload_api=True)

    assert reports[0].state == "started"
    assert process_calls[0][-1] == "--reload"
    state_path = tmp_path / ".runtime" / "services" / "state" / "api.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["pid"] == 43210
    assert payload["process_group_id"] == 43211
    assert payload["service_run_id"].startswith("run-")


def test_up_skips_already_running_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / ".runtime" / "services"
    state_root = runtime_root / "state"
    state_root.mkdir(parents=True)
    state_root.joinpath("api.json").write_text(
        json.dumps(
            {
                "service": "api",
                "pid": 12345,
                "process_group_id": 12345,
                "service_run_id": "run-existing-api",
                "command": ["python", "-m", "uvicorn", "app.main:app"],
                "reload_enabled": True,
                "log_path": str(runtime_root / "logs" / "api.log"),
                "started_at": "2026-03-25T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(services, "_is_process_running", lambda pid: pid == 12345)

    orchestrator = services.ServiceOrchestrator(
        project_root=tmp_path,
        runtime_root=runtime_root,
        sleeper=lambda seconds: None,
    )

    reports = orchestrator.up(services=["api"], reload_api=True)

    assert reports[0].state == "already_running"
    assert reports[0].pid == 12345
    assert reports[0].service_run_id == "run-existing-api"


def test_down_stops_process_and_cleans_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / ".runtime" / "services"
    state_root = runtime_root / "state"
    state_root.mkdir(parents=True)
    state_path = state_root / "worker.json"
    state_path.write_text(
        json.dumps(
            {
                "service": "worker",
                "pid": 22334,
                "process_group_id": 22335,
                "service_run_id": "run-existing-worker",
                "command": ["python", "-m", "app.bootstrap.temporal"],
                "reload_enabled": False,
                "log_path": str(runtime_root / "logs" / "worker.log"),
                "started_at": "2026-03-25T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    termination_calls: list[tuple[str, int]] = []

    monkeypatch.setattr(services, "_is_process_running", lambda pid: pid == 22334)
    monkeypatch.setattr(
        services,
        "_terminate_process_group",
        lambda process_group_id: termination_calls.append(("term", process_group_id)),
    )
    monkeypatch.setattr(services, "_wait_for_process_exit", lambda pid, timeout_seconds: True)

    orchestrator = services.ServiceOrchestrator(
        project_root=tmp_path,
        runtime_root=runtime_root,
        sleeper=lambda seconds: None,
    )

    reports = orchestrator.down(services=["worker"])

    assert reports[0].state == "stopped"
    assert termination_calls == [("term", 22335)]
    assert state_path.exists() is False


def test_status_reports_running_infra_services(tmp_path: Path) -> None:
    def fake_runner(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        _ = kwargs
        assert command[:4] == ["docker", "compose", "ps", "--services"]
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="postgres\nredis\ntemporal\ntemporal-ui\n",
            stderr="",
        )

    orchestrator = services.ServiceOrchestrator(
        project_root=tmp_path,
        runtime_root=tmp_path / ".runtime" / "services",
        command_runner=fake_runner,
    )

    reports = orchestrator.status(services=["infra"])

    assert reports[0].state == "running"
    assert "postgres" in (reports[0].detail or "")


def test_run_migrate_records_success_state(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        _ = kwargs
        calls.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    runtime_root = tmp_path / ".runtime" / "services"
    orchestrator = services.ServiceOrchestrator(
        project_root=tmp_path,
        runtime_root=runtime_root,
        command_runner=fake_runner,
    )

    reports = orchestrator.up(services=["migrate"])

    assert reports[0].state == "completed"
    assert calls[0][-3:] == ["-m", "alembic", "upgrade"] or "alembic" in calls[0]
    state_path = runtime_root / "state" / "migrate.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["success"] is True


def test_resolve_services_rejects_unknown_service() -> None:
    with pytest.raises(ValueError, match="不支持的服务名"):
        services.resolve_services(["unknown"], action="up")
