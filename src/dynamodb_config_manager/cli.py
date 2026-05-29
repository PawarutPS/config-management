from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import load_env_config, load_table_map
from .dynamodb_client import DynamoDBConfigClient
from .models import ConfigManagerError, DeploymentSummary
from .processor import ConfigProcessor


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        repo_root = Path(args.repo_root).resolve()
        env_config = load_env_config(args.env, args.env_config)
        table_map = load_table_map(args.table_map)
        dynamodb_client = DynamoDBConfigClient(env_config)
        processor = ConfigProcessor(repo_root, dynamodb_client, table_map)
        summary = processor.deploy(
            env=args.env,
            scope=args.scope,
            path=args.path,
            table_name=args.table_name,
            dry_run=args.dry_run,
            clear_table=args.clear_table,
            confirm_clear=args.confirm_clear,
            changed_base=args.changed_base,
            changed_head=args.changed_head,
            billing_mode=args.billing_mode,
        )
        print_summary(summary)
        return 1 if summary.status == "FAILED" else 0
    except ConfigManagerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a clean failure
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dynamodb-config-manager",
        description="Validate and deploy CSV config files into DynamoDB.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--env", choices=["dev", "uat", "prod"], required=True)
    parser.add_argument("--env-config", type=Path)
    parser.add_argument("--scope", choices=["all", "file", "folder", "changed"], required=True)
    parser.add_argument("--path", type=Path)
    parser.add_argument("--table-name")
    parser.add_argument("--table-map", type=Path)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--clear-table", action="store_true")
    parser.add_argument("--confirm-clear", action="store_true")
    parser.add_argument("--changed-base")
    parser.add_argument("--changed-head", default="HEAD")
    parser.add_argument("--billing-mode", default="PAY_PER_REQUEST")
    return parser


def print_summary(summary: DeploymentSummary) -> None:
    files = [result.filepath for result in summary.results]
    tables = [result.table_name for result in summary.results]
    rows_read = sum(result.record_count for result in summary.results)
    rows_upserted = sum(result.rows_upserted for result in summary.results)
    rows_failed = sum(result.rows_failed for result in summary.results)

    print(f"Environment : {summary.env}")
    print()
    print("Files Processed")
    for filepath in files:
        print(f"- {filepath}")
    print()
    print("Table")
    for table in tables:
        print(f"- {table}")
    print()
    print("Rows Read")
    print(f"- {rows_read}")
    print()
    print("Rows Upserted")
    print(f"- {rows_upserted}")
    print()
    print("Rows Failed")
    print(f"- {rows_failed}")
    print()
    print("Status")
    print(f"- {summary.status}")

    failures = [result for result in summary.results if result.error_detail]
    if failures:
        print()
        print("Errors")
        for result in failures:
            print(f"- {result.filepath}: {result.error_detail}")


if __name__ == "__main__":
    raise SystemExit(main())
