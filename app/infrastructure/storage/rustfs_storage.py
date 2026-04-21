import asyncio
import boto3
from botocore.exceptions import ClientError
from app.domain.ports.storage_port import IStoragePort

class RustFSStorage(IStoragePort):
    def __init__(self, endpoint: str, access_key: str, secret_key: str):
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
        )

    async def upload_file(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=bucket, Key=key, Body=data, ContentType=content_type,
        )
        return key

    async def download_file(self, bucket: str, key: str) -> bytes:
        resp = await asyncio.to_thread(
            self._client.get_object, Bucket=bucket, Key=key
        )
        return resp["Body"].read()

    async def get_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    async def ensure_buckets(self, *bucket_names: str) -> None:
        """Create buckets if they don't exist. Call on app startup."""
        for name in bucket_names:
            try:
                await asyncio.to_thread(self._client.head_bucket, Bucket=name)
            except ClientError:
                await asyncio.to_thread(self._client.create_bucket, Bucket=name)