"""CLI entry point for inference-engine."""
from __future__ import annotations

import argparse
import atexit
import sys

from dotenv import load_dotenv
load_dotenv()


def main() -> None:
    from app.core.logging import setup_logging
    listener = setup_logging()
    if listener is not None:
        atexit.register(listener.stop)

    parser = argparse.ArgumentParser(
        prog="inference-engine",
        description="Inference Engine CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # deploy subcommand
    deploy_parser = subparsers.add_parser(
        "deploy",
        help="Deploy a trained model artifact to the inference engine.",
    )
    deploy_parser.add_argument("artifact", help="Path to the model artifact (.pkl, .joblib, etc.)")
    deploy_parser.add_argument("--name", help="Model name (default: derived from filename)")
    deploy_parser.add_argument("--version", help="Version string (default: auto-incremented)")
    deploy_parser.add_argument("--device", choices=["cpu", "gpu"], help="Execution target")
    deploy_parser.add_argument(
        "--framework",
        choices=["sklearn", "pytorch", "transformers", "xgboost", "lightgbm",
                 "catboost", "onnx", "sentence_transformers"],
        help="Override/assert the model framework when auto-detection is unreliable "
             "(e.g. the framework's package isn't installed in this environment)",
    )
    deploy_parser.add_argument("--routing", choices=["static", "canary", "ab"], help="Routing strategy")
    deploy_parser.add_argument("--sample-input", dest="sample_input", help="Sample input for validation")
    deploy_parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                               help="Run full flow including validation but write nothing")
    deploy_parser.add_argument("--allow-load", dest="allow_load", action="store_true",
                               help="Permit pickle/joblib deserialization during inspection "
                                    "(required for full metadata extraction from pickle artifacts)")
    deploy_parser.add_argument("--yes", "-y", dest="yes", action="store_true",
                               help="Skip all confirmation prompts (CI mode). "
                                    "Implies --allow-load.")

    # fix subcommand
    fix_parser = subparsers.add_parser(
        "fix",
        help="Fix a broken existing pipeline definition.",
    )
    fix_parser.add_argument("model_dir", help="Path to the model version directory (e.g. models/sentiment/v1/)")
    fix_parser.add_argument("--sample-input", dest="sample_input", default=None, help="Sample input for validation")
    fix_parser.add_argument("--yes", "-y", dest="yes", action="store_true",
                            help="Skip all confirmation prompts (CI mode).")

    # logs subcommand
    logs_parser = subparsers.add_parser(
        "logs",
        help="Query the persistent structured event log.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  inference-engine logs --deployment-id abc123
  inference-engine logs --event PredictionFailed --since 1h
  inference-engine logs --request-id xyz-456
  inference-engine logs --level ERROR --since 24h
  inference-engine logs --component PredictionService --since 30m
  inference-engine logs --follow
  inference-engine logs --deployment-id abc123 --format json
  inference-engine logs --event DeploymentFailed --limit 10
  inference-engine logs --stats
  inference-engine logs --purge --older-than 7d""",
    )
    logs_parser.add_argument("--event", dest="event", help="Filter by event name, prefix match (e.g. PredictionCompleted)")
    logs_parser.add_argument("--component", dest="component", help="Filter by component (e.g. PredictionService)")
    logs_parser.add_argument("--model", dest="model_id", help="Filter by model name")
    logs_parser.add_argument("--request-id", dest="request_id", help="Filter by request ID")
    logs_parser.add_argument("--job-id", dest="job_id", help="Filter by job ID")
    logs_parser.add_argument("--deployment-id", dest="deployment_id", help="Filter by deployment ID")
    logs_parser.add_argument("--level", dest="level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                             help="Minimum level")
    logs_parser.add_argument("--since", dest="since", help="Time window, e.g. 5m, 1h, 24h, 7d")
    logs_parser.add_argument("--limit", dest="limit", type=int, default=50, help="Max rows (default: 50)")
    logs_parser.add_argument("--format", dest="format", choices=["table", "json"], default="table",
                             help="Output format (default: table)")
    logs_parser.add_argument("--follow", dest="follow", action="store_true", help="Live tail (poll every 1s)")
    logs_parser.add_argument("--stats", dest="stats", action="store_true", help="Show log store stats")
    logs_parser.add_argument("--purge", dest="purge", action="store_true", help="Purge old events")
    logs_parser.add_argument("--older-than", dest="older_than", help="Age threshold for --purge (default: 7d)")
    logs_parser.add_argument("--yes", "-y", dest="yes", action="store_true",
                             help="Skip confirmation prompt for --purge")

    args = parser.parse_args()

    if args.command == "deploy":
        from app.cli.commands.deploy import run_deploy
        run_deploy(
            artifact_path=args.artifact,
            name=args.name,
            version=args.version,
            device=args.device,
            routing=args.routing,
            sample_input=args.sample_input,
            dry_run=args.dry_run,
            framework=args.framework,
            allow_load=args.allow_load,
            yes=args.yes,
        )
    elif args.command == "fix":
        from app.cli.commands.fix import run_fix
        run_fix(
            model_dir=args.model_dir,
            sample_input=args.sample_input,
            yes=args.yes,
        )
    elif args.command == "logs":
        from app.cli.commands.logs import run_logs
        run_logs(
            event=args.event,
            component=args.component,
            model_id=args.model_id,
            request_id=args.request_id,
            job_id=args.job_id,
            deployment_id=args.deployment_id,
            level=args.level,
            since=args.since,
            limit=args.limit,
            format=args.format,
            follow=args.follow,
            stats=args.stats,
            purge=args.purge,
            older_than=args.older_than,
            yes=args.yes,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
