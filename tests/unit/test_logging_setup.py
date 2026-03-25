import logging
from pathlib import Path

from app.config.settings import Settings
from app.observability.context import bind_observability_context, reset_observability_context
from app.observability.logging import configure_logging


def test_configure_logging_writes_process_specific_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("COGNITIVE_OS_PROCESS_ROLE", "api")
    monkeypatch.setenv("COGNITIVE_OS_SERVICE_RUN_ID", "run-test-1")
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        log_file_enabled=True,
        log_dir=str(tmp_path),
    )

    configure_logging(settings)
    token = bind_observability_context(
        trace_id="trace-test-1",
        chain_id="chain-test-1",
        request_id="request-test-1",
        process_role="api",
        service_run_id="run-test-1",
    )
    try:
        logging.getLogger("tests.logging").info("写入文件日志")
    finally:
        reset_observability_context(token)

    log_path = tmp_path / "api.log"
    content = log_path.read_text(encoding="utf-8")

    assert "写入文件日志" in content
    assert "trace=trace-test-1" in content
    assert "chain=chain-test-1" in content
    assert "request=request-test-1" in content
