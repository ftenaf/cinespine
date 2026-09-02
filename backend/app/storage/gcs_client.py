import os
import logging
from datetime import timedelta
from typing import Optional
from google.cloud import storage

logger = logging.getLogger(__name__)

class GCSClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GCSClient, cls).__new__(cls)
            cls._instance.client = None
            cls._instance.bucket_name = os.getenv("CINESPINE_GCS_BUCKET")
            if os.getenv("CINESPINE_USE_GCS") == "1" and cls._instance.bucket_name:
                try:
                    cls._instance.client = storage.Client()
                    logger.info("Initialized Google Cloud Storage client for bucket: %s", cls._instance.bucket_name)
                except Exception as e:
                    logger.error("Failed to initialize GCS Client: %s", e)
        return cls._instance

    @property
    def is_enabled(self) -> bool:
        return self.client is not None and self.bucket_name is not None

    def upload_file(self, object_name: str, content_bytes: bytes, content_type: str) -> Optional[str]:
        """Uploads a file to GCS and returns the gs:// URI."""
        if not self.is_enabled:
            return None
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(object_name)
            blob.upload_from_string(content_bytes, content_type=content_type)
            return f"gs://{self.bucket_name}/{object_name}"
        except Exception as e:
            logger.error("GCS Upload failed for %s: %s", object_name, e)
            return None

    def generate_signed_url(self, gcs_uri: str, expiration_minutes: int = 60) -> Optional[str]:
        """Generates a v4 signed URL for a gs:// URI."""
        if not self.is_enabled or not gcs_uri.startswith("gs://"):
            return None
        
        try:
            # Parse gs://bucket/path/to/object
            path = gcs_uri[5:]
            bucket_name, object_name = path.split("/", 1)
            
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=expiration_minutes),
                method="GET",
            )
            return url
        except Exception as e:
            logger.error("GCS Signed URL generation failed for %s: %s", gcs_uri, e)
            return None

# Singleton instance
gcs = GCSClient()
