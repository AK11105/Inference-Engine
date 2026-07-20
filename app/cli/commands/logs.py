"""inference-engine logs — query the persistent structured event log."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.table import Table

from app.infra.logs.sqlite_log_sink import (
    DEFAULT_DB_PATH,
    get_log_stats,
    purge_old_events,
    query_events,
)

console = Console()

_COLUMNS = ("timestamp", "level", "event", "component", "request_id", "job_id", "deployment_id", "model_id", "payload")


def _humanize_age(delta: timedelta) -> str:
    if delta.days >= 1:
        return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    minutes = delta.seconds // 60
    return f"{minutes} minute{'s' if minutes != 1 else ''} ago"


def _print_rows(rows: list[dict], *, format: str) -> None:
    if not rows:
        console.print("[dim]No matching events.[/dim]")
        return
    if format == "json":
        for row in rows:
            print(json.dumps(row))
        return
    table = Table(title=f"[bold]Events[/bold] ({len(rows)})", padding=(0, 1))
    for column in _COLUMNS:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*(str(row.get(c) or "") for c in _COLUMNS))
    console.print(table)


def _print_stats(db_path: str) -> None:
    stats = get_log_stats(db_path)
    size_mb = stats["size_bytes"] / (1024 * 1024)
    if stats["oldest"]:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(stats["oldest"])
        oldest = _humanize_age(age)
    else:
        oldest = "n/a"
    console.print(f"{stats['count']:,} events | {size_mb:.1f} MB | oldest: {oldest}")


def _run_purge(db_path: str, *, older_than: str | None, yes: bool) -> None:
    older_than = older_than or "7d"
    if not yes:
        try:
            answer = input(f"Purge events older than {older_than}? (Y/n) > ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("", "y", "yes"):
            console.print("Aborted. No events purged.")
            return
    deleted = purge_old_events(db_path, older_than=older_than)
    console.print(f"Purged {deleted:,} events.")


def _run_follow(db_path: str, *, format: str, **filters) -> None:
    latest = query_events(db_path, limit=1, **filters)
    last_id = latest[0]["id"] if latest else 0
    console.print("[dim]Following log store (Ctrl+C to stop)...[/dim]")
    try:
        while True:
            rows = query_events(db_path, after_id=last_id, limit=1000, **filters)
            if rows:
                _print_rows(rows, format=format)
                last_id = rows[-1]["id"]
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped following.[/dim]")


def run_logs(
    *,
    event: str | None = None,
    component: str | None = None,
    model_id: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
    deployment_id: str | None = None,
    level: str | None = None,
    since: str | None = None,
    limit: int = 50,
    format: str = "table",
    follow: bool = False,
    stats: bool = False,
    purge: bool = False,
    older_than: str | None = None,
    yes: bool = False,
) -> None:
    db_path = os.environ.get("LOG_DB_PATH", DEFAULT_DB_PATH)

    if not os.path.exists(db_path):
        console.print("[red]No log store found. Run the server first.[/red]")
        sys.exit(1)

    if stats:
        _print_stats(db_path)
        return

    if purge:
        _run_purge(db_path, older_than=older_than, yes=yes)
        return

    filters = dict(
        event=event, component=component, model_id=model_id, request_id=request_id,
        job_id=job_id, deployment_id=deployment_id, level=level, since=since,
    )

    if follow:
        _run_follow(db_path, format=format, **filters)
        return

    rows = query_events(db_path, limit=limit, **filters)
    _print_rows(rows, format=format)
