from __future__ import annotations

from .config import load_env_config
from .dynamodb_client import DynamoDBConfigClient
from .models import DeployConfigFileRequest, DeploymentSummary
from .processor import ConfigProcessor


def deploy_config_file(request: DeployConfigFileRequest) -> DeploymentSummary:
    env_config = load_env_config(request.env, request.env_config_path)
    dynamodb_client = DynamoDBConfigClient(env_config)
    processor = ConfigProcessor(request.repo_root, dynamodb_client)
    return processor.deploy(
        env=request.env,
        scope="file",
        path=request.file_path,
        table_name=request.table_name,
        dry_run=request.dry_run,
        clear_table=request.clean_data_from_table,
        confirm_clear=request.clean_data_from_table,
        billing_mode=request.billing_mode,
    )
