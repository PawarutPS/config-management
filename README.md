# DynamoDB Config Manager

Python repository for managing DynamoDB config data from CSV files with Git as the source of truth.

The target workflow is simple:

```text
User uploads or edits CSV
  -> Merge Request review
  -> Merge
  -> Jenkins detects changed CSV files
  -> Jenkins uploads changed config into DynamoDB
```

Users do not create deployment scripts and do not enter table parameters manually. Jenkins deploys the changed CSV files.

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

## Table Name Rule

For the Jenkins changed-file workflow, table name comes from the CSV file name.

Example:

```text
config/cde/loc/dpf_config_location.csv -> dpf_config_location
```

This means users only need to upload or edit CSV files in the correct folder.

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

## Jenkins Deployment

Jenkins should run changed-file deployment after merge.

Dry run validation:

```bash
dynamodb-config-manager \
  --env dev \
  --env-config examples/env_config.toml \
  --scope changed \
  --changed-base origin/main \
  --changed-head HEAD
```

Actual deploy with S3 backup:

```bash
dynamodb-config-manager \
  --env dev \
  --env-config examples/env_config.toml \
  --scope changed \
  --changed-base origin/main \
  --changed-head HEAD \
  --no-dry-run \
  --backup-s3-bucket my-config-backup-bucket \
  --backup-s3-prefix dynamodb-config-backup
```

Dry run validates files, checks whether each DynamoDB table exists, and previews rows. It does not create tables, clear data, upsert data, or upload S3 backups.

Deploy mode creates a missing table using string keys from `pk__` and optional `sk__`, upserts data, then uploads each successfully deployed CSV to S3. The backup object key is `<backup-s3-prefix>/<env>/<relative csv path>`.

A Jenkins pipeline example is available at `examples/Jenkinsfile`. It generates the CLI command, prints it for audit, then executes it.

## Optional Clear Table

Clearing a table is disabled by default. If a pipeline needs to clear existing data before upsert, both flags are required:

```bash
dynamodb-config-manager \
  --env dev \
  --env-config examples/env_config.toml \
  --scope changed \
  --changed-base origin/main \
  --changed-head HEAD \
  --no-dry-run \
  --clear-table \
  --confirm-clear
```

If `--clear-table` is set without `--confirm-clear`, the tool raises an error before any DynamoDB write.

## Manual Commands

Manual commands are still available for local validation or troubleshooting.

```bash
# Validate and preview one file
dynamodb-config-manager --env dev --scope file --path config/cde/dpf_config_sample.csv

# Validate and preview all CSV files
dynamodb-config-manager --env dev --scope all

# Validate and preview one folder
dynamodb-config-manager --env dev --scope folder --path config/cde
```

## Logging

Each processed file logs:

```text
ENV FILEPATH FILE_NAME TABLE_NAME PARTITION_KEY SORT_KEY COLUMN_LIST RECORD_COUNT ROWS_INSERTED ROWS_UPDATED ROWS_FAILED STATUS ERROR_DETAIL
```

## Local Development

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
```
