from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from .models import KeySchema, ValidatedConfigFile, ValidationError


ALLOWED_CONFIG_ROOTS = {"cde", "scf", "def"}
CONFIG_DIR_NAME = "config"
PK_PREFIX = "pk__"
SK_PREFIX = "sk__"


def validate_allowed_config_roots(repo_root: Path) -> None:
    config_dir = repo_root / CONFIG_DIR_NAME
    if not config_dir.exists():
        raise ValidationError("config directory does not exist")
    if not config_dir.is_dir():
        raise ValidationError("config path is not a directory")

    invalid_roots = [
        child.name
        for child in config_dir.iterdir()
        if child.is_dir() and child.name not in ALLOWED_CONFIG_ROOTS
    ]
    if invalid_roots:
        raise ValidationError(
            f"unsupported config root folder(s): {', '.join(sorted(invalid_roots))}"
        )


def validate_config_file(repo_root: Path, filepath: Path, table_name: str) -> ValidatedConfigFile:
    absolute_path = _resolve_path(repo_root, filepath)
    relative_path = _relative_to_repo(repo_root, absolute_path)

    _validate_file_location(relative_path)
    _validate_file_exists(absolute_path)
    _validate_table_name(absolute_path, table_name)

    headers, raw_rows = _read_csv(absolute_path)
    _validate_headers(headers)
    key_schema = _extract_key_schema(headers)
    rows = _normalize_rows(headers, raw_rows)
    _validate_key_values(rows, key_schema)
    _validate_duplicates(rows, key_schema)

    return ValidatedConfigFile(
        path=absolute_path,
        relative_path=relative_path,
        file_name=absolute_path.name,
        table_name=table_name,
        headers=headers,
        key_schema=key_schema,
        rows=rows,
    )


def _resolve_path(repo_root: Path, filepath: Path) -> Path:
    path = filepath if filepath.is_absolute() else repo_root / filepath
    return path.resolve()


def _relative_to_repo(repo_root: Path, filepath: Path) -> Path:
    try:
        return filepath.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValidationError(f"file must be inside repository: {filepath}") from exc


def _validate_file_location(relative_path: Path) -> None:
    parts = relative_path.parts
    if len(parts) < 3 or parts[0] != CONFIG_DIR_NAME:
        raise ValidationError(f"file must be under config/<cde|scf|def>: {relative_path}")
    if parts[1] not in ALLOWED_CONFIG_ROOTS:
        raise ValidationError(f"unsupported config root folder: {parts[1]}")


def _validate_file_exists(filepath: Path) -> None:
    if not filepath.exists():
        raise ValidationError(f"file does not exist: {filepath}")
    if not filepath.is_file():
        raise ValidationError(f"path is not a file: {filepath}")
    if filepath.suffix != ".csv":
        raise ValidationError(f"only .csv files are supported: {filepath}")


def _validate_table_name(filepath: Path, table_name: str) -> None:
    if not table_name:
        raise ValidationError("table_name is required")
    if Path(filepath).stem != table_name:
        raise ValidationError(
            f"table_name must match CSV file name: table_name={table_name}, file_stem={Path(filepath).stem}"
        )


def _read_csv(filepath: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with filepath.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                raise ValidationError(f"CSV header is missing: {filepath}")
            headers = list(reader.fieldnames)
            rows = []
            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    raise ValidationError(f"CSV row has more values than headers at row {row_number}")
                rows.append(dict(row))
    except UnicodeDecodeError as exc:
        raise ValidationError(f"CSV cannot be decoded as UTF-8: {filepath}") from exc
    except csv.Error as exc:
        raise ValidationError(f"CSV cannot be read: {filepath}: {exc}") from exc
    return headers, rows


def _validate_headers(headers: list[str]) -> None:
    if any(header is None or header.strip() == "" for header in headers):
        raise ValidationError("CSV header must not contain empty columns")
    duplicate_headers = sorted(
        header for header, count in Counter(headers).items() if count > 1
    )
    if duplicate_headers:
        raise ValidationError(f"CSV header contains duplicate columns: {duplicate_headers}")


def _extract_key_schema(headers: list[str]) -> KeySchema:
    pk_columns = [header for header in headers if header.startswith(PK_PREFIX)]
    sk_columns = [header for header in headers if header.startswith(SK_PREFIX)]

    if len(pk_columns) != 1:
        raise ValidationError(f"CSV must contain exactly one {PK_PREFIX} column")
    if len(sk_columns) > 1:
        raise ValidationError(f"CSV must contain at most one {SK_PREFIX} column")

    partition_source = pk_columns[0]
    partition_key = partition_source.removeprefix(PK_PREFIX)
    if not partition_key:
        raise ValidationError(f"{PK_PREFIX} column must include a key name")

    sort_source = sk_columns[0] if sk_columns else None
    sort_key = sort_source.removeprefix(SK_PREFIX) if sort_source else None
    if sort_source and not sort_key:
        raise ValidationError(f"{SK_PREFIX} column must include a key name")

    return KeySchema(
        partition_source=partition_source,
        partition_key=partition_key,
        sort_source=sort_source,
        sort_key=sort_key,
    )


def _normalize_rows(headers: list[str], raw_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_row in raw_rows:
        row: dict[str, Any] = {}
        for header in headers:
            target_header = _rename_header(header)
            value = raw_row.get(header)
            row[target_header] = None if value in (None, "") else str(value)
        rows.append(row)
    return rows


def _rename_header(header: str) -> str:
    if header.startswith(PK_PREFIX):
        return header.removeprefix(PK_PREFIX)
    if header.startswith(SK_PREFIX):
        return header.removeprefix(SK_PREFIX)
    return header


def _validate_key_values(rows: list[dict[str, Any]], key_schema: KeySchema) -> None:
    for row_number, row in enumerate(rows, start=2):
        if row[key_schema.partition_key] in (None, ""):
            raise ValidationError(f"partition key is empty at CSV row {row_number}")
        if key_schema.sort_key and row[key_schema.sort_key] in (None, ""):
            raise ValidationError(f"sort key is empty at CSV row {row_number}")


def _validate_duplicates(rows: list[dict[str, Any]], key_schema: KeySchema) -> None:
    seen: set[tuple[Any, ...]] = set()
    for row_number, row in enumerate(rows, start=2):
        if key_schema.sort_key:
            key = (row[key_schema.partition_key], row[key_schema.sort_key])
        else:
            key = (row[key_schema.partition_key],)
        if key in seen:
            raise ValidationError(f"duplicate key found at CSV row {row_number}: {key}")
        seen.add(key)
