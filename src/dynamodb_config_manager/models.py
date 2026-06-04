from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Environment = Literal["dev", "uat", "prod"]
Scope = Literal["all", "file", "folder", "changed"]
Status = Literal["SUCCESS", "FAILED", "DRY_RUN"]


class ConfigManagerError(Exception):
    """Base exception for expected config manager failures."""


class ValidationError(ConfigManagerError):
    """Raised when a config file or deployment input is invalid."""


class DeploymentError(ConfigManagerError):
    """Raised when DynamoDB deployment fails."""


class ConfigBaseModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)


class KeySchema(ConfigBaseModel):
    partition_source: str
    partition_key: str
    sort_source: str | None = None
    sort_key: str | None = None


class ValidatedConfigFile(ConfigBaseModel):
    path: Path
    relative_path: Path
    file_name: str
    table_name: str
    headers: list[str]
    key_schema: KeySchema
    rows: list[dict[str, Any]]

    @property
    def record_count(self) -> int:
        return len(self.rows)

    @property
    def columns(self) -> list[str]:
        return list(self.rows[0].keys()) if self.rows else _renamed_headers(self.headers)


class FileDeploymentResult(ConfigBaseModel):
    env: Environment
    filepath: str
    file_name: str
    table_name: str
    partition_key: str
    sort_key: str | None
    column_list: list[str]
    record_count: int
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_failed: int = 0
    status: Status = "SUCCESS"
    error_detail: str | None = None
    table_existed: bool | None = None
    backup_s3_uri: str | None = None
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def rows_upserted(self) -> int:
        return self.rows_inserted + self.rows_updated


class DeploymentSummary(ConfigBaseModel):
    env: Environment
    results: list[FileDeploymentResult]

    @property
    def status(self) -> Status:
        if any(result.status == "FAILED" for result in self.results):
            return "FAILED"
        if all(result.status == "DRY_RUN" for result in self.results):
            return "DRY_RUN"
        return "SUCCESS"


def _renamed_headers(headers: list[str]) -> list[str]:
    renamed = []
    for header in headers:
        if header.startswith("pk__"):
            renamed.append(header.removeprefix("pk__"))
        elif header.startswith("sk__"):
            renamed.append(header.removeprefix("sk__"))
        else:
            renamed.append(header)
    return renamed
