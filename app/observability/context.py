import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import uuid4


@dataclass(slots=True, frozen=True)
class ObservabilityContext:
    trace_id: str | None = None
    chain_id: str | None = None
    request_id: str | None = None
    process_role: str | None = None
    service_run_id: str | None = None


_context_var: ContextVar[ObservabilityContext | None] = ContextVar(
    "cognitiveos_observability_context",
    default=None,
)


def get_observability_context() -> ObservabilityContext:
    current = _context_var.get() or ObservabilityContext()
    return ObservabilityContext(
        trace_id=current.trace_id,
        chain_id=current.chain_id,
        request_id=current.request_id,
        process_role=current.process_role or os.getenv("COGNITIVE_OS_PROCESS_ROLE") or "manual",
        service_run_id=current.service_run_id
        or os.getenv("COGNITIVE_OS_SERVICE_RUN_ID")
        or "manual",
    )


def bind_observability_context(
    *,
    trace_id: str | None = None,
    chain_id: str | None = None,
    request_id: str | None = None,
    process_role: str | None = None,
    service_run_id: str | None = None,
) -> Token[ObservabilityContext]:
    current = get_observability_context()
    return _context_var.set(
        ObservabilityContext(
            trace_id=trace_id if trace_id is not None else current.trace_id,
            chain_id=chain_id if chain_id is not None else current.chain_id,
            request_id=request_id if request_id is not None else current.request_id,
            process_role=process_role if process_role is not None else current.process_role,
            service_run_id=service_run_id
            if service_run_id is not None
            else current.service_run_id,
        )
    )


def reset_observability_context(token: Token[ObservabilityContext]) -> None:
    _context_var.reset(token)


def ensure_observability_context() -> Token[ObservabilityContext] | None:
    current = get_observability_context()
    if current.trace_id and current.chain_id and current.request_id:
        return None
    trace_id = current.trace_id or new_observability_id()
    chain_id = current.chain_id or trace_id
    request_id = current.request_id or new_observability_id()
    return bind_observability_context(
        trace_id=trace_id,
        chain_id=chain_id,
        request_id=request_id,
    )


def current_trace_fields() -> tuple[str | None, str | None, str | None]:
    context = get_observability_context()
    return context.trace_id, context.chain_id, context.request_id


def new_observability_id() -> str:
    return str(uuid4())
