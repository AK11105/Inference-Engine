# logs

Query the persistent structured event log.

```bash
inference-engine logs [options]
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--deployment-id` | — | Filter by deployment correlation ID |
| `--request-id` | — | Filter by request correlation ID |
| `--job-id` | — | Filter by async job ID |
| `--event` | — | Filter by event name, prefix match (e.g. `Prediction`) |
| `--level` | — | Minimum level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--component` | — | Filter by component name |
| `--model` | — | Filter by model name |
| `--since` | — | Time window: `5m`, `1h`, `24h`, `7d` |
| `--limit` | `50` | Max rows returned |
| `--format` | `table` | Output: `table` or `json` (newline-delimited, for piping to `jq`) |
| `--follow` | off | Live tail — polls for new events every 1s |
| `--stats` | off | Show log store size and event count |
| `--purge` | off | Purge events older than `--older-than` (default `7d`), asks for confirmation |
| `--older-than` | `7d` | Age threshold for `--purge` |
| `--yes` / `-y` | off | Skip the `--purge` confirmation prompt |

## Examples

```bash
inference-engine logs --deployment-id abc123
inference-engine logs --event PredictionFailed --since 1h
inference-engine logs --request-id xyz-456
inference-engine logs --level ERROR --since 24h
inference-engine logs --component PredictionService --since 30m
inference-engine logs --follow
inference-engine logs --deployment-id abc123 --format json
inference-engine logs --event DeploymentFailed --limit 10
inference-engine logs --stats
inference-engine logs --purge --older-than 7d
```

## Notes

- Reads from the same SQLite store the server writes to (`LOG_DB_PATH`, default `logs/events.db`).
- If the store doesn't exist yet, prints `No log store found. Run the server first.` and exits non-zero.
- `ENV=production` disables the durable SQLite sink entirely (see `app/core/logging.py`), so `logs` has nothing to query there.
