# DynamoDB Config Manager

Python repository for managing DynamoDB config data from CSV files with Git as the source of truth.

The command-line interface is implemented with Typer. Jenkins runs it with `python3 dynamodb_config_manager/cli.py`, and Typer validates input types from the function signature.

Jenkins jobs are separated by environment, so the CLI does not require `--env`. AWS credentials should come from Jenkins AK/SK credentials or standard AWS environment variables.

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
dynamodb_config_manager/
tests/
examples/
Jenkinsfile
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

AWS credentials are externalized. No AWS account, access key, secret key, profile, endpoint, or region is hardcoded.

Preferred Jenkins setup uses standard AWS environment variables:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN optional
AWS_DEFAULT_REGION
```

For Jenkins, configure AK/SK with Jenkins credentials and set region with `AWS_DEFAULT_REGION`. The CLI does not require `--env` or `--env-config` when each Jenkins job already maps to one environment.

## Jenkins Deployment

Jenkins should run changed-file deployment after merge.

Dry run validation:

```bash
python3 dynamodb_config_manager/cli.py \
  --scope changed \
  --changed-base origin/main \
  --changed-head HEAD
```

Actual deploy with S3 backup:

```bash
python3 dynamodb_config_manager/cli.py \
  --scope changed \
  --changed-base origin/main \
  --changed-head HEAD \
  --no-dry-run \
  --clear-table \
  --confirm-clear \
  --backup-s3-bucket my-config-backup-bucket \
  --backup-s3-prefix dynamodb-config-backup
```

Dry run validates files, checks whether each DynamoDB table exists, and previews rows. It does not create tables, clear data, upsert data, or upload S3 backups.

Deploy mode creates a missing table using string keys from `pk__` and optional `sk__`, upserts data, then uploads each successfully deployed CSV to S3. The backup object key is `<backup-s3-prefix>/<relative csv path>`.

A Jenkins pipeline example is available at `Jenkinsfile`. It generates the CLI command, prints it for audit, then executes it.

## Deleted CSV Files

By default, deleting a CSV file does not delete the DynamoDB table. To make a deleted CSV remove the matching table, enable both safety flags:

```bash
python3 dynamodb_config_manager/cli.py \
  --scope changed \
  --changed-base HEAD~1 \
  --changed-head HEAD \
  --no-dry-run \
  --delete-removed-tables \
  --confirm-delete-tables
```

When enabled, the table name is resolved from the deleted CSV file stem. For example, deleting `config/cde/cat_table.csv` deletes DynamoDB table `cat_table` if it exists.

## Optional Clear Table

Clearing a table is disabled by default. If a pipeline needs to clear existing data before upsert, both flags are required:

```bash
python3 dynamodb_config_manager/cli.py \
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
python3 dynamodb_config_manager/cli.py --scope file --path config/cde/dpf_config_sample.csv

# Validate and preview all CSV files
python3 dynamodb_config_manager/cli.py --scope all

# Validate and preview one folder
python3 dynamodb_config_manager/cli.py --scope folder --path config/cde
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
