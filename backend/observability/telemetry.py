from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer


logger = logging.getLogger(__name__)
INSTRUMENTATION_NAME = "ielts-writing-agent"


def _environment_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    logger.warning("Invalid boolean value for %s; using default", name)
    return default


@dataclass(frozen=True)
class TelemetrySettings:
    disabled: bool
    exporter: str
    service_name: str
    otlp_endpoint: str | None

    @classmethod
    def from_environment(cls) -> "TelemetrySettings":
        return cls(
            disabled=_environment_flag("OTEL_SDK_DISABLED", True),
            exporter=os.getenv("OTEL_TRACES_EXPORTER", "console").strip().lower(),
            service_name=os.getenv(
                "OTEL_SERVICE_NAME",
                "ielts-writing-agent",
            ).strip(),
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or None,
        )


@dataclass
class TelemetryRuntime:
    enabled: bool
    provider: TracerProvider | None = None
    tracer: Tracer | None = None

    def shutdown(self) -> None:
        if self.provider is not None:
            self.provider.force_flush()
            self.provider.shutdown()


_runtime = TelemetryRuntime(enabled=False)


def _build_exporter(settings: TelemetrySettings) -> SpanExporter:
    if settings.exporter == "console":
        return ConsoleSpanExporter()
    if settings.exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        if settings.otlp_endpoint:
            return OTLPSpanExporter(endpoint=settings.otlp_endpoint)
        return OTLPSpanExporter()

    logger.warning(
        "Unknown OTEL_TRACES_EXPORTER=%s; using console exporter",
        settings.exporter,
    )
    return ConsoleSpanExporter()


def create_telemetry_runtime(
    settings: TelemetrySettings | None = None,
    span_exporter: SpanExporter | None = None,
) -> TelemetryRuntime:
    settings = settings or TelemetrySettings.from_environment()
    if settings.disabled or settings.exporter == "none":
        return TelemetryRuntime(enabled=False)

    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: settings.service_name})
    )
    exporter = span_exporter or _build_exporter(settings)
    if span_exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    return TelemetryRuntime(
        enabled=True,
        provider=provider,
        tracer=provider.get_tracer(INSTRUMENTATION_NAME),
    )


def initialize_telemetry(
    settings: TelemetrySettings | None = None,
    span_exporter: SpanExporter | None = None,
) -> TelemetryRuntime:
    global _runtime
    previous_runtime = _runtime
    _runtime = create_telemetry_runtime(settings, span_exporter)
    if previous_runtime.enabled:
        previous_runtime.shutdown()
    return _runtime


def shutdown_telemetry() -> None:
    global _runtime
    runtime = _runtime
    _runtime = TelemetryRuntime(enabled=False)
    runtime.shutdown()


def _qualified_exception_name(exception: Exception) -> str:
    exception_type = type(exception)
    return f"{exception_type.__module__}.{exception_type.__name__}"


class SanitizedTelemetryError(RuntimeError):
    """Exception representation that contains no provider or user message."""


def _record_safe_exception(span: Span, exception: Exception) -> None:
    error_type = _qualified_exception_name(exception)
    safe_exception = SanitizedTelemetryError(error_type).with_traceback(
        exception.__traceback__
    )
    span.record_exception(
        safe_exception,
        attributes={
            "error.type": error_type,
            "exception.escaped": True,
        },
        escaped=True,
    )
    span.set_status(Status(StatusCode.ERROR, description=error_type))
    span.set_attribute("error.type", error_type)


@contextmanager
def _start_span(
    name: str,
    attributes: dict[str, Any],
) -> Iterator[Span | None]:
    tracer = _runtime.tracer if _runtime.enabled else None
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(
        name,
        kind=SpanKind.INTERNAL,
        attributes=attributes,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except Exception as exception:
            _record_safe_exception(span, exception)
            raise


def workflow_span(
    workflow_name: str,
    session_source: str,
    checkpoint_backend: str,
):
    return _start_span(
        f"ielts.workflow.{workflow_name}",
        {
            "ielts.workflow.name": workflow_name,
            "ielts.session.source": session_source,
            "ielts.checkpoint.enabled": True,
            "ielts.checkpoint.backend": checkpoint_backend,
        },
    )


def node_span(node_name: str, tool_name: str | None = None):
    attributes: dict[str, Any] = {"ielts.node.name": node_name}
    if tool_name is not None:
        attributes["ielts.tool.name"] = tool_name
    return _start_span(f"ielts.node.{node_name}", attributes)


class _SanitizeUnhandledExceptionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            await self.app(scope, receive, send)
        except Exception as exception:
            error_type = _qualified_exception_name(exception)
            raise SanitizedTelemetryError(error_type) from None


def _safe_url(scope: dict[str, Any]) -> str:
    scheme = scope.get("scheme", "http")
    server = scope.get("server") or ("localhost", None)
    host = str(server[0])
    port = server[1]
    if port and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    return f"{scheme}://{host}{scope.get('path', '')}"


def _sanitize_server_request(span: Span, scope: dict[str, Any]) -> None:
    if not span or not span.is_recording():
        return

    if scope.get("client"):
        span.set_attribute("client.address", "[REDACTED]")
        span.set_attribute("client.port", 0)
        span.set_attribute("net.peer.ip", "[REDACTED]")
        span.set_attribute("net.peer.port", 0)

    if scope.get("headers"):
        span.set_attribute("user_agent.original", "[REDACTED]")
        span.set_attribute("http.user_agent", "[REDACTED]")

    if scope.get("query_string"):
        path = scope.get("path", "")
        safe_url = _safe_url(scope)
        span.set_attribute("http.target", path)
        span.set_attribute("http.url", safe_url)
        span.set_attribute("url.full", safe_url)
        span.set_attribute("url.query", "[REDACTED]")


def instrument_fastapi(app, runtime: TelemetryRuntime) -> None:
    if not runtime.enabled or runtime.provider is None:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    app.add_middleware(_SanitizeUnhandledExceptionMiddleware)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=runtime.provider,
        server_request_hook=_sanitize_server_request,
        http_capture_headers_server_request=["$^"],
        http_capture_headers_server_response=["$^"],
        http_capture_headers_sanitize_fields=[".*"],
        exclude_spans=["receive", "send"],
    )
