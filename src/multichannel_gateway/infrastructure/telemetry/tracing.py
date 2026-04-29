from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from src.multichannel_gateway.app import TelemetrySettings


def setup_tracing(app: FastAPI, settings: TelemetrySettings) -> None:
    # If telemetry is disabled, leave the current provider untouched
    if not settings.otel_enabled:
        return

    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        resource = Resource.create({"service.name": settings.otel_service_name})
        sampler = ParentBased(TraceIdRatioBased(settings.otel_sampling_ratio))
        provider = TracerProvider(resource=resource, sampler=sampler)
        trace.set_tracer_provider(provider)

    if settings.otel_endpoint:
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.otel_endpoint,
            insecure=settings.otel_insecure,
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Required for detecting errors in endpoints. Without it, everything would have to be handled manually
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
