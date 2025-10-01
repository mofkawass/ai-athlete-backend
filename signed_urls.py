import datetime
from google.cloud import storage

def get_v4_signed_put_url(client: storage.Client, bucket_name: str, blob_name: str, content_type: str, minutes: int = 15) -> str:
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=minutes),
        method="PUT",
        content_type=content_type,
    )
    return url

def get_v4_signed_get_url(client: storage.Client, bucket_name: str, blob_name: str, minutes: int = 60) -> str:
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=minutes),
        method="GET",
    )
    return url
