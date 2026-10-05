# Incident responder

This local host service receives Grafana notifications at `POST /alerts` on port
8001 and launches the installed, authenticated Codex CLI without an interactive UI.
Run it from the repository root with one worker:

```sh
uv sync --frozen
codex login status
uv run uvicorn server:app --app-dir incident-response --host 127.0.0.1 --port 8001
```

Use `CODEX_BIN=/absolute/path/to/codex` if Codex is not on PATH. Codex must be able
to write its own runtime/state directory and reach its model provider. When a
trusted enterprise/network CA is required, set `CODEX_CA_CERTIFICATE` to the
existing trusted PEM bundle for your environment. Do not disable TLS verification.

Test with the exact Question 5 payload:

```sh
curl -X POST http://localhost:8001/alerts \
  -H 'Content-Type: application/json' \
  -d '{"alerts":[{"status":"firing","labels":{"alertname":"ResponderTest","test":"true"},"annotations":{"summary":"Test notification; no incident to fix"}}]}'
```

The HTTP 202 response returns the job ID, not a completed diagnosis. Look in
`incident-response/incidents/<job-id>/`:

- `alert.json`: received alert labels, annotations, status and start time.
- `evidence.json`: endpoint, five-minute window, Prometheus metrics, Loki logs,
  Tempo search results and complete matching traces; failures are recorded.
- `prompt.txt`: instructions supplied to Codex; alert/telemetry text is untrusted.
- `agent.log`: Codex process output and diagnostic errors.
- `status.json`: queued, collecting, running, completed or failed.
- `answer.txt`: the real final agent response, if it produced one.

For Question 5, wait for `completed`, read the whole answer, and copy its last
non-empty line. Never submit a fabricated answer or an error message as a
successful agent response. Test alerts use a read-only agent sandbox and require
no changes. Real alerts use workspace-write and ask the agent to investigate,
fix and test locally, with no push, deployment or changes to monitoring rules.
The responder invokes `codex exec --ephemeral --sandbox ... -C ...
--output-last-message ... -` and passes the prompt through stdin without a shell.

Resolved notifications are ignored. Active duplicate alerts are suppressed and
jobs are serialized with an eight-job queue limit. A job has a ten-minute timeout.
Saved incidents are gitignored. This is a local homework service, not a durable
job queue: interrupted queued/running jobs are not automatically resumed after a
restart. Keep it bound to loopback for the manual test; configure the Grafana
webhook in Question 6 after verifying this test succeeds.

Telemetry URLs default to host ports 9090, 3100 and 3200. Override with
`PROMETHEUS_URL`, `LOKI_URL` and `TEMPO_URL` if necessary.

The prompt also includes the alert and up to 64,000 characters of telemetry, so
Codex can acknowledge test notifications without needing an extra file-read tool.
The complete evidence remains in the incident directory. On this machine the
working launch command uses its existing system CA bundle:

```sh
CODEX_CA_CERTIFICATE=/etc/ssl/cert.pem uv run uvicorn server:app --app-dir incident-response --host 127.0.0.1 --port 8001
```

This fixes the CLI's certificate trust configuration without disabling certificate
verification. File-editing commands in an agent launched inside another sandbox
may still be restricted; Question 6 must verify that the repair actually ran.

## Question 6: Grafana webhook

The contact point and notification policy are provisioned in
`observability/grafana/provisioning/alerting/webhook.yaml`. Grafana sends alerts
to `http://host.docker.internal:8001/alerts`. Docker Desktop can reach the host
responder through that name. Keep the responder running and restart Grafana
when provisioning changes:

```sh
docker compose restart grafana
curl -i http://localhost:8000/api/orders/express-1002
```

Watch the rule change to Firing and a new incident directory appear. Review the
agent's answer and code diff. A completed job only means the agent returned an
answer; verify it actually fixed the issue and ran tests. If its tools report a
sandbox error, start this same responder from your own terminal, where Codex can
initialize its sandbox normally; do not disable the sandbox. After reviewing a
successful repair, run the tests, rebuild the app and verify the same request:

```sh
uv run --frozen pytest -q -s
docker compose up --build -d --wait app
curl -i http://localhost:8000/api/orders/express-1002
```

The old error remains inside the alert's five-minute lookback until it expires.
