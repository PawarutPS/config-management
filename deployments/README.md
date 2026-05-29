# Deployment Files

Create one Python file per config update workflow in this folder.

Use `DeployConfigFileRequest` to make parameters explicit:

- `env`: `dev`, `uat`, or `prod`
- `file_path`: CSV file to deploy
- `table_name`: required and must match the CSV file stem
- `dry_run`: `True` validates and previews only
- `clean_data_from_table`: `True` clears the table before upsert
- `env_config_path`: TOML file that maps environment to AWS profile/region

Run an update file after installing the package:

```bash
python3 deployments/update_config_a.py
```
