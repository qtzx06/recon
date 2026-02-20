from contextlib import contextmanager
import time
from urllib.parse import urlparse

from .schemas import TraceStep
from .settings import settings

if settings.dd_trace_enabled:
    try:
        from ddtrace import tracer
        if settings.dd_trace_agent_url:
            parsed = urlparse(settings.dd_trace_agent_url)
            if parsed.scheme in {'http', 'https'} and parsed.hostname:
                tracer.configure(
                    hostname=parsed.hostname,
                    port=parsed.port or 8126,
                    https=(parsed.scheme == 'https'),
                )
            elif parsed.scheme == 'unix' and parsed.path:
                tracer.configure(uds_path=parsed.path)
    except Exception:  # pragma: no cover
        tracer = None
else:
    tracer = None


class TraceCollector:
    def __init__(self) -> None:
        self.steps: list[TraceStep] = []

    @contextmanager
    def step(self, name: str, detail: str | None = None):
        started = time.perf_counter()
        dd_span = None
        if tracer is not None:
            dd_span = tracer.trace(
                f'recon.{name}',
                service=settings.dd_service,
                resource=name,
            )
            dd_span.set_tag('env', settings.dd_env)
            dd_span.set_tag('version', settings.dd_version)
            if detail:
                dd_span.set_tag('detail', detail)
        ok = True
        err_msg = None
        try:
            yield
        except Exception as exc:
            ok = False
            err_msg = str(exc)
            if dd_span is not None:
                dd_span.set_tag('error', 1)
                dd_span.set_tag('error.msg', err_msg)
            raise
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.steps.append(
                TraceStep(
                    step=name,
                    duration_ms=duration_ms,
                    ok=ok,
                    detail=detail if ok else err_msg,
                )
            )
            if dd_span is not None:
                dd_span.finish()

    def as_list(self) -> list[TraceStep]:
        return self.steps
