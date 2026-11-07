"""
Firebase Storage Service & Token-Based CDN Helper
"""

import base64
import uuid
import urllib.parse
from typing import Tuple, Optional
from .firebase_service import get_storage_bucket
from ..core.config import settings


class StorageService:
    def __init__(self):
        self._bucket = None

    @property
    def bucket(self):
        if self._bucket is None:
            self._bucket = get_storage_bucket()
        return self._bucket

    def upload_fire_snapshot(
        self,
        group_id: str,
        cam_id: str,
        alert_id: str,
        image_data: str | bytes,
        filename: str = "initial_detected.jpg",
    ) -> Tuple[str, str]:
        """
        Upload snapshot frame to Firebase Storage and generate fixed Token-based Download URL.
        Returns: (storage_path, token_based_download_url)
        """
        # Convert base64 if string
        if isinstance(image_data, str):
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            raw_bytes = base64.b64decode(image_data)
        else:
            raw_bytes = image_data

        storage_path = f"fire_alerts/{group_id}/{cam_id}/{alert_id}/{filename}"
        download_token = str(uuid.uuid4())

        if self.bucket is not None:
            try:
                blob = self.bucket.blob(storage_path)
                blob.metadata = {"firebaseStorageDownloadTokens": download_token}
                blob.upload_from_string(raw_bytes, content_type="image/jpeg")

                encoded_path = urllib.parse.quote(storage_path, safe="")
                bucket_name = self.bucket.name
                download_url = (
                    f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{encoded_path}"
                    f"?alt=media&token={download_token}"
                )
                return storage_path, download_url
            except Exception as e:
                # Log and fallback to mock URL
                print(f"⚠️ Warning: Storage upload failed ({e}), using fallback CDN URL")

        # Fallback CDN URL for local/testing
        encoded_path = urllib.parse.quote(storage_path, safe="")
        bucket_name = settings.FIREBASE_STORAGE_BUCKET
        download_url = (
            f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{encoded_path}"
            f"?alt=media&token={download_token}"
        )
        return storage_path, download_url

    def upload_camera_thumbnail(
        self,
        cam_id: str,
        image_data: str | bytes,
        content_type: str = "image/png",
    ) -> Tuple[str, str]:
        """
        Upload camera snapshot-on-exit frame to Firebase Storage.
        Appends ?v=<timestamp> cache buster for client freshness.
        Returns: (storage_path, token_based_download_url)
        """
        import time

        if isinstance(image_data, str):
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            raw_bytes = base64.b64decode(image_data)
        else:
            raw_bytes = image_data

        ext = "png" if "png" in content_type.lower() else "jpg"
        storage_path = f"cameras/{cam_id}/thumbnail.{ext}"
        download_token = str(uuid.uuid4())
        cache_buster = int(time.time())

        if self.bucket is not None:
            try:
                blob = self.bucket.blob(storage_path)
                blob.metadata = {"firebaseStorageDownloadTokens": download_token}
                blob.upload_from_string(raw_bytes, content_type=content_type)

                encoded_path = urllib.parse.quote(storage_path, safe="")
                bucket_name = self.bucket.name
                download_url = (
                    f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{encoded_path}"
                    f"?alt=media&token={download_token}&v={cache_buster}"
                )
                return storage_path, download_url
            except Exception as e:
                print(f"⚠️ Warning: Storage upload failed ({e}), using fallback CDN URL")

        encoded_path = urllib.parse.quote(storage_path, safe="")
        bucket_name = settings.FIREBASE_STORAGE_BUCKET
        download_url = (
            f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{encoded_path}"
            f"?alt=media&token={download_token}&v={cache_buster}"
        )
        return storage_path, download_url


_storage_service_instance: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    global _storage_service_instance
    if _storage_service_instance is None:
        _storage_service_instance = StorageService()
    return _storage_service_instance
