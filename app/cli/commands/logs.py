"""inference-engine logs — query the persistent structured event log."""
from __future__ import annotations

import os

from rich.console import Console
from rich.table import Table

from app.infra.logs.sqlite_log_sink import query_events

console = Console()


def run_logs(
    *,
    event_type: str | None = None,
    model_id: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
    deployment_id: str | None = None,
    since: str | None = None,
    limit: int = 50,
) -> None:
    db_path = os.environ.get("LOG_DB_PATH", "app/instance/logs.db")
    rows = query_events(
        db_path,
        event_type=event_type,
        model_id=model_id,
        request_id=request_id,
        job_id=job_id,
        deployment_id=deployment_id,
        since=since,
        limit=limit,
    )

    if not rows:
        console.print("[dim]No matching events.[/dim]")
        return

    table = Table(title=f"[bold]Events[/bold] ({len(rows)})", padding=(0, 1))
    for column in ("timestamp", "level", "event_type", "request_id", "job_id", "deployment_id", "model_id", "payload"):
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*(str(row.get(c) or "") for c in
                         ("timestamp", "level", "event_type", "request_id", "job_id", "deployment_id", "model_id", "payload")))
    console.print(table)
