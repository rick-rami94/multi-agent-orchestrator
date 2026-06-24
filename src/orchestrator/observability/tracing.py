"""Thin OpenTelemetry wrapper.

`span(...)` is a context manager that records an OTel span when the SDK is
installed/configured, and is otherwise a no-op — so instrumentation never
breaks the demo.
"""

from __future__ import annotations

from contextlib import contextmanager

from ..config import get_settings

_TRACER = None


def setup_tracing():
    """Configure an OTLP exporter if an endpoint is set; safe to call repeatedly."""
    global _TRACER
    if _TRACER is not None:
        return _TRACER
    settings = get_settings()
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        provider = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
        if settings.otel_exporter_otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        else:
            exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _TRACER = trace.get_tracer(settings.otel_service_name)
    except Exception:
        _TRACER = False  # sentinel: tried, unavailable
    return _TRACER


@contextmanager
def span(name: str, **attributes):
    tracer = setup_tracing()
    if not tracer:
        yield None
        return
    with tracer.start_as_current_span(name) as s:
        for k, v in attributes.items():
            s.set_attribute(k, str(v))
        yield s
