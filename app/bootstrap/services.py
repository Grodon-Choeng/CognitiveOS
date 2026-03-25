import argparse
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / ".runtime" / "services"
STATE_ROOT = RUNTIME_ROOT / "state"
LOG_ROOT = RUNTIME_ROOT / "logs"

LOCAL_PROCESS_SERVICES = ("api", "worker", "feishu-longconn")
ONE_SHOT_SERVICES = ("migrate",)
ALL_SERVICES = ("infra", "migrate", "api", "worker", "feishu-longconn")
INFRA_SERVICES = ("postgres", "redis", "temporal", "temporal-ui")
SERVICE_START_ORDER = {name: index for index, name in enumerate(ALL_SERVICES)}
SERVICE_STOP_ORDER = {
    name: index for index, name in enumerate(("feishu-longconn", "worker", "api", "infra"))
}


@dataclass(slots=True, frozen=True)
class ProcessStateRecord:
    service: str
    pid: int
    process_group_id: int
    service_run_id: str
    command: list[str]
    reload_enabled: bool
    log_path: str
    started_at: str


@dataclass(slots=True, frozen=True)
class OneShotStateRecord:
    service: str
    success: bool
    executed_at: str
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class ServiceReport:
    service: str
    state: str
    detail: str | None = None
    pid: int | None = None
    service_run_id: str | None = None
    log_path: str | None = None
    reload_enabled: bool | None = None
    started_at: str | None = None


class ServiceOrchestrator:
    def __init__(
        self,
        *,
        project_root: Path | None = None,
        runtime_root: Path | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        process_factory: Callable[..., subprocess.Popen[str]] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.project_root = project_root or PROJECT_ROOT
        self.runtime_root = runtime_root or RUNTIME_ROOT
        self.state_root = self.runtime_root / "state"
        self.log_root = self.runtime_root / "logs"
        self.command_runner = command_runner or subprocess.run
        self.process_factory = process_factory or subprocess.Popen
        self.sleeper = sleeper or time.sleep

    def up(
        self,
        *,
        services: Sequence[str] | None = None,
        reload_api: bool = False,
    ) -> list[ServiceReport]:
        reports: list[ServiceReport] = []
        for service in resolve_services(services, action="up"):
            if service == "infra":
                reports.append(self._start_infra())
                continue
            if service == "migrate":
                reports.append(self._run_migrate())
                continue
            reports.append(self._start_process(service, reload_api=reload_api))
        return reports

    def down(
        self,
        *,
        services: Sequence[str] | None = None,
    ) -> list[ServiceReport]:
        reports: list[ServiceReport] = []
        for service in resolve_services(services, action="down"):
            if service == "infra":
                reports.append(self._stop_infra())
                continue
            if service == "migrate":
                reports.append(
                    ServiceReport(
                        service="migrate",
                        state="not_running",
                        detail="migrate 是一次性动作，没有常驻进程可停止。",
                    )
                )
                continue
            reports.append(self._stop_process(service))
        return reports

    def restart(
        self,
        *,
        services: Sequence[str] | None = None,
        reload_api: bool = False,
    ) -> list[ServiceReport]:
        selected = resolve_services(services, action="restart")
        reports: list[ServiceReport] = []
        reports.extend(self.down(services=selected))
        reports.extend(self.up(services=selected, reload_api=reload_api))
        return reports

    def status(
        self,
        *,
        services: Sequence[str] | None = None,
    ) -> list[ServiceReport]:
        reports: list[ServiceReport] = []
        for service in resolve_services(services, action="status"):
            if service == "infra":
                reports.append(self._status_infra())
                continue
            if service == "migrate":
                reports.append(self._status_migrate())
                continue
            reports.append(self._status_process(service))
        return reports

    def _start_infra(self) -> ServiceReport:
        running = set(self._list_running_infra_services())
        if running == set(INFRA_SERVICES):
            return ServiceReport(
                service="infra",
                state="already_running",
                detail="所有本地基础设施已在运行。",
            )
        self._run_command(["docker", "compose", "up", "-d", *INFRA_SERVICES])
        return ServiceReport(
            service="infra",
            state="started",
            detail="已执行 docker compose up -d。",
        )

    def _stop_infra(self) -> ServiceReport:
        running = set(self._list_running_infra_services())
        if not running:
            return ServiceReport(
                service="infra",
                state="not_running",
                detail="本地基础设施当前未运行。",
            )
        self._run_command(["docker", "compose", "stop", *INFRA_SERVICES])
        return ServiceReport(
            service="infra",
            state="stopped",
            detail="已停止本地基础设施容器。",
        )

    def _status_infra(self) -> ServiceReport:
        running = self._list_running_infra_services()
        if not running:
            return ServiceReport(
                service="infra",
                state="stopped",
                detail="没有检测到正在运行的基础设施容器。",
            )
        if set(running) == set(INFRA_SERVICES):
            return ServiceReport(
                service="infra",
                state="running",
                detail="运行中：" + ", ".join(running),
            )
        return ServiceReport(
            service="infra",
            state="partial",
            detail="部分运行中：" + ", ".join(running),
        )

    def _run_migrate(self) -> ServiceReport:
        try:
            self._run_command([sys.executable, "-m", "alembic", "upgrade", "head"])
        except RuntimeError as exc:
            self._save_one_shot_state(
                OneShotStateRecord(
                    service="migrate",
                    success=False,
                    executed_at=_now_isoformat(),
                    detail=str(exc),
                )
            )
            raise

        record = OneShotStateRecord(
            service="migrate",
            success=True,
            executed_at=_now_isoformat(),
            detail="数据库 migration 已执行到 head。",
        )
        self._save_one_shot_state(record)
        return ServiceReport(
            service="migrate",
            state="completed",
            detail=record.detail,
            started_at=record.executed_at,
        )

    def _status_migrate(self) -> ServiceReport:
        record = self._load_one_shot_state("migrate")
        if record is None:
            return ServiceReport(
                service="migrate",
                state="unknown",
                detail="尚未记录本地 migrate 执行结果。",
            )
        return ServiceReport(
            service="migrate",
            state="completed" if record.success else "failed",
            detail=record.detail,
            started_at=record.executed_at,
        )

    def _start_process(
        self,
        service: str,
        *,
        reload_api: bool,
    ) -> ServiceReport:
        existing = self._load_process_state(service)
        if existing is not None and _is_process_running(existing.pid):
            return ServiceReport(
                service=service,
                state="already_running",
                detail="检测到已有运行中的本地进程。",
                pid=existing.pid,
                service_run_id=existing.service_run_id,
                log_path=existing.log_path,
                reload_enabled=existing.reload_enabled,
                started_at=existing.started_at,
            )
        if existing is not None:
            self._delete_state_file(service)

        command = build_process_command(service, reload_api=reload_api)
        service_run_id = _new_service_run_id()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.log_root.mkdir(parents=True, exist_ok=True)
        log_path = self._log_path(service)
        process_env = {
            **os.environ,
            "COGNITIVE_OS_PROCESS_ROLE": _service_process_role(service),
            "COGNITIVE_OS_SERVICE_RUN_ID": service_run_id,
        }
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(
                f"\n[{_now_isoformat()}] 启动 {service}：{' '.join(command)}\n"
            )
            process = self.process_factory(
                command,
                cwd=self.project_root,
                env=process_env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )

        self.sleeper(0.2)
        if process.poll() is not None:
            raise RuntimeError(
                f"{service} 启动失败，进程已立即退出。最近日志：\n{self._read_log_tail(log_path)}"
            )

        process_group_id = _get_process_group_id(process.pid)
        record = ProcessStateRecord(
            service=service,
            pid=process.pid,
            process_group_id=process_group_id,
            service_run_id=service_run_id,
            command=command,
            reload_enabled=reload_api if service == "api" else False,
            log_path=str(log_path),
            started_at=_now_isoformat(),
        )
        self._save_process_state(record)
        return ServiceReport(
            service=service,
            state="started",
            detail="启动成功。",
            pid=record.pid,
            service_run_id=record.service_run_id,
            log_path=record.log_path,
            reload_enabled=record.reload_enabled,
            started_at=record.started_at,
        )

    def _stop_process(self, service: str) -> ServiceReport:
        record = self._load_process_state(service)
        if record is None:
            return ServiceReport(
                service=service,
                state="not_running",
                detail="没有找到本地进程状态文件。",
            )
        if not _is_process_running(record.pid):
            self._delete_state_file(service)
            return ServiceReport(
                service=service,
                state="stopped",
                detail="检测到陈旧 PID 文件，已清理。",
            )

        _terminate_process_group(record.process_group_id)
        if not _wait_for_process_exit(record.pid, timeout_seconds=5.0):
            _kill_process_group(record.process_group_id)
            _wait_for_process_exit(record.pid, timeout_seconds=2.0)

        self._delete_state_file(service)
        return ServiceReport(
            service=service,
            state="stopped",
            detail="本地进程已停止。",
        )

    def _status_process(self, service: str) -> ServiceReport:
        record = self._load_process_state(service)
        if record is None:
            return ServiceReport(
                service=service,
                state="stopped",
                detail="未发现本地进程状态文件。",
            )
        if not _is_process_running(record.pid):
            self._delete_state_file(service)
            return ServiceReport(
                service=service,
                state="stopped",
                detail="检测到陈旧 PID 文件，已清理。",
            )
        return ServiceReport(
            service=service,
            state="running",
            detail="本地进程运行中。",
            pid=record.pid,
            service_run_id=record.service_run_id,
            log_path=record.log_path,
            reload_enabled=record.reload_enabled,
            started_at=record.started_at,
        )

    def _run_command(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return self.command_runner(
                list(command),
                cwd=self.project_root,
                check=True,
                text=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            detail = stderr or stdout or f"{exc.cmd} exited with code {exc.returncode}"
            raise RuntimeError(detail) from exc

    def _list_running_infra_services(self) -> list[str]:
        result = self.command_runner(
            ["docker", "compose", "ps", "--services", "--filter", "status=running"],
            cwd=self.project_root,
            check=True,
            text=True,
            capture_output=True,
        )
        services = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return [service for service in services if service in INFRA_SERVICES]

    def _save_process_state(self, record: ProcessStateRecord) -> None:
        path = self._state_path(record.service)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_process_state(self, service: str) -> ProcessStateRecord | None:
        path = self._state_path(service)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ProcessStateRecord(
            service=str(payload["service"]),
            pid=int(payload["pid"]),
            process_group_id=int(payload["process_group_id"]),
            service_run_id=str(payload["service_run_id"]),
            command=[str(item) for item in payload["command"]],
            reload_enabled=bool(payload["reload_enabled"]),
            log_path=str(payload["log_path"]),
            started_at=str(payload["started_at"]),
        )

    def _save_one_shot_state(self, record: OneShotStateRecord) -> None:
        path = self._state_path(record.service)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_one_shot_state(self, service: str) -> OneShotStateRecord | None:
        path = self._state_path(service)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return OneShotStateRecord(
            service=str(payload["service"]),
            success=bool(payload["success"]),
            executed_at=str(payload["executed_at"]),
            detail=_optional_str(payload.get("detail")),
        )

    def _delete_state_file(self, service: str) -> None:
        path = self._state_path(service)
        if path.exists():
            path.unlink()

    def _state_path(self, service: str) -> Path:
        return self.state_root / f"{service}.json"

    def _log_path(self, service: str) -> Path:
        return self.log_root / f"{service}.log"

    @staticmethod
    def _read_log_tail(path: Path, line_limit: int = 20) -> str:
        if not path.exists():
            return "暂无日志。"
        lines = path.read_text(encoding="utf-8").splitlines()
        return "\n".join(lines[-line_limit:]) if lines else "暂无日志。"


def resolve_services(
    services: Sequence[str] | None,
    *,
    action: str,
) -> list[str]:
    raw_values: list[str] = []
    if services:
        for value in services:
            raw_values.extend(segment for segment in value.split(",") if segment.strip())
    normalized = [_normalize_service_name(value) for value in raw_values if value.strip()]

    if not normalized or "all" in normalized:
        if action == "up":
            return ["infra", "migrate", "api", "worker"]
        if action == "down":
            return ["feishu-longconn", "worker", "api", "infra"]
        if action == "restart":
            return ["infra", "migrate", "api", "worker"]
        if action == "status":
            return ["infra", "migrate", "api", "worker", "feishu-longconn"]
        raise ValueError(f"不支持的 action：{action}")

    for service in normalized:
        if service not in ALL_SERVICES:
            raise ValueError(f"不支持的服务名：{service}")

    if action == "down":
        return sorted(set(normalized), key=lambda item: SERVICE_STOP_ORDER.get(item, 999))
    return sorted(set(normalized), key=lambda item: SERVICE_START_ORDER[item])


def build_process_command(service: str, *, reload_api: bool) -> list[str]:
    if service == "api":
        command = [sys.executable, "-m", "uvicorn", "app.main:app"]
        if reload_api:
            command.append("--reload")
        return command
    if service == "worker":
        return [sys.executable, "-m", "app.bootstrap.temporal"]
    if service == "feishu-longconn":
        return [sys.executable, "-m", "app.bootstrap.feishu_long_connection"]
    raise ValueError(f"{service} 不是可启动的本地常驻进程。")


def print_reports(reports: Sequence[ServiceReport]) -> None:
    for report in reports:
        parts = [f"[{report.service}] {report.state}"]
        if report.pid is not None:
            parts.append(f"pid={report.pid}")
        if report.service_run_id is not None:
            parts.append(f"run={report.service_run_id}")
        if report.reload_enabled is not None:
            parts.append(f"reload={'on' if report.reload_enabled else 'off'}")
        if report.started_at is not None:
            parts.append(f"time={report.started_at}")
        if report.log_path is not None:
            parts.append(f"log={report.log_path}")
        if report.detail:
            parts.append(report.detail)
        print(" | ".join(parts))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CognitiveOS 服务编排器")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("up", "down", "status", "restart"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument(
            "--services",
            nargs="*",
            default=["all"],
            help="服务列表，可传 all 或逗号分隔值，例如 infra,migrate,api,worker",
        )
        if command in {"up", "restart"}:
            subparser.add_argument(
                "--reload",
                action="store_true",
                help="仅对 api 启用 uvicorn reload",
            )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    orchestrator = ServiceOrchestrator()

    try:
        if args.command == "up":
            reports = orchestrator.up(services=args.services, reload_api=args.reload)
        elif args.command == "down":
            reports = orchestrator.down(services=args.services)
        elif args.command == "restart":
            reports = orchestrator.restart(services=args.services, reload_api=args.reload)
        elif args.command == "status":
            reports = orchestrator.status(services=args.services)
        else:
            parser.error(f"未知命令：{args.command}")
            return 2
    except Exception as exc:
        print(f"启动编排失败：{exc}", file=sys.stderr)
        return 1

    print_reports(reports)
    return 0


def _normalize_service_name(value: str) -> str:
    normalized = value.strip().casefold().replace("_", "-")
    return normalized or "all"


def _now_isoformat() -> str:
    return datetime.now(UTC).isoformat()


def _optional_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _new_service_run_id() -> str:
    return f"run-{uuid4()}"


def _service_process_role(service: str) -> str:
    if service in LOCAL_PROCESS_SERVICES:
        return service
    return "orchestrator"


def _is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_process_group(process_group_id: int) -> None:
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return


def _kill_process_group(process_group_id: int) -> None:
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        return


def _wait_for_process_exit(pid: int, *, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not _is_process_running(pid):
            return True
        time.sleep(0.1)
    return not _is_process_running(pid)


def _get_process_group_id(pid: int) -> int:
    try:
        return os.getpgid(pid)
    except OSError:
        return pid


if __name__ == "__main__":
    raise SystemExit(main())
