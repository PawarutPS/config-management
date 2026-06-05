from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .config import AwsEnvironmentConfig
from .models import DeploymentError, KeySchema


class DynamoDBConfigClient:
    def __init__(self, env_config: AwsEnvironmentConfig):
        try:
            import boto3
        except ImportError as exc:
            raise DeploymentError("boto3 is required for DynamoDB deployment") from exc

        session_kwargs: dict[str, str] = {}
        if env_config.aws_profile:
            session_kwargs["profile_name"] = env_config.aws_profile
        if env_config.region:
            session_kwargs["region_name"] = env_config.region
        if env_config.aws_access_key_id:
            session_kwargs["aws_access_key_id"] = env_config.aws_access_key_id
        if env_config.aws_secret_access_key:
            session_kwargs["aws_secret_access_key"] = env_config.aws_secret_access_key
        if env_config.aws_session_token:
            session_kwargs["aws_session_token"] = env_config.aws_session_token

        session = boto3.Session(**session_kwargs)
        resource_kwargs: dict[str, str] = {}
        if env_config.endpoint_url:
            resource_kwargs["endpoint_url"] = env_config.endpoint_url

        self.resource = session.resource("dynamodb", **resource_kwargs)
        self.client = session.client("dynamodb", **resource_kwargs)
        self.s3_client = session.client("s3", **resource_kwargs)

    def table_exists(self, table_name: str) -> bool:
        try:
            self.client.describe_table(TableName=table_name)
            return True
        except self.client.exceptions.ResourceNotFoundException:
            return False

    def create_table(
        self,
        table_name: str,
        key_schema: KeySchema,
        billing_mode: str = "PAY_PER_REQUEST",
    ) -> None:
        key_schema_spec = [
            {"AttributeName": key_schema.partition_key, "KeyType": "HASH"},
        ]
        attribute_definitions = [
            {"AttributeName": key_schema.partition_key, "AttributeType": "S"},
        ]
        if key_schema.sort_key:
            key_schema_spec.append({"AttributeName": key_schema.sort_key, "KeyType": "RANGE"})
            attribute_definitions.append(
                {"AttributeName": key_schema.sort_key, "AttributeType": "S"}
            )

        table = self.resource.create_table(
            TableName=table_name,
            KeySchema=key_schema_spec,
            AttributeDefinitions=attribute_definitions,
            BillingMode=billing_mode,
        )
        table.wait_until_exists()

    def clear_table(self, table_name: str, key_schema: KeySchema) -> int:
        table = self.resource.Table(table_name)
        projection_names = {"#pk": key_schema.partition_key}
        projection_expression = "#pk"
        if key_schema.sort_key:
            projection_names["#sk"] = key_schema.sort_key
            projection_expression = "#pk, #sk"

        deleted = 0
        scan_kwargs: dict[str, Any] = {
            "ProjectionExpression": projection_expression,
            "ExpressionAttributeNames": projection_names,
        }

        while True:
            response = table.scan(**scan_kwargs)
            with table.batch_writer() as batch:
                for item in response.get("Items", []):
                    key = {key_schema.partition_key: item[key_schema.partition_key]}
                    if key_schema.sort_key:
                        key[key_schema.sort_key] = item[key_schema.sort_key]
                    batch.delete_item(Key=key)
                    deleted += 1

            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return deleted
            scan_kwargs["ExclusiveStartKey"] = last_key

    def upsert_items(self, table_name: str, items: Iterable[dict[str, Any]]) -> int:
        table = self.resource.Table(table_name)
        upserted = 0
        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)
                upserted += 1
        return upserted

    def upload_file_to_s3(self, filepath: str, bucket: str, key: str) -> str:
        self.s3_client.upload_file(filepath, bucket, key)
        return f"s3://{bucket}/{key}"
