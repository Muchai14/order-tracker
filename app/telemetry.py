"""Console and optional OTLP OpenTelemetry signals for GET /api/orders/{order_id}."""
import logging
import os
import sys
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogRecordExporter

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

resource = Resource.create({"service.name": "order-tracker"})
traces = TracerProvider(resource=resource)
traces.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter(out=sys.stdout)))
readers = [PeriodicExportingMetricReader(ConsoleMetricExporter(out=sys.stdout), export_interval_millis=5000)]
logs = LoggerProvider(resource=resource)
logs.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogRecordExporter(out=sys.stdout)))
# With no endpoint, the Question 2 console-only mode still works.
endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
if endpoint:
    traces.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint + "/v1/traces")))
    readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint + "/v1/metrics"), export_interval_millis=5000))
    logs.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint + "/v1/logs")))
meters = MeterProvider(resource=resource, metric_readers=readers)
tracer = traces.get_tracer(__name__)
counter = meters.get_meter(__name__).create_counter("order_lookup_requests", description="Order lookups by HTTP route and status")
# Publish an initial zero so Prometheus can see the first 500 increment.
counter.add(0, {"http.route": "/api/orders/{order_id}", "http.request.method": "GET", "http.response.status_code": 500})
logger = logging.getLogger("order-tracker")
logger.setLevel(logging.INFO)
logger.addHandler(LoggingHandler(logger_provider=logs))

class LookupTelemetry:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "GET" or not scope["path"].startswith("/api/orders/"):
            return await self.app(scope, receive, send)
        route = "/api/orders/{order_id}"
        status = 500
        async def capture(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
        with tracer.start_as_current_span("GET " + route, kind=trace.SpanKind.SERVER) as span:
            try:
                await self.app(scope, receive, capture)
            except Exception:
                logger.exception("Order lookup failed")
                raise
            finally:
                attrs = {"http.route": route, "http.request.method": "GET", "http.response.status_code": status}
                span.set_attributes(attrs)
                if status >= 500:
                    span.set_status(trace.StatusCode.ERROR)
                counter.add(1, attrs)
                logger.info("Order lookup completed", extra={**attrs, "url.path": scope["path"]})


def flush():
    for provider in (traces, meters, logs):
        provider.force_flush()
