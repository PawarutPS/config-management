from __future__ import annotations

import logging
import sys
from enum import Enum
from pathlib import Path

import typer

from .config import load_env_config, load_table_map
from .dynamodb_client import DynamoDBConfigClient
from .models import ConfigManagerError, DeploymentSummary, Environment, Scope
from .processor import ConfigProcessor


class ScopeOption(str, Enum):
    all = "all"
    file = "file"
    folder = "folder"
    changed = "changed"


app = typer.Typer(help="Validate and deploy CSV config files into DynamoDB.")


def main() -> None:
    app()


@app.command()
def deploy(
    scope: ScopeOption = ScopeOption.changed,
    env: str = "default",
    path: Path | None = None,
    table_name: str | None = None,
    table_map: Path | None = None,
    dry_run: bool = True,
    clear_table: bool = False,
    confirm_clear: bool = False,
    changed_base: str | None = None,
    changed_head: str = "HEAD",
    billing_mode: str = "PAY_PER_REQUEST",
    backup_s3_bucket: str | None = None,
    backup_s3_prefix: str = "",
    repo_root = Path.cwd(),
) -> None:
    _run_deploy(
        env=env,
        scope=scope.value,
        path=path,
        table_name=table_name,
        table_map=table_map,
        dry_run=dry_run,
        clear_table=clear_table,
        confirm_clear=confirm_clear,
        changed_base=changed_base,
        changed_head=changed_head,
        billing_mode=billing_mode,
        backup_s3_bucket=backup_s3_bucket,
        backup_s3_prefix=backup_s3_prefix,
        repo_root=repo_root,
    )


def _run_deploy(
    env: Environment,
    scope: Scope,
    path: Path | None,
    table_name: str | None,
    table_map: Path | None,
    dry_run: bool,
    clear_table: bool,
    confirm_clear: bool,
    changed_base: str | None,
    changed_head: str,
    billing_mode: str,
    backup_s3_bucket: str | None,
    backup_s3_prefix: str,
    repo_root: Path,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        resolved_repo_root = repo_root.resolve()
        loaded_env_config = load_env_config(env=None, config_path=None)
        loaded_table_map = load_table_map(table_map)
        dynamodb_client = DynamoDBConfigClient(loaded_env_config)
        processor = ConfigProcessor(resolved_repo_root, dynamodb_client, loaded_table_map)
        summary = processor.deploy(
            env=env,
            scope=scope,
            path=path,
            table_name=table_name,
            dry_run=dry_run,
            clear_table=clear_table,
            confirm_clear=confirm_clear,
            changed_base=changed_base,
            changed_head=changed_head,
            billing_mode=billing_mode,
            backup_s3_bucket=backup_s3_bucket,
            backup_s3_prefix=backup_s3_prefix,
        )
        print_summary(summary)
        if summary.status == "FAILED":
            raise typer.Exit(code=1)
    except ConfigManagerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise typer.Exit(code=1) from exc


def print_summary(summary: DeploymentSummary) -> None:
    files = [result.filepath for result in summary.results]
    tables = [result.table_name for result in summary.results]
    rows_read = sum(result.record_count for result in summary.results)
    rows_upserted = sum(result.rows_upserted for result in summary.results)
    rows_failed = sum(result.rows_failed for result in summary.results)
    backup_uris = [result.backup_s3_uri for result in summary.results if result.backup_s3_uri]

    if summary.env != "default":
        print(f"Environment : {summary.env}")
    print("Files Processed")
    for filepath in files:
        print(f"- {filepath}")
    print("Table")
    for table in tables:
        print(f"- {table}")
    print("Rows Read")
    print(f"- {rows_read}")
    print("Rows Upserted")
    print(f"- {rows_upserted}")
    print("Rows Failed")
    print(f"- {rows_failed}")
    if backup_uris:

        print("S3 Backup")
        for backup_uri in backup_uris:
            print(f"- {backup_uri}")

    print("Status")
    print(f"- {summary.status}")

    failures = [result for result in summary.results if result.error_detail]
    if failures:

        print("Errors")
        for result in failures:
            print(f"- {result.filepath}: {result.error_detail}")


if __name__ == "__main__":
    main()
