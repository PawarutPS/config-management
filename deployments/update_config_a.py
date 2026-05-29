from pathlib import Path

from dynamodb_config_manager.deployment import deploy_config_file
from dynamodb_config_manager.models import DeployConfigFileRequest


def update_config_a() -> None:
    summary = deploy_config_file(
        DeployConfigFileRequest(
            env="dev",
            file_path=Path("config/cde/dpf_config_sample.csv"),
            table_name="dpf_config_sample",
            dry_run=True,
            clean_data_from_table=False,
            env_config_path=Path("examples/env_config.toml"),
        )
    )
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    update_config_a()
