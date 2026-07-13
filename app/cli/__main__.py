"""CLI entry point for inference-engine."""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv
load_dotenv()


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

    # fix subcommand
    fix_parser = subparsers.add_parser(
        "fix",
        help="Fix a broken existing pipeline definition.",
    )
    fix_parser.add_argument("model_dir", help="Path to the model version directory (e.g. models/sentiment/v1/)")
    fix_parser.add_argument("--sample-input", dest="sample_input", default=None, help="Sample input for validation")

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
        )
    elif args.command == "fix":
        from app.cli.commands.fix import run_fix
        run_fix(
            model_dir=args.model_dir,
            sample_input=args.sample_input,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
