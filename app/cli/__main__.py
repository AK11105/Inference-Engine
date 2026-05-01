"""CLI entry point for inference-engine."""
from __future__ import annotations

import argparse
import sys


def main() -> None:
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

    args = parser.parse_args()

    if args.command == "deploy":
        from app.cli.deploy import run_deploy
        run_deploy(args.artifact)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
