"""
MediaMTX Integration Service for Mắt Phố
Communicates with MediaMTX Control REST API (Port 9997) to dynamically add/remove RTSP paths.
"""

import os
import logging
import httpx
from typing import Optional, List

logger = logging.getLogger("backend.mediamtx")

MEDIAMTX_API_URL = os.getenv("MEDIAMTX_API_URL", "http://127.0.0.1:9997")


class MediaMTXService:
    def __init__(self, api_url: str = MEDIAMTX_API_URL):
        self.api_url = api_url.rstrip("/")

    def _candidate_urls(self, path: str) -> List[str]:
        # On Google Cloud Run (K_SERVICE env is set), MediaMTX does not run on localhost/container;
        # camera sync goes through Outbound Edge WebSocket (/internal/edge/ws) instead.
        if os.getenv("K_SERVICE"):
            if "mediamtx" not in self.api_url and "localhost" not in self.api_url and "127.0.0.1" not in self.api_url:
                return [f"{self.api_url}{path}"]
            return []

        is_docker = os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "true"
        if not is_docker:
            urls = [f"http://127.0.0.1:9997{path}", f"http://localhost:9997{path}"]
            if "mediamtx" not in self.api_url:
                urls.insert(0, f"{self.api_url}{path}")
            return list(dict.fromkeys(urls))
        urls = [f"{self.api_url}{path}"]
        if "mediamtx:9997" in self.api_url:
            urls.extend([
                f"http://127.0.0.1:9997{path}",
                f"http://host.docker.internal:9997{path}",
            ])
        return list(dict.fromkeys(urls))

    def add_path(self, cam_id: str, rtsp_source: str) -> bool:
        """
        Dynamically registers an RTSP source in MediaMTX.
        Path will be available at:
          - RTSP: rtsp://mediamtx:8554/live/{cam_id}
          - HLS: http://mediamtx:8888/live/{cam_id}/index.m3u8
        """
        actual_source = rtsp_source.strip()
        if any(k in actual_source.lower() for k in ("mock", "test", "demo")):
            actual_source = "rtsp://127.0.0.1:8554/mock/cam_test"
        elif ":8554/" in actual_source:
            for local_alias in ("rtsp://127.0.0.1:8554/", "rtsp://localhost:8554/", "rtsp://0.0.0.0:8554/", "rtsp://10.0.2.2:8554/", "rtsp://mediamtx:8554/"):
                if actual_source.lower().startswith(local_alias):
                    actual_source = "rtsp://127.0.0.1:8554/" + actual_source[len(local_alias):]
                    break

        payload = {
            "source": "publisher",
            "fallback": f"/{actual_source.split(':8554/', 1)[1]}" if ":8554/" in actual_source else "/mock/cam_test",
        }

        prefixes = ["live", "app"]
        success = False
        for prefix in prefixes:
            for base_url in self._candidate_urls(""):
                url = f"{base_url}/v3/config/paths/add/{prefix}/{cam_id}"
                try:
                    with httpx.Client(timeout=2.0) as client:
                        res = client.post(url, json=payload)
                        if res.status_code in (200, 201):
                            logger.info(f"Added MediaMTX path {prefix}/{cam_id}")
                            success = True
                            break
                        elif res.status_code == 400 and "already exists" in res.text:
                            patch_url = f"{base_url}/v3/config/paths/patch/{prefix}/{cam_id}"
                            patch_res = client.patch(patch_url, json=payload)
                            if patch_res.status_code in (200, 204):
                                success = True
                                break
                except Exception:
                    pass
        return success

    def remove_path(self, cam_id: str) -> bool:
        """Removes a dynamic path from MediaMTX."""
        prefixes = ["live", "app"]
        for prefix in prefixes:
            for base_url in self._candidate_urls(""):
                url = f"{base_url}/v3/config/paths/delete/{prefix}/{cam_id}"
                try:
                    with httpx.Client(timeout=2.0) as client:
                        res = client.delete(url)
                        if res.status_code in (200, 204):
                            return True
                except Exception:
                    pass
        return False


_mediamtx_service_instance: Optional[MediaMTXService] = None


def get_mediamtx_service() -> MediaMTXService:
    global _mediamtx_service_instance
    if _mediamtx_service_instance is None:
        _mediamtx_service_instance = MediaMTXService()
    return _mediamtx_service_instance
