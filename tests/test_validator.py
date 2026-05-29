from __future__ import annotations

from pathlib import Path

import pytest

from dynamodb_config_manager.models import ValidationError
from dynamodb_config_manager.validator import (
    validate_allowed_config_roots,
    validate_config_file,
)


def write_csv(repo_root: Path, relative_path: str, content: str) -> Path:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_validate_csv_renames_keys_and_keeps_empty_values_as_none(tmp_path: Path) -> None:
    write_csv(
        tmp_path,
        "config/cde/dpf_config_sample.csv",
        "pk__config_no,sk__type,name,description\n001,A,CONFIG_A,\n",
    )
    (tmp_path / "config/scf").mkdir(parents=True)
    (tmp_path / "config/def").mkdir(parents=True)

    result = validate_config_file(
        tmp_path,
        Path("config/cde/dpf_config_sample.csv"),
        "dpf_config_sample",
    )

    assert result.key_schema.partition_key == "config_no"
    assert result.key_schema.sort_key == "type"
    assert result.rows == [
        {
            "config_no": "001",
            "type": "A",
            "name": "CONFIG_A",
            "description": None,
        }
    ]


def test_validate_rejects_duplicate_pk_only(tmp_path: Path) -> None:
    write_csv(
        tmp_path,
        "config/cde/dpf_config_sample.csv",
        "pk__config_no,name\n001,CONFIG_A\n001,CONFIG_B\n",
    )

    with pytest.raises(ValidationError, match="duplicate key"):
        validate_config_file(
            tmp_path,
            Path("config/cde/dpf_config_sample.csv"),
            "dpf_config_sample",
        )


def test_validate_rejects_duplicate_pk_and_sk(tmp_path: Path) -> None:
    write_csv(
        tmp_path,
        "config/cde/dpf_config_sample.csv",
        "pk__config_no,sk__type,name\n001,A,CONFIG_A\n001,A,CONFIG_B\n",
    )

    with pytest.raises(ValidationError, match="duplicate key"):
        validate_config_file(
            tmp_path,
            Path("config/cde/dpf_config_sample.csv"),
            "dpf_config_sample",
        )


def test_validate_rejects_empty_key_values(tmp_path: Path) -> None:
    write_csv(
        tmp_path,
        "config/cde/dpf_config_sample.csv",
        "pk__config_no,sk__type,name\n001,,CONFIG_A\n",
    )

    with pytest.raises(ValidationError, match="sort key is empty"):
        validate_config_file(
            tmp_path,
            Path("config/cde/dpf_config_sample.csv"),
            "dpf_config_sample",
        )


def test_validate_rejects_table_name_mismatch(tmp_path: Path) -> None:
    write_csv(
        tmp_path,
        "config/cde/dpf_config_sample.csv",
        "pk__config_no,name\n001,CONFIG_A\n",
    )

    with pytest.raises(ValidationError, match="table_name must match"):
        validate_config_file(
            tmp_path,
            Path("config/cde/dpf_config_sample.csv"),
            "another_table",
        )


def test_validate_rejects_invalid_config_root(tmp_path: Path) -> None:
    (tmp_path / "config/cde").mkdir(parents=True)
    (tmp_path / "config/scf").mkdir(parents=True)
    (tmp_path / "config/def").mkdir(parents=True)
    (tmp_path / "config/bad").mkdir(parents=True)

    with pytest.raises(ValidationError, match="unsupported config root"):
        validate_allowed_config_roots(tmp_path)


def test_validate_rejects_duplicate_headers(tmp_path: Path) -> None:
    write_csv(
        tmp_path,
        "config/cde/dpf_config_sample.csv",
        "pk__config_no,name,name\n001,CONFIG_A,CONFIG_B\n",
    )

    with pytest.raises(ValidationError, match="duplicate columns"):
        validate_config_file(
            tmp_path,
            Path("config/cde/dpf_config_sample.csv"),
            "dpf_config_sample",
        )


def test_validate_converts_missing_trailing_values_to_none(tmp_path: Path) -> None:
    write_csv(
        tmp_path,
        "config/cde/dpf_config_sample.csv",
        "pk__config_no,name,description\n001,CONFIG_A\n",
    )

    result = validate_config_file(
        tmp_path,
        Path("config/cde/dpf_config_sample.csv"),
        "dpf_config_sample",
    )

    assert result.rows[0]["description"] is None


def test_validate_rejects_rows_with_extra_values(tmp_path: Path) -> None:
    write_csv(
        tmp_path,
        "config/cde/dpf_config_sample.csv",
        "pk__config_no,name\n001,CONFIG_A,EXTRA\n",
    )

    with pytest.raises(ValidationError, match="more values than headers"):
        validate_config_file(
            tmp_path,
            Path("config/cde/dpf_config_sample.csv"),
            "dpf_config_sample",
        )
