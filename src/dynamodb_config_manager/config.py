from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Environment, ValidationError


@dataclass(frozen=True)
class AwsEnvironmentConfig:
    env: Environment
    region: str | None = None
    aws_profile: str | None = None
    endpoint_url: str | None = None
    account_id: str | None = None


def load_env_config(env: Environment, config_path: Path | None) -> AwsEnvironmentConfig:
    path = config_path or _config_path_from_env()
    if path is None:
        return AwsEnvironmentConfig(env=env)

    if not path.exists():
        raise ValidationError(f"environment config file does not exist: {path}")

    with path.open("rb") as config_file:
        data = tomllib.load(config_file)

    env_data = data.get("env", {}).get(env)
    if not isinstance(env_data, dict):
        raise ValidationError(f"environment mapping is missing for env: {env}")

    return AwsEnvironmentConfig(
        env=env,
        region=_optional_str(env_data, "region"),
        aws_profile=_optional_str(env_data, "aws_profile"),
        endpoint_url=_optional_str(env_data, "endpoint_url"),
        account_id=_optional_str(env_data, "account_id"),
    )


def load_table_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    if not path.exists():
        raise ValidationError(f"table map file does not exist: {path}")

    with path.open("rb") as table_map_file:
        data = tomllib.load(table_map_file)

    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise ValidationError("table map file must contain a [tables] section")

    table_map: dict[str, str] = {}
    for filepath, table_name in tables.items():
        if not isinstance(filepath, str) or not isinstance(table_name, str):
            raise ValidationError("table map keys and values must be strings")
        table_map[filepath] = table_name
    return table_map


def _config_path_from_env() -> Path | None:
    value = os.getenv("DCM_ENV_CONFIG")
    return Path(value) if value else None


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"environment config value must be a string: {key}")
    return value
