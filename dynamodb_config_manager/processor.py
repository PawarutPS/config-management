from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .dynamodb_client import DynamoDBConfigClient
from .models import (
    DeploymentSummary,
    Environment,
    FileDeploymentResult,
    Scope,
    ValidatedConfigFile,
    ValidationError,
)
from .validator import validate_allowed_config_roots, validate_config_file


LOGGER = logging.getLogger("dynamodb_config_manager")


class ConfigProcessor:
    def __init__(
        self,
        repo_root: Path,
        dynamodb_client: DynamoDBConfigClient,
        table_map: dict[str, str] | None = None,
    ):
        self.repo_root = repo_root.resolve()
        self.dynamodb_client = dynamodb_client
        self.table_map = table_map or {}

    def deploy(
        self,
        scope: Scope,
        env: Environment = "default",
        path: Path | None = None,
        table_name: str | None = None,
        dry_run: bool = True,
        clear_table: bool = False,
        confirm_clear: bool = False,
        changed_base: str | None = None,
        changed_head: str = "HEAD",
        billing_mode: str = "PAY_PER_REQUEST",
        backup_s3_bucket: str | None = None,
        backup_s3_prefix: str = "",
    ) -> DeploymentSummary:
        if clear_table and not confirm_clear:
            raise ValidationError("confirm_clear=true is required when clear_table=true")

        files = self.resolve_files(scope, path, changed_base, changed_head)
        validated_files = [
            self._validate_file_for_deploy(filepath, table_name, scope) for filepath in files
        ]

        results = [
            self._deploy_file(
                env,
                config_file,
                dry_run,
                clear_table,
                billing_mode,
                backup_s3_bucket,
                backup_s3_prefix,
            )
            for config_file in validated_files
        ]
        return DeploymentSummary(env=env, results=results)

    def resolve_files(
        self,
        scope: Scope,
        path: Path | None,
        changed_base: str | None,
        changed_head: str,
    ) -> list[Path]:
        validate_allowed_config_roots(self.repo_root)

        if scope == "file":
            if path is None:
                raise ValidationError("--path is required when --scope file")
            return [path]
        if scope == "folder":
            if path is None:
                raise ValidationError("--path is required when --scope folder")
            folder = path if path.is_absolute() else self.repo_root / path
            if not folder.exists() or not folder.is_dir():
                raise ValidationError(f"folder does not exist: {path}")
            return sorted(folder.rglob("*.csv"))
        if scope == "all":
            return sorted((self.repo_root / "config").rglob("*.csv"))
        if scope == "changed":
            return self._changed_csv_files(changed_base, changed_head)
        raise ValidationError(f"unsupported scope: {scope}")

    def _validate_file_for_deploy(
        self, filepath: Path, table_name: str | None, scope: Scope
    ) -> ValidatedConfigFile:
        explicit_table_name = self._table_name_for(filepath, table_name, scope)
        return validate_config_file(self.repo_root, filepath, explicit_table_name)

    def _table_name_for(self, filepath: Path, table_name: str | None, scope: Scope) -> str:
        if scope == "file" and table_name:
            return table_name

        relative_path = self._relative_path(filepath)
        mapped_name = self.table_map.get(relative_path.as_posix())
        if mapped_name:
            return mapped_name

        if scope == "file" and not table_name:
            return Path(filepath).stem

        return relative_path.stem

    def _relative_path(self, filepath: Path) -> Path:
        absolute_path = filepath if filepath.is_absolute() else self.repo_root / filepath
        try:
            return absolute_path.resolve().relative_to(self.repo_root)
        except ValueError as exc:
            raise ValidationError(f"file must be inside repository: {filepath}") from exc

    def _changed_csv_files(self, changed_base: str | None, changed_head: str) -> list[Path]:
        command = ["git", "diff", "--name-only", "--diff-filter=ACMRT"]
        if changed_base:
            command.extend([changed_base, changed_head])
        else:
            command.extend([f"{changed_head}~1", changed_head])

        completed = subprocess.run(
            command,
            cwd=self.repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return [
            Path(line)
            for line in completed.stdout.splitlines()
            if line.startswith("config/") and line.endswith(".csv")
        ]

    def _deploy_file(
        self,
        env: Environment,
        config_file: ValidatedConfigFile,
        dry_run: bool,
        clear_table: bool,
        billing_mode: str,
        backup_s3_bucket: str | None,
        backup_s3_prefix: str,
    ) -> FileDeploymentResult:
        result = FileDeploymentResult(
            env=env,
            filepath=config_file.relative_path.as_posix(),
            file_name=config_file.file_name,
            table_name=config_file.table_name,
            partition_key=config_file.key_schema.partition_key,
            sort_key=config_file.key_schema.sort_key,
            column_list=config_file.columns,
            record_count=config_file.record_count,
        )

        try:
            result.table_existed = self.dynamodb_client.table_exists(config_file.table_name)
            if dry_run:
                result.status = "DRY_RUN"
                result.preview_rows = config_file.rows[:5]
                self._log_result(result)
                return result

            if not result.table_existed:
                self.dynamodb_client.create_table(
                    config_file.table_name,
                    config_file.key_schema,
                    billing_mode=billing_mode,
                )

            if clear_table:
                self.dynamodb_client.clear_table(config_file.table_name, config_file.key_schema)

            result.rows_inserted = self.dynamodb_client.upsert_items(
                config_file.table_name, config_file.rows
            )
            if backup_s3_bucket:
                backup_key = self._backup_s3_key(config_file.relative_path, backup_s3_prefix)
                result.backup_s3_uri = self.dynamodb_client.upload_file_to_s3(
                    str(config_file.path), backup_s3_bucket, backup_key
                )
            result.status = "SUCCESS"
        except Exception as exc:  # noqa: BLE001 - log and continue summary for all files
            result.status = "FAILED"
            result.rows_failed = config_file.record_count
            result.error_detail = str(exc)

        self._log_result(result)
        return result

    def _log_result(self, result: FileDeploymentResult) -> None:
        LOGGER.info(
            "ENV=%s FILEPATH=%s FILE_NAME=%s TABLE_NAME=%s PARTITION_KEY=%s "
            "SORT_KEY=%s COLUMN_LIST=%s RECORD_COUNT=%s ROWS_INSERTED=%s "
            "ROWS_UPDATED=%s ROWS_FAILED=%s STATUS=%s ERROR_DETAIL=%s BACKUP_S3_URI=%s",
            result.env,
            result.filepath,
            result.file_name,
            result.table_name,
            result.partition_key,
            result.sort_key,
            result.column_list,
            result.record_count,
            result.rows_inserted,
            result.rows_updated,
            result.rows_failed,
            result.status,
            result.error_detail,
            result.backup_s3_uri,
        )

    def _backup_s3_key(self, relative_path: Path, prefix: str) -> str:
        normalized_prefix = prefix.strip("/")
        key_parts = [part for part in [normalized_prefix, relative_path.as_posix()] if part]
        return "/".join(key_parts)
