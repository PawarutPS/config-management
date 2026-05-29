# DynamoDB Config Manager

Python repository for managing DynamoDB config data from CSV files with Git as the source of truth.

## Repository Layout

```text
config/
├── cde/
├── scf/
└── def/
src/dynamodb_config_manager/
tests/
examples/
```

Only `config/cde`, `config/scf`, and `config/def` are valid root folders. Any other folder directly under `config/` raises an error.

## CSV Rules

- Only `.csv` files are supported.
- Header must exist, must not contain empty names, and must not contain duplicate names.
- Exactly one partition key column is required with prefix `pk__`.
- At most one sort key column is allowed with prefix `sk__`.
- Empty CSV values become `None`/DynamoDB `NULL`, not `"None"` or `"null"`.
- Key values must not be empty.
- Duplicate keys raise an error.

Example:

```csv
pk__config_no,sk__type,name,description
001,A,CONFIG_A,
001,B,CONFIG_B,test
```

Before writing to DynamoDB, key prefixes are removed:

```json
{
  "config_no": "001",
  "type": "A",
  "name": "CONFIG_A",
  "description": null
}
```

## Table Names

`table_name` is always explicit. The tool never derives the table name from the CSV file path.

For `--scope file`, pass `--table-name`:

```bash
dynamodb-config-manager \
  --env dev \
  --scope file \
  --path config/cde/dpf_config_sample.csv \
  --table-name dpf_config_sample \
  --dry-run
```

For `--scope all`, `--scope folder`, or `--scope changed`, pass a TOML table map:

```toml
[tables]
"config/cde/loc/dpf_config_location.csv" = "dpf_config_location"
```

The explicit table name must match `Path(filepath).stem`; otherwise the process stops.

## Environment Mapping

Environment-to-AWS mapping is externalized. No AWS account, profile, endpoint, or region is hardcoded.

Use `--env-config` or set `DCM_ENV_CONFIG`:

```toml
[env.dev]
aws_profile = "my-dev-profile"
region = "ap-southeast-1"

[env.uat]
aws_profile = "my-uat-profile"
region = "ap-southeast-1"

[env.prod]
aws_profile = "my-prod-profile"
region = "ap-southeast-1"
```

Supported environments are `dev`, `uat`, and `prod`.

## Deploy Modes

Dry run is the default:

```bash
dynamodb-config-manager --env dev --scope file --path config/cde/dpf_config_sample.csv --table-name dpf_config_sample
```

Dry run performs validation, checks whether the DynamoDB table exists, and previews rows. It does not create tables, clear data, or upsert data.

Deploy mode uses `--no-dry-run`:

```bash
dynamodb-config-manager \
  --env dev \
  --scope file \
  --path config/cde/dpf_config_sample.csv \
  --table-name dpf_config_sample \
  --no-dry-run
```

If a table does not exist, the tool creates it using string keys from `pk__` and optional `sk__` columns. The default billing mode is `PAY_PER_REQUEST`; override with `--billing-mode` when needed.

## Python Update Files

User-managed deploy files can be created under `deployments/`. Each file should call `deploy_config_file()` with a Pydantic request model.

Example: `deployments/update_config_a.py`

```python
from pathlib import Path

from dynamodb_config_manager.deployment import deploy_config_file
from dynamodb_config_manager.models import DeployConfigFileRequest


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
```

Set `clean_data_from_table=True` when the table must be cleared before upsert. The helper automatically sends the required clear confirmation for that file-level deployment.

## Clear Table

Clearing a table is guarded by two flags:

```bash
dynamodb-config-manager \
  --env dev \
  --scope file \
  --path config/cde/dpf_config_sample.csv \
  --table-name dpf_config_sample \
  --no-dry-run \
  --clear-table \
  --confirm-clear
```

If `--clear-table` is set without `--confirm-clear`, the tool raises an error before any DynamoDB write.

## Deploy Scopes

```bash
# All CSV files under config/
dynamodb-config-manager --env dev --scope all --table-map examples/table_map.toml

# One CSV file
dynamodb-config-manager --env dev --scope file --path config/cde/dpf_config_sample.csv --table-name dpf_config_sample

# One folder
dynamodb-config-manager --env dev --scope folder --path config/cde --table-map examples/table_map.toml

# Changed CSV files for CI/CD
dynamodb-config-manager --env dev --scope changed --changed-base origin/main --changed-head HEAD --table-map examples/table_map.toml
```

## Logging

Each processed file logs:

```text
ENV FILEPATH FILE_NAME TABLE_NAME PARTITION_KEY SORT_KEY COLUMN_LIST RECORD_COUNT ROWS_INSERTED ROWS_UPDATED ROWS_FAILED STATUS ERROR_DETAIL
```

## Local Development

```bash
python -m pip install -e ".[dev]"
pytest
```
