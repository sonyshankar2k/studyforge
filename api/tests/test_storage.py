"""Storage backends. S3 is tested against moto, an in-memory fake of the AWS API."""

import boto3
import pytest
from moto import mock_aws

from app.storage import LocalStorage, S3Storage

BUCKET = "studyforge-test-uploads"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


async def test_s3_round_trip_is_encrypted(s3_client):
    storage = S3Storage(BUCKET, client=s3_client)
    key = await storage.save(b"%PDF-1.4 hello", ".pdf")

    assert key.startswith("protocols/") and key.endswith(".pdf")
    assert await storage.read(key) == b"%PDF-1.4 hello"
    head = s3_client.head_object(Bucket=BUCKET, Key=key)
    assert head["ServerSideEncryption"] == "AES256"
    assert head["ContentType"] == "application/pdf"

    await storage.delete(key)
    assert s3_client.list_objects_v2(Bucket=BUCKET).get("KeyCount") == 0


async def test_s3_rejects_keys_outside_its_prefix(s3_client):
    storage = S3Storage(BUCKET, client=s3_client)
    with pytest.raises(ValueError):
        await storage.read("../secrets.txt")
    with pytest.raises(ValueError):
        await storage.read("other-prefix/file.pdf")


async def test_s3_delete_of_a_missing_key_is_harmless(s3_client):
    await S3Storage(BUCKET, client=s3_client).delete("protocols/missing.pdf")


async def test_local_storage_round_trip_and_path_safety(tmp_path):
    storage = LocalStorage(tmp_path)
    key = await storage.save(b"text", ".txt")
    assert await storage.read(key) == b"text"
    with pytest.raises(ValueError):
        await storage.read("../../etc/passwd")
