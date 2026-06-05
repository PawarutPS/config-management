from __future__ import annotations

from pathlib import Path

import pytest

from dynamodb_config_manager.models import KeySchema, ValidationError
from dynamodb_config_manager.processor import ConfigProcessor


class FakeDynamoDBClient:
    def __init__(self, table_exists: bool = True):
        self._table_exists = table_exists
        self.created_tables: list[tuple[str, KeySchema, str]] = []
        self.cleared_tables: list[str] = []
        self.upserted_items: list[tuple[str, list[dict[str, object]]]] = []
        self.uploaded_files: list[tuple[str, str, str]] = []

    def table_exists(self, table_name: str) -> bool:
        return self._table_exists

    def create_table(
        self, table_name: str, key_schema: KeySchema, billing_mode: str = "PAY_PER_REQUEST"
    ) -> None:
        self.created_tables.append((table_name, key_schema, billing_mode))

    def clear_table(self, table_name: str, key_schema: KeySchema) -> int:
        self.cleared_tables.append(table_name)
        return 0

    def upsert_items(self, table_name: str, items: list[dict[str, object]]) -> int:
        item_list = list(items)
        self.upserted_items.append((table_name, item_list))
        return len(item_list)

    def upload_file_to_s3(self, filepath: str, bucket: str, key: str) -> str:
        self.uploaded_files.append((filepath, bucket, key))
        return f"s3://{bucket}/{key}"


def write_repo_csv(repo_root: Path) -> None:
    (repo_root / "config/cde").mkdir(parents=True)
    (repo_root / "config/scf").mkdir(parents=True)
    (repo_root / "config/def").mkdir(parents=True)
    (repo_root / "config/cde/dpf_config_sample.csv").write_text(
        "pk__config_no,name\n001,CONFIG_A\n",
        encoding="utf-8",
    )


def test_dry_run_does_not_write_to_dynamodb(tmp_path: Path) -> None:
    write_repo_csv(tmp_path)
    fake_client = FakeDynamoDBClient(table_exists=False)
    processor = ConfigProcessor(tmp_path, fake_client)

    summary = processor.deploy(
        env="dev",
        scope="file",
        path=Path("config/cde/dpf_config_sample.csv"),
        table_name="dpf_config_sample",
        dry_run=True,
    )

    assert summary.status == "DRY_RUN"
    assert fake_client.created_tables == []
    assert fake_client.cleared_tables == []
    assert fake_client.upserted_items == []
    assert summary.results[0].preview_rows == [{"config_no": "001", "name": "CONFIG_A"}]


def test_deploy_creates_missing_table_and_upserts(tmp_path: Path) -> None:
    write_repo_csv(tmp_path)
    fake_client = FakeDynamoDBClient(table_exists=False)
    processor = ConfigProcessor(tmp_path, fake_client)

    summary = processor.deploy(
        env="dev",
        scope="file",
        path=Path("config/cde/dpf_config_sample.csv"),
        table_name="dpf_config_sample",
        dry_run=False,
    )

    assert summary.status == "SUCCESS"
    assert fake_client.created_tables[0][0] == "dpf_config_sample"
    assert fake_client.upserted_items == [
        ("dpf_config_sample", [{"config_no": "001", "name": "CONFIG_A"}])
    ]


def test_clear_table_requires_confirmation(tmp_path: Path) -> None:
    write_repo_csv(tmp_path)
    fake_client = FakeDynamoDBClient()
    processor = ConfigProcessor(tmp_path, fake_client)

    with pytest.raises(ValidationError, match="confirm_clear"):
        processor.deploy(
            env="dev",
            scope="file",
            path=Path("config/cde/dpf_config_sample.csv"),
            table_name="dpf_config_sample",
            dry_run=False,
            clear_table=True,
            confirm_clear=False,
        )


def test_all_scope_uses_file_stem_as_table_name(tmp_path: Path) -> None:
    write_repo_csv(tmp_path)
    fake_client = FakeDynamoDBClient()
    processor = ConfigProcessor(tmp_path, fake_client)

    summary = processor.deploy(env="dev", scope="all", dry_run=True)

    assert summary.status == "DRY_RUN"
    assert summary.results[0].table_name == "dpf_config_sample"


def test_all_scope_can_override_table_name_with_table_map(tmp_path: Path) -> None:
    write_repo_csv(tmp_path)
    fake_client = FakeDynamoDBClient()
    processor = ConfigProcessor(
        tmp_path,
        fake_client,
        {"config/cde/dpf_config_sample.csv": "dpf_config_sample"},
    )

    summary = processor.deploy(env="dev", scope="all", dry_run=True)

    assert summary.status == "DRY_RUN"
    assert summary.results[0].table_name == "dpf_config_sample"


def test_file_scope_uses_file_stem_when_table_name_is_not_provided(tmp_path: Path) -> None:
    write_repo_csv(tmp_path)
    fake_client = FakeDynamoDBClient()
    processor = ConfigProcessor(tmp_path, fake_client)

    summary = processor.deploy(
        env="dev",
        scope="file",
        path=Path("config/cde/dpf_config_sample.csv"),
        dry_run=True,
    )

    assert summary.status == "DRY_RUN"
    assert summary.results[0].table_name == "dpf_config_sample"


def test_deploy_uploads_changed_csv_to_s3_backup(tmp_path: Path) -> None:
    write_repo_csv(tmp_path)
    fake_client = FakeDynamoDBClient(table_exists=True)
    processor = ConfigProcessor(tmp_path, fake_client)

    summary = processor.deploy(
        env="dev",
        scope="file",
        path=Path("config/cde/dpf_config_sample.csv"),
        dry_run=False,
        backup_s3_bucket="config-backup-bucket",
        backup_s3_prefix="dynamodb-config-backup",
    )

    assert summary.status == "SUCCESS"
    assert summary.results[0].backup_s3_uri == (
        "s3://config-backup-bucket/dynamodb-config-backup/config/cde/dpf_config_sample.csv"
    )
    assert fake_client.uploaded_files == [
        (
            str(tmp_path / "config/cde/dpf_config_sample.csv"),
            "config-backup-bucket",
            "dynamodb-config-backup/config/cde/dpf_config_sample.csv",
        )
    ]


def test_dry_run_does_not_upload_s3_backup(tmp_path: Path) -> None:
    write_repo_csv(tmp_path)
    fake_client = FakeDynamoDBClient(table_exists=True)
    processor = ConfigProcessor(tmp_path, fake_client)

    summary = processor.deploy(
        env="dev",
        scope="file",
        path=Path("config/cde/dpf_config_sample.csv"),
        dry_run=True,
        backup_s3_bucket="config-backup-bucket",
        backup_s3_prefix="dynamodb-config-backup",
    )

    assert summary.status == "DRY_RUN"
    assert fake_client.uploaded_files == []
