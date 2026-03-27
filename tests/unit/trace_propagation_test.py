from opentelemetry import context as context_api
from opentelemetry import propagate
from opentelemetry import trace
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    TraceState,
    set_span_in_context,
)
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from src.multichannel_gateway.infrastructure.telemetry.propagation import (
    extract_trace_context,
    inject_trace_context,
)


def test_trace_context_roundtrip() -> None:
    # Create a minimal business payload that mimics a queue message body.
    payload = {"channel": "telegram", "message_id": "42"}
    # Build a deterministic synthetic producer span context so the test does not depend on a global tracer provider.
    producer_span_context = SpanContext(
        # Use a fixed trace ID to make the roundtrip assertion deterministic.
        trace_id=0x1234567890ABCDEF1234567890ABCDEF,
        # Use a fixed span ID representing the producer span.
        span_id=0x1234567890ABCDEF,
        # Mark the original producer span as local because it was "created" on the sender side.
        is_remote=False,
        # Mark the trace as sampled so the generated carrier represents a real traced request.
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        # Use an empty trace state because this test only needs traceparent propagation.
        trace_state=TraceState(),
    )
    # Put the synthetic producer span into an OpenTelemetry Context object.
    producer_context = set_span_in_context(NonRecordingSpan(producer_span_context))
    # Save the current global propagator so the test can restore it afterwards.
    original_propagator = propagate.get_global_textmap()
    # Force the standard W3C propagator to make the test independent from any other test mutating global OTEL state.
    propagate.set_global_textmap(TraceContextTextMapPropagator())

    try:
        # Attach the synthetic producer context so inject_trace_context() sees it as the current active span.
        token = context_api.attach(producer_context)
        try:
            enriched_payload = inject_trace_context(payload)
        finally:
            # Always detach the producer context to avoid leaking state into other tests.
            context_api.detach(token)

        assert "_otel_trace_context" in enriched_payload
        carrier = enriched_payload["_otel_trace_context"]
        # Ensure the carrier is a mapping because extract_trace_context() expects key-value headers.
        assert isinstance(carrier, dict)
        # Ensure the carrier is not empty, otherwise injection did not happen.
        assert carrier
        # Ensure the standard W3C traceparent header was actually propagated.
        assert "traceparent" in carrier

        parent_context, extracted_payload = extract_trace_context(enriched_payload)

        # Ensure the business payload was preserved and the helper removed only its own internal metadata.
        assert extracted_payload == payload
        # Ensure extraction produced a usable parent context rather than returning no tracing information.
        assert parent_context is not None

        # Attach the extracted context so OpenTelemetry exposes it as the current remote parent span.
        token = context_api.attach(parent_context)
        try:
            # Read the currently active span context reconstructed from the extracted carrier.
            extracted_span_context = trace.get_current_span().get_span_context()
            # The extracted parent must be marked as remote because it came from serialized queue metadata.
            assert extracted_span_context.is_remote is True
            # The extracted trace must belong to the same distributed trace as the original producer.
            assert extracted_span_context.trace_id == producer_span_context.trace_id
            # The extracted parent span ID must match the original producer span ID exactly.
            assert extracted_span_context.span_id == producer_span_context.span_id
        finally:
            # Always detach the extracted context to keep the test isolated.
            context_api.detach(token)
    finally:
        # Restore the original global propagator so this test does not affect the rest of the suite.
        propagate.set_global_textmap(original_propagator)
