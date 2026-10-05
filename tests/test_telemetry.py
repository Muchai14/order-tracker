from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from app import main, telemetry


def test_lookup_signals_cover_success_missing_and_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'orders.db')
    captured = []
    class Counter:
        def add(self, count, attributes):
            captured.append((count, attributes))
    monkeypatch.setattr(telemetry, 'counter', Counter())
    exporter = InMemorySpanExporter()
    telemetry.traces.add_span_processor(SimpleSpanProcessor(exporter))
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert client.get('/healthz').json() == {'status': 'ok'}
        assert client.get('/api/orders/standard-1001').status_code == 200
        assert client.get('/api/orders/standard-1002').status_code == 404
        # Independent of the exercise bug: verify unexpected failures become 500 telemetry.
        monkeypatch.setattr(main, 'order_detail', lambda row: 1 / 0)
        assert client.get('/api/orders/standard-1001').status_code == 500
    assert [attrs['http.response.status_code'] for _, attrs in captured] == [200, 404, 500]
    assert all(count == 1 and attrs['http.route'] == '/api/orders/{order_id}' for count, attrs in captured)
    spans = exporter.get_finished_spans()
    assert [span.attributes['http.response.status_code'] for span in spans] == [200, 404, 500]
    assert spans[-1].status.status_code.name == 'ERROR'
    assert any(event.name == 'exception' for event in spans[-1].events)
