# Monitoring Setup

## Prometheus

Metrics are available at `GET /metrics` (requires `admin` scope).

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: inference-engine
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
    bearer_token: <admin-api-key>
```

Or use basic header auth via a scrape config `authorization` block.

---

## Recommended alerts

| Alert | Query | Threshold |
|---|---|---|
| High error rate | `rate(inference_errors_total[5m]) / rate(inference_requests_total[5m])` | > 5% |
| High p99 latency | `histogram_quantile(0.99, rate(inference_latency_seconds_bucket[5m]))` | > 2s |
| Timeout spike | `rate(executor_timeouts_total[5m])` | > 0 |
| Queue depth growing | `job_queue_depth` | > 100 |

---

## Grafana

![Grafana dashboard panel layout mockup](../assets/grafana-dashboard-light.png#only-light)
![Grafana dashboard panel layout mockup](../assets/grafana-dashboard-dark.png#only-dark)

Import a dashboard using the metrics from [Metrics reference](metrics.md). Key panels:

- Request rate by model/tenant
- p50/p95/p99 latency histogram
- Error rate by error type
- Queue depth over time
- Executor inflight gauge

---

## Log aggregation

All logs are JSON on stdout. Ship to your collector without additional parsing:

```bash
# Datadog
docker run ... | datadog-agent ...

# Loki
uvicorn ... 2>&1 | promtail ...
```

Use `request_id` to correlate log lines with job records and OTel traces.

---

## Distributed tracing

See [Tracing](tracing.md) for OpenTelemetry setup with Jaeger or any OTLP-compatible backend.
