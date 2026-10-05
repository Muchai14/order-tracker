"""Check a Q3 request through Grafana's actual data source proxies (stdlib only)."""
import base64
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GRAFANA = os.getenv('GRAFANA_URL', 'http://localhost:3000')
APP = os.getenv('APP_URL', 'http://localhost:8000')
AUTH = base64.b64encode(('admin:' + os.getenv('GRAFANA_PASSWORD', 'homework-local')).encode()).decode()


def query(source, path, params=None):
    url = GRAFANA + '/api/datasources/proxy/uid/' + source + path
    if params:
        url += '?' + urlencode(params)
    with urlopen(Request(url, headers={'Authorization': 'Basic ' + AUTH}), timeout=10) as response:
        return json.load(response)


def verify():
    started = time.time()
    try:
        with urlopen(APP + '/api/orders/standard-1002', timeout=10) as response:
            status = response.status
    except HTTPError as exc:
        status = exc.code
    assert status == 404, f'Expected missing order, got HTTP {status}'
    last_error = ''
    for _ in range(30):
        try:
            metrics = query('prometheus', '/api/v1/query', {'query': 'order_lookup_requests_total{http_response_status_code="404"}'})
            assert any(float(item['value'][1]) >= 1 for item in metrics['data']['result']), 'Metric not exported yet'
            logs = query('loki', '/loki/api/v1/query_range', {
                'query': '{service_name="order-tracker"} | http_response_status_code="404"',
                'start': str(int(started * 1e9)), 'end': str(time.time_ns()), 'limit': '50',
            })
            assert logs['data']['result'], 'Log not exported yet'
            traces = query('tempo', '/api/search', {
                'q': '{ resource.service.name = "order-tracker" && span.http.response.status_code = 404 }',
                'start': str(int(started)), 'end': str(int(time.time()) + 1), 'limit': '20',
            })
            assert traces.get('traces'), 'Trace not exported yet'
            trace_id = traces['traces'][0]['traceID']
            detail = query('tempo', '/api/traces/' + trace_id)
            # Loki may put structured metadata on each value or in stream labels.
            assert trace_id in json.dumps(logs), 'Waiting for matching log and trace IDs'
            print(json.dumps({'http_status': status, 'metric': metrics['data']['result'], 'logs': logs['data']['result'], 'trace_id': trace_id, 'trace': detail, 'verified_via': 'Grafana data source proxies'}, indent=2))
            return
        except (HTTPError, URLError, AssertionError, KeyError, TimeoutError) as exc:
            last_error = str(exc)
            time.sleep(3)
    raise SystemExit('Telemetry verification failed: ' + last_error)


if __name__ == '__main__':
    verify()
