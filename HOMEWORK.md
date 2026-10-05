# Homework 4: DevOps and Observability for AI-Built Apps

Submission repository: https://github.com/Muchai14/order-tracker

| Question | Answer |
| --- | --- |
| 1 | `{"status":"ok"}` |
| 2 | **200** |
| 3 | **404** |
| 4 | **Normal** |
| 5 | Actual agent response below. |
| 6 | **The express delivery date calculation tried to use a day that does not exist in that month.** |

## Question 5: actual last line

The agent returned one paragraph on one line:

> Acknowledged `ResponderTest` (`test: true`). Supplied telemetry shows zero values for 404 and 500 responses, with no logs or traces returned. No incident to fix. No tools run or files accessed or modified.

[Original response](docs/evidence/question5-answer.txt).

## Verification

- Started the app with Docker Compose and checked `/healthz`.
- Confirmed console metrics, logs and traces for `standard-1001` (200).
- Queried `standard-1002` (404) through the Collector pipeline; verified the
  metric, log and matching trace through Grafana data source proxies and viewed
  the request count and logs in the dashboard.
- Observed Grafana's 5xx rule in Normal after the 404 request. The rule includes
  the endpoint, five-minute window and dashboard link; absent 5xx data evaluates
  to zero. Prometheus rule tests cover no errors, 404, 500 and recovery.
- Posted the supplied test notification to `/alerts`; the responder automatically
  launched headless Codex and saved its real response.
- Triggered a real 500 with `express-1002`; Grafana delivered the webhook and
  Codex reproduced the bug, changed the date arithmetic and added eight
  regression cases. After review, **15 tests passed**. Rebuilt the app and
  verified the same lookup returned **200 three times**, with delivery date
  `2026-10-02` for the seeded `2026-09-30` order.

`standard-1002` is not a seeded order, so Question 4's request does not trigger
this 5xx alert. The seeded express order is `express-1002`.

The original expression `placed_at.replace(day=placed_at.day + 2)` could create
an invalid day. The repair uses `placed_at + timedelta(days=2)`, including across
month and year boundaries.

[Run instructions](README.md) · [Responder instructions](incident-response/README.md)
· [Recorded evidence](docs/evidence) · [Automatic repair response](docs/evidence/question6-answer.txt)

The earlier nested-sandbox failure is retained as a separate historical record.
The successful repair ran through the responder started in a host terminal.
