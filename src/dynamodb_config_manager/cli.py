from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from .config import load_env_config, load_table_map
from .dynamodb_client import DynamoDBConfigClient
from .models import ConfigManagerError, DeploymentSummary, Environment, Scope
from .processor import ConfigProcessor




class EnvironmentOption(str, Enum):
    dev = "dev"
    uat = "uat"
    prod = "prod"


class ScopeOption(str, Enum):
    all = "all"
    file = "file"
    folder = "folder"
    changed = "changed"

app = typer.Typer(
    help="Validate and deploy CSV config files into DynamoDB.",
    no_args_is_help=True,
)


def main() -> None:
    app()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    env: Annotated[
        EnvironmentOption | None,
        typer.Option("--env", help="Target environment: dev, uat, or prod."),
    ] = None,
    env_config: Annotated[
        Path | None,
        typer.Option("--env-config", help="TOML file for AWS environment mapping."),
    ] = None,
    scope: Annotated[
        ScopeOption | None,
        typer.Option("--scope", help="Deploy scope: all, file, folder, or changed."),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="CSV file path or folder path for file/folder scope."),
    ] = None,
    table_name: Annotated[
        str | None,
        typer.Option("--table-name", help="Optional table name override for single-file deploy."),
    ] = None,
    table_map: Annotated[
        Path | None,
        typer.Option("--table-map", help="Optional TOML map from CSV path to table name."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--no-dry-run", help="Validate only, without writes."),
    ] = True,
    clear_table: Annotated[
        bool,
        typer.Option("--clear-table", help="Clear the table before upsert."),
    ] = False,
    confirm_clear: Annotated[
        bool,
        typer.Option("--confirm-clear", help="Required with --clear-table."),
    ] = False,
    changed_base: Annotated[
        str | None,
        typer.Option("--changed-base", help="Git base ref for changed scope."),
    ] = None,
    changed_head: Annotated[
        str,
        typer.Option("--changed-head", help="Git head ref for changed scope."),
    ] = "HEAD",
    billing_mode: Annotated[
        str,
        typer.Option("--billing-mode", help="DynamoDB billing mode for table creation."),
    ] = "PAY_PER_REQUEST",
    backup_s3_bucket: Annotated[
        str | None,
        typer.Option("--backup-s3-bucket", help="S3 bucket for CSV backup after deploy."),
    ] = None,
    backup_s3_prefix: Annotated[
        str,
        typer.Option("--backup-s3-prefix", help="S3 key prefix for CSV backup."),
    ] = "",
    repo_root: Annotated[
        Path,
        typer.Option("--repo-root", help="Repository root path."),
    ] = Path.cwd(),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if env is None or scope is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(code=0)

    _run_deploy(
        env=env.value,
        env_config=env_config,
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


@app.command()
def deploy(
    env: Annotated[EnvironmentOption, typer.Option("--env", help="Target environment: dev, uat, or prod.")],
    scope: Annotated[ScopeOption, typer.Option("--scope", help="Deploy scope: all, file, folder, or changed.")],
    env_config: Annotated[
        Path | None,
        typer.Option("--env-config", help="TOML file for AWS environment mapping."),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="CSV file path or folder path for file/folder scope."),
    ] = None,
    table_name: Annotated[
        str | None,
        typer.Option("--table-name", help="Optional table name override for single-file deploy."),
    ] = None,
    table_map: Annotated[
        Path | None,
        typer.Option("--table-map", help="Optional TOML map from CSV path to table name."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--no-dry-run", help="Validate only, without writes."),
    ] = True,
    clear_table: Annotated[
        bool, typer.Option("--clear-table", help="Clear the table before upsert.")
    ] = False,
    confirm_clear: Annotated[
        bool, typer.Option("--confirm-clear", help="Required with --clear-table.")
    ] = False,
    changed_base: Annotated[
        str | None, typer.Option("--changed-base", help="Git base ref for changed scope.")
    ] = None,
    changed_head: Annotated[
        str, typer.Option("--changed-head", help="Git head ref for changed scope.")
    ] = "HEAD",
    billing_mode: Annotated[
        str, typer.Option("--billing-mode", help="DynamoDB billing mode for table creation.")
    ] = "PAY_PER_REQUEST",
    backup_s3_bucket: Annotated[
        str | None,
        typer.Option("--backup-s3-bucket", help="S3 bucket for CSV backup after deploy."),
    ] = None,
    backup_s3_prefix: Annotated[
        str, typer.Option("--backup-s3-prefix", help="S3 key prefix for CSV backup.")
    ] = "",
    repo_root: Annotated[Path, typer.Option("--repo-root", help="Repository root path.")] = Path.cwd(),
) -> None:
    _run_deploy(
        env=env.value,
        env_config=env_config,
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
    env_config: Path | None,
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
        loaded_env_config = load_env_config(env, env_config)
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
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def print_summary(summary: DeploymentSummary) -> None:
    files = [result.filepath for result in summary.results]
    tables = [result.table_name for result in summary.results]
    rows_read = sum(result.record_count for result in summary.results)
    rows_upserted = sum(result.rows_upserted for result in summary.results)
    rows_failed = sum(result.rows_failed for result in summary.results)
    backup_uris = [result.backup_s3_uri for result in summary.results if result.backup_s3_uri]

    typer.echo(f"Environment : {summary.env}")
    typer.echo()
    typer.echo("Files Processed")
    for filepath in files:
        typer.echo(f"- {filepath}")
    typer.echo()
    typer.echo("Table")
    for table in tables:
        typer.echo(f"- {table}")
    typer.echo()
    typer.echo("Rows Read")
    typer.echo(f"- {rows_read}")
    typer.echo()
    typer.echo("Rows Upserted")
    typer.echo(f"- {rows_upserted}")
    typer.echo()
    typer.echo("Rows Failed")
    typer.echo(f"- {rows_failed}")
    typer.echo()
    if backup_uris:
        typer.echo()
        typer.echo("S3 Backup")
        for backup_uri in backup_uris:
            typer.echo(f"- {backup_uri}")

    typer.echo("Status")
    typer.echo(f"- {summary.status}")

    failures = [result for result in summary.results if result.error_detail]
    if failures:
        typer.echo()
        typer.echo("Errors")
        for result in failures:
            typer.echo(f"- {result.filepath}: {result.error_detail}")


if __name__ == "__main__":
    main()
