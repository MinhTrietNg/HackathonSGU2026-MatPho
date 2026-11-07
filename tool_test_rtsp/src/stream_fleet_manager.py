"""
StreamFleetManager: Central coordinator for a fleet of virtual RTSP cameras.
Manages multiple VirtualCamWorkers, batch controls (Start/Stop/Pause/Speed),
JSON presets, and Edge Backend synchronization.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tool_test_rtsp.src.virtual_cam_worker import VirtualCamWorker

logger = logging.getLogger("stream-fleet-manager")


class StreamFleetManager:
    """Manages a fleet of virtual RTSP camera workers."""

    def __init__(
        self,
        mediamtx_host: str = "127.0.0.1",
        mediamtx_port: int = 8554,
    ) -> None:
        self.mediamtx_host = mediamtx_host
        self.mediamtx_port = mediamtx_port
        self._workers: Dict[str, VirtualCamWorker] = {}
        self._lock = threading.Lock()

    def generate_next_cam_id(self) -> str:
        """Generate a non-colliding camera ID such as cam_01, cam_02."""
        with self._lock:
            existing_ids = set(self._workers.keys())
            idx = 1
            while True:
                candidate = f"cam_{idx:02d}"
                if candidate not in existing_ids:
                    return candidate
                idx += 1

    def add_camera(
        self,
        video_path: str,
        cam_id: Optional[str] = None,
        cam_name: Optional[str] = None,
        fps: int = 25,
        width: int = 1280,
        height: int = 720,
        auto_loop: bool = True,
        auto_start: bool = False,
    ) -> VirtualCamWorker:
        """Add a camera stream from a local video file."""
        if not cam_id:
            cam_id = self.generate_next_cam_id()

        if not cam_name:
            cam_name = f"Camera {cam_id.upper()}"

        target_rtsp_url = f"rtsp://{self.mediamtx_host}:{self.mediamtx_port}/source/{cam_id}"

        with self._lock:
            if cam_id in self._workers:
                # Stop existing before replacing
                self._workers[cam_id].stop()

            worker = VirtualCamWorker(
                cam_id=cam_id,
                cam_name=cam_name,
                video_path=video_path,
                target_rtsp_url=target_rtsp_url,
                fps=fps,
                width=width,
                height=height,
                auto_loop=auto_loop,
            )
            self._workers[cam_id] = worker

        if auto_start:
            worker.start()

        return worker

    def remove_camera(self, cam_id: str) -> bool:
        """Stop and remove a camera from the fleet."""
        with self._lock:
            worker = self._workers.pop(cam_id, None)
        if worker:
            worker.stop()
            return True
        return False

    def clear(self) -> None:
        """Stop and remove all cameras."""
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for w in workers:
            w.stop()

    def get_camera(self, cam_id: str) -> Optional[VirtualCamWorker]:
        """Retrieve a camera worker by ID."""
        with self._lock:
            return self._workers.get(cam_id)

    def list_cameras(self) -> List[VirtualCamWorker]:
        """List all camera workers in stable order."""
        with self._lock:
            return sorted(self._workers.values(), key=lambda w: w.cam_id)

    def add_from_directory(
        self,
        dir_path: str,
        extensions: Tuple[str, ...] = (".mp4", ".avi", ".mkv", ".mov"),
        auto_start: bool = False,
    ) -> List[str]:
        """
        Scan a directory for video files and create virtual cameras for each.
        Returns the list of created cam_ids.
        """
        p = Path(dir_path)
        if not p.is_dir():
            raise FileNotFoundError(f"Directory not found: {dir_path}")

        files = sorted(
            [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in extensions],
            key=lambda f: f.name.lower(),
        )

        created_ids: List[str] = []
        for file in files:
            cam_id = self.generate_next_cam_id()
            clean_name = file.stem.replace("_", " ").title()
            cam_name = f"Camera {cam_id} ({clean_name})"
            self.add_camera(
                video_path=str(file.resolve()),
                cam_id=cam_id,
                cam_name=cam_name,
                auto_start=auto_start,
            )
            created_ids.append(cam_id)

        return created_ids

    # --- Batch Controls ---

    def start_all(self) -> None:
        """Start all camera workers."""
        for worker in self.list_cameras():
            if not worker.is_running:
                worker.start()

    def stop_all(self) -> None:
        """Stop all camera workers."""
        for worker in self.list_cameras():
            if worker.is_running:
                worker.stop()

    def pause_all(self) -> None:
        """Pause all running cameras."""
        for worker in self.list_cameras():
            worker.pause()

    def resume_all(self) -> None:
        """Resume all paused cameras."""
        for worker in self.list_cameras():
            worker.resume()

    def set_speed_all(self, speed: float) -> None:
        """Set playback speed multiplier for all cameras."""
        for worker in self.list_cameras():
            worker.set_speed(speed)

    def seek_all_seconds(self, seconds: float) -> None:
        """Seek all cameras to a specific second."""
        for worker in self.list_cameras():
            worker.seek_to_second(seconds)

    def seek_all_ratio(self, ratio: float) -> None:
        """Seek all cameras to a ratio between 0.0 and 1.0."""
        for worker in self.list_cameras():
            worker.seek_to_ratio(ratio)

    def get_fleet_status(self) -> List[Dict[str, Any]]:
        """Return snapshot status dict for each camera in the fleet."""
        return [w.get_state() for w in self.list_cameras()]

    # --- Presets (Save / Load) ---

    def save_preset(self, file_path: str) -> None:
        """Export current fleet configuration to a JSON file."""
        cams_data = []
        for w in self.list_cameras():
            cams_data.append(
                {
                    "cam_id": w.cam_id,
                    "cam_name": w.cam_name,
                    "video_path": w.video_path,
                    "fps": w.fps,
                    "width": w.width,
                    "height": w.height,
                    "speed": w.speed,
                    "auto_loop": w.auto_loop,
                }
            )

        payload = {
            "version": "1.0",
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "mediamtx_host": self.mediamtx_host,
            "mediamtx_port": self.mediamtx_port,
            "cameras": cams_data,
        }

        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def load_preset(self, file_path: str, auto_start: bool = False) -> List[str]:
        """Load fleet configuration from a JSON preset file."""
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Preset file not found: {file_path}")

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.clear()
        self.mediamtx_host = data.get("mediamtx_host", self.mediamtx_host)
        self.mediamtx_port = data.get("mediamtx_port", self.mediamtx_port)

        loaded_ids: List[str] = []
        for cam_data in data.get("cameras", []):
            cid = cam_data["cam_id"]
            w = self.add_camera(
                video_path=cam_data.get("video_path", ""),
                cam_id=cid,
                cam_name=cam_data.get("cam_name"),
                fps=cam_data.get("fps", 25),
                width=cam_data.get("width", 1280),
                height=cam_data.get("height", 720),
                auto_loop=cam_data.get("auto_loop", cam_data.get("loop", True)),
                auto_start=auto_start,
            )
            w.set_speed(cam_data.get("speed", 1.0))
            loaded_ids.append(cid)

        return loaded_ids

    # --- Edge Backend Synchronization ---

    def sync_camera_to_edge(
        self,
        cam_id: str,
        edge_api_url: str = "http://localhost:8090",
        edge_mediamtx_host: str = "mediamtx",
        internal_secret: str = "secure_internal_key_for_ai_and_worker_communication",
        timeout_s: float = 4.0,
    ) -> Dict[str, Any]:
        """
        Synchronize a single camera to Edge Backend SQLite & Live Decoder.
        The Edge container communicates with MediaMTX via docker network hostname `edge_mediamtx_host`.
        """
        worker = self.get_camera(cam_id)
        if not worker:
            raise KeyError(f"Camera ID '{cam_id}' not found in fleet.")

        # From inside Docker Edge Backend, MediaMTX is reached at rtsp://mediamtx:8554/source/{cam_id}
        docker_rtsp_url = f"rtsp://{edge_mediamtx_host}:{self.mediamtx_port}/source/{cam_id}"

        payload = {
            "cam_id": worker.cam_id,
            "cam_name": worker.cam_name,
            "rtsp_url": docker_rtsp_url,
            "is_active": True,
        }

        endpoint = f"{edge_api_url.rstrip('/')}/api/v1/edge/cameras"
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-internal-secret": internal_secret,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                status_code = resp.getcode()
                body = json.loads(resp.read().decode("utf-8"))
                return {
                    "cam_id": cam_id,
                    "status_code": status_code,
                    "success": True,
                    "response": body,
                    "registered_rtsp": docker_rtsp_url,
                }
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")
            logger.warning("HTTP error syncing camera %s: %d %s", cam_id, e.code, err_msg)
            return {
                "cam_id": cam_id,
                "status_code": e.code,
                "success": False,
                "error": err_msg,
            }
        except Exception as exc:
            logger.warning("Connection error syncing camera %s: %s", cam_id, exc)
            return {
                "cam_id": cam_id,
                "status_code": 0,
                "success": False,
                "error": str(exc),
            }

    def sync_all_to_edge(
        self,
        edge_api_url: str = "http://localhost:8090",
        edge_mediamtx_host: str = "mediamtx",
        internal_secret: str = "secure_internal_key_for_ai_and_worker_communication",
    ) -> Dict[str, Any]:
        """Synchronize all cameras in fleet to Edge Backend."""
        results = {}
        for cam in self.list_cameras():
            res = self.sync_camera_to_edge(
                cam_id=cam.cam_id,
                edge_api_url=edge_api_url,
                edge_mediamtx_host=edge_mediamtx_host,
                internal_secret=internal_secret,
            )
            results[cam.cam_id] = res

        successful_count = sum(1 for r in results.values() if r.get("success"))
        return {
            "total": len(results),
            "synced": successful_count,
            "results": results,
        }
