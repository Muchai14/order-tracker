# Order Tracker

[Homework 4 answers and verification](HOMEWORK.md)

A small order tracking app for the AI Dev Tools Zoomcamp observability homework. It includes a web page, API, tests, and a Docker Compose setup. You add telemetry, alerts, and an incident responder in Homework 4.

The main user flow is creating an order and checking its status. Three sample orders are created on first startup.

## Run it

You need Docker with Compose. To run the tests, you also need Python 3.11+ and `uv`.

```bash
docker compose up --build -d --wait
```

Open <http://127.0.0.1:8000>. The API is at `/api/orders`, and the health check is at `/healthz`. Data is stored in a Docker volume and survives container recreation.

If port 8000 is occupied, set `ORDER_TRACKER_PORT`, for example:

```bash
ORDER_TRACKER_PORT=18080 docker compose up --build -d --wait
```

Run tests with `uv run --frozen pytest -q`. Stop the app with `docker compose down`. Add `-v` only if you also want to delete the order data.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Web page |
| GET | `/healthz` | Database health check |
| GET | `/api/orders` | List orders |
| POST | `/api/orders` | Create an order |
| GET | `/api/orders/{id}` | Check an order |
| PATCH | `/api/orders/{id}` | Change an order status |

The app uses SQLite to keep setup small. Run one app container at a time. The course exercise is about detecting and handling an incident, not scaling the database.

## Homework 4 — Question 2: console telemetry

Order lookups (`GET /api/orders/{order_id}`) now produce OpenTelemetry metrics,
logs and traces. The `order_lookup_requests` counter includes `http.route`,
`http.request.method` and `http.response.status_code`. Metric labels use the
route template instead of individual order IDs. Logs include the request path
and share the request span's trace ID. Unexpected errors are captured in logs
and span events, and counted as HTTP 500.

```sh
docker compose up --build -d --wait
curl -i http://localhost:8000/api/orders/standard-1001
docker compose logs --since 1m app
```

Allow about 5 seconds for the console exporters. In the metric output, find
`"name": "order_lookup_requests"`, then its data point attributes:

```json
{
  "http.route": "/api/orders/{order_id}",
  "http.request.method": "GET",
  "http.response.status_code": 200
}
```

Question 2 answer: **200**. Run tests with `uv run --frozen pytest -q -s`.

## Homework 4 — Question 3: telemetry pipeline

Compose now runs the app, OpenTelemetry Collector, Prometheus, Loki, Tempo and
Grafana. The app retains its console exporters and also sends all three signals
to the Collector over OTLP/HTTP. Prometheus scrapes Collector metrics; Collector
pushes logs to Loki and traces to Tempo. Configuration and the provisioned
Grafana dashboard are saved in `observability/`. Named volumes persist data.

```sh
docker compose up --build -d --wait
curl -i http://localhost:8000/api/orders/standard-1002
```

Wait about 15 seconds for export and scraping. Open
[Grafana's Order Tracker dashboard](http://localhost:3000/d/orders).
Sign in with username `admin` and password `homework-local` (override
`GRAFANA_PASSWORD` before first startup to use a different password).
The dashboard shows cumulative request counts by route/status, 5xx increases
in the last five minutes, and lookup logs. A zero 5xx panel is expected here.

In Grafana Explore:

- **Prometheus:** `order_lookup_requests_total{http_response_status_code="404"}`
- **Loki:** `{service_name="order-tracker"} | http_response_status_code="404"`
- **Tempo:** `{ resource.service.name = "order-tracker" && span.http.response.status_code = 404 }`

Expand the Loki entry to find `url_path` and `trace_id`; search that trace ID in
Tempo to inspect the same request. The console output retains the original
OpenTelemetry attribute names; Prometheus and Loki normalize dots to underscores.

The starter has no `standard-1002` order, so this lookup returns **404**.
All published ports bind to host loopback. This is a local homework stack.
No alert or responder is configured yet; those are later questions.

To verify all three stores through Grafana's data source proxies, run:

```sh
python3 scripts/verify_telemetry.py
```

The script makes a new `standard-1002` request, waits for ingestion, and checks
that a 404 metric, a 404 log and its matching trace are queryable from Grafana.
It prints the evidence as JSON and exits with an error if verification fails.

Verified locally: the Grafana dashboard displayed the 404 series and lookup logs;
the verification script confirmed the matching Tempo trace. A sample result is
saved in `docs/evidence/question3.json`. The one-shot `tempo-init` container sets
the named volume's owner to Tempo's UID (10001); Tempo itself runs as its normal
non-root user.

## Homework 4 — Question 4: 5xx alert

The provisioned **Order lookup server errors** rule checks
`GET /api/orders/{order_id}` every 10 seconds. It fires immediately on evaluation
when the 5xx counter increases within the last 5 minutes (`for: 0s`). Annotations
include the endpoint, window and dashboard/panel links. The query's
`or vector(0)` handles an absent 5xx series; `noDataState: OK` keeps the rule Normal
when no data is returned. Query execution failures remain Error. The application
publishes an initial zero-valued 500 counter so the first later error is counted.
Allow about 15 seconds after app startup for the initial baseline to be scraped.

Configuration: `observability/grafana/provisioning/alerting/alerts.yaml`.
After editing provisioning files, restart Grafana to load them:

```sh
docker compose restart grafana
curl -i http://localhost:8000/api/orders/standard-1002
```

Wait for the next evaluation, then open
[Grafana Alert rules](http://localhost:3000/alerting/list).
The lookup returns 404, which is outside 5xx, so the observed rule state for
Question 4 is **Normal**. There is no pending interval and no webhook has been
configured yet. Question 6 will connect the responder and trigger a real 500.

Test the alert expression with synthetic Prometheus data:

```sh
docker compose exec -T prometheus promtool test rules /dev/stdin < tests/alert-rules.test.yaml
```

These tests cover absent errors, 404-only traffic, a 500 increment, and recovery
once the error leaves the window. They do not generate a live incident.

## Homework 4 — Question 5: automatic responder

See [incident-response/README.md](incident-response/README.md) for startup,
the test notification, evidence files and how to read the actual Codex answer.
The responder runs on the host on port 8001 to use the local authenticated Codex
CLI and repository. Grafana webhook wiring is intentionally left for Question 6.

Question 5 was verified with the exact test payload. The responder launched Codex
and completed with exit code 0. Its actual final answer is saved in
[docs/evidence/question5-answer.txt](docs/evidence/question5-answer.txt).

## Homework 4 — Question 6: verified automatic repair

Grafana's real 5xx alert delivered a webhook to the host responder, which launched
Codex automatically. Running the responder from an ordinary terminal allowed
Codex's workspace sandbox to initialize. Codex reproduced seven failing date
boundary cases, then fixed the estimate with `placed_at + timedelta(days=2)` and
added eight API regression cases (ordinary date, month end, leap year and year end).
The reviewer reran the complete suite: **15 passed**, with three dependency
deprecation warnings. The app was rebuilt and the same `express-1002` lookup
returned **HTTP 200** three times, with estimated delivery `2026-10-02` for the
seeded `2026-09-30` order.

Question 6 answer: **The express delivery date calculation tried to use a day
that does not exist in that month.** `datetime.replace(day=day + 2)` is field
replacement, not date arithmetic, and raises `ValueError` at month boundaries.

The actual automatic agent response is saved in
[docs/evidence/question6-answer.txt](docs/evidence/question6-answer.txt).
The earlier blocked attempt is retained separately for transparency. During the
retry, the notification repeat interval was temporarily shortened so Grafana
could resend an already-firing alert; the saved policy is restored to four hours.
