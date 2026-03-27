from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from sentry_sdk.integrations.opentelemetry import SentrySpanProcessor

from multichannel_gateway.app.config import TelemetrySettings


def setup_tracing(app: FastAPI, settings: TelemetrySettings) -> None:
    # If telemetry is disabled, a no-op provider is used
    if not settings.otel_enabled:
        trace.set_tracer_provider(trace.NoOpTracerProvider())
        return

    resource = Resource.create({"service.name": settings.otel_service_name})
    sampler = ParentBased(TraceIdRatioBased(settings.otel_sampling_ratio))
    provider = TracerProvider(resource=resource, sampler=sampler)
    if settings.otel_endpoint:
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.otel_endpoint,
            insecure=settings.otel_insecure,
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    provider.add_span_processor(SentrySpanProcessor())
    trace.set_tracer_provider(provider)

    # Required for detecting errors in endpoints. Without it, everything would have to be handled manually
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
