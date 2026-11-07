"""
Virtual RTSP Camera Worker.
Streams any local video file (MP4/MKV/AVI) to a standardized MediaMTX RTSP path indefinitely,
supporting real-time Seeking (Tua), Playback Speed adjustment, Pause, Hot-Swapping, and OSD.
"""

from __future__ import annotations

import os
import time
import datetime
import logging
import threading
from fractions import Fraction
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import cv2
import numpy as np
import av

logger = logging.getLogger("rtsp_studio.worker")


class VirtualCamWorker:
    def __init__(
        self,
        cam_id: str,
        video_path: str,
        target_rtsp_url: Optional[str] = None,
        cam_name: str = "",
        fps: int = 25,
        width: int = 1280,
        height: int = 720,
        enable_osd: bool = True,
        auto_loop: bool = True,
    ):
        self.cam_id = cam_id
        self.cam_name = cam_name or cam_id
        self.video_path = str(Path(video_path).resolve())
        self.target_rtsp_url = target_rtsp_url or f"rtsp://localhost:8554/source/{cam_id}"
        self.fps = fps
        self.width = width
        self.height = height
        self.enable_osd = enable_osd
        self.auto_loop = auto_loop

        # Control state (Thread-safe)
        self._lock = threading.Lock()
        self._is_running = False
        self._is_paused = False
        self._speed_multiplier = 1.0
        self._seek_requested_sec: Optional[float] = None
        self._pending_swap_path: Optional[str] = None
        self._stop_event = threading.Event()

        # Telemetry & Preview
        self._current_sec = 0.0
        self._duration_sec = 0.0
        self._total_frames = 0
        self._frames_sent = 0
        self._current_preview_bgr: Optional[np.ndarray] = None
        self._is_rtsp_connected = False
        self._last_error = ""

        # Thread handle
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._is_paused

    @property
    def speed(self) -> float:
        with self._lock:
            return self._speed_multiplier

    def start(self) -> None:
        """Start the background RTSP streaming thread."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"Worker-{self.cam_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("[cam_id=%s] Virtual Camera started for %s -> %s", self.cam_id, self.video_path, self.target_rtsp_url)

    def stop(self, timeout_s: float = 3.0) -> None:
        """Gracefully stop streaming."""
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout_s)
        logger.info("[cam_id=%s] Virtual Camera stopped.", self.cam_id)

    def pause(self) -> None:
        """Pause playback without dropping the RTSP stream (freezes frame)."""
        with self._lock:
            self._is_paused = True

    def resume(self) -> None:
        """Resume active playback."""
        with self._lock:
            self._is_paused = False

    def toggle_pause(self) -> bool:
        """Toggle between Pause and Play."""
        with self._lock:
            self._is_paused = not self._is_paused
            return self._is_paused

    def set_speed(self, multiplier: float) -> None:
        """Set playback speed (e.g. 0.25, 0.5, 1.0, 2.0, 4.0)."""
        with self._lock:
            self._speed_multiplier = max(0.1, min(16.0, float(multiplier)))

    def seek_to_second(self, target_sec: float) -> None:
        """Seek video playback to a specific timestamp in seconds."""
        with self._lock:
            self._seek_requested_sec = max(0.0, float(target_sec))

    def seek_to_ratio(self, ratio: float) -> None:
        """Seek video playback using a 0.0 - 1.0 slider ratio."""
        with self._lock:
            if self._duration_sec > 0:
                self._seek_requested_sec = max(0.0, min(self._duration_sec, ratio * self._duration_sec))

    def swap_video(self, new_video_path: str) -> None:
        """Hot-swap the active video file without disconnecting RTSP."""
        p = Path(new_video_path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Video file not found: {new_video_path}")
        with self._lock:
            self._pending_swap_path = str(p)

    def toggle_osd(self, enabled: Optional[bool] = None) -> bool:
        with self._lock:
            if enabled is not None:
                self.enable_osd = enabled
            else:
                self.enable_osd = not self.enable_osd
            return self.enable_osd

    def get_state(self) -> Dict[str, Any]:
        """Return a real-time status snapshot for the GUI."""
        with self._lock:
            ratio = 0.0
            if self._duration_sec > 0:
                ratio = min(1.0, max(0.0, self._current_sec / self._duration_sec))

            return {
                "cam_id": self.cam_id,
                "cam_name": self.cam_name,
                "video_path": self.video_path,
                "video_name": os.path.basename(self.video_path),
                "target_rtsp_url": self.target_rtsp_url,
                "is_running": self._is_running,
                "is_paused": self._is_paused,
                "speed": self._speed_multiplier,
                "current_sec": self._current_sec,
                "duration_sec": self._duration_sec,
                "progress_ratio": ratio,
                "fps": self.fps,
                "frames_sent": self._frames_sent,
                "is_rtsp_connected": self._is_rtsp_connected,
                "enable_osd": self.enable_osd,
                "last_error": self._last_error,
            }

    def get_preview_thumbnail(self, max_w: int = 320, max_h: int = 180) -> Optional[np.ndarray]:
        """Return downscaled BGR image for GUI preview."""
        with self._lock:
            if self._current_preview_bgr is None:
                return None
            img = self._current_preview_bgr
        try:
            h, w = img.shape[:2]
            scale = min(max_w / w, max_h / h)
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            return cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        except Exception:
            return None

    def _open_video_capture(self, path: str) -> Tuple[Optional[cv2.VideoCapture], int, float, float]:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return None, 0, 0.0, 0.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        v_fps = cap.get(cv2.CAP_PROP_FPS) or self.fps
        duration_s = total_frames / v_fps if v_fps > 0 else 0.0
        return cap, total_frames, v_fps, duration_s

    def _draw_osd(self, img: np.ndarray, current_sec: float, duration_sec: float, speed: float, is_paused: bool) -> None:
        """Draw surveillance OSD over the frame."""
        h, w = img.shape[:2]
        now = datetime.datetime.now()

        # Top banner overlay
        cv2.rectangle(img, (15, 15), (w - 15, 60), (20, 22, 28), -1)
        cv2.rectangle(img, (15, 15), (w - 15, 60), (70, 75, 88), 1)

        # Blinking REC dot
        blink = (int(time.time() * 2) % 2) == 0
        dot_color = (0, 0, 240) if blink else (50, 50, 70)
        cv2.circle(img, (35, 38), 8, dot_color, -1)
        cv2.putText(img, "REC", (50, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 2)

        # Cam Name / ID
        title = f"{self.cam_name} [{self.cam_id}]"
        cv2.putText(img, title, (110, 44), cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 220, 255), 2)

        # Status badge
        badge = "PAUSED" if is_paused else f"PLAY {speed:.2f}x"
        badge_color = (0, 165, 255) if is_paused else (0, 255, 128)
        cv2.putText(img, f"[{badge}]", (w - 380, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.6, badge_color, 2)

        # Real-time wall clock
        clock_str = now.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(img, clock_str, (w - 240, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1)

        # Bottom seekbar / timecode
        cur_min, cur_sec = int(current_sec // 60), int(current_sec % 60)
        dur_min, dur_sec = int(duration_sec // 60), int(duration_sec % 60)
        tc_text = f"TC: {cur_min:02d}:{cur_sec:02d} / {dur_min:02d}:{dur_sec:02d}"
        cv2.putText(img, tc_text, (25, h - 25), cv2.FONT_HERSHEY_DUPLEX, 0.6, (240, 240, 240), 1)

    def _run_loop(self) -> None:
        """Main worker execution loop."""
        cap, total_frames, v_fps, duration_s = self._open_video_capture(self.video_path)
        if not cap:
            self._last_error = f"Cannot open video {self.video_path}"
            logger.error("[cam_id=%s] %s", self.cam_id, self._last_error)
            self._is_running = False
            return

        with self._lock:
            self._total_frames = total_frames
            self._duration_sec = duration_s

        frame_interval_s = 1.0 / self.fps
        last_frame_bgr: Optional[np.ndarray] = None
        current_frame_pos = 0.0

        # RTSP Publisher Handle
        output_container: Optional[av.container.OutputContainer] = None
        output_stream = None
        clock_tb = Fraction(1, 90_000)
        rtsp_connect_retry_at = 0.0

        pts_counter = 0

        try:
            while not self._stop_event.is_set():
                loop_start = time.monotonic()

                # 1. Handle Hot-Swap Video Request
                with self._lock:
                    pending_swap = self._pending_swap_path
                    self._pending_swap_path = None
                    seek_req = self._seek_requested_sec
                    self._seek_requested_sec = None
                    paused = self._is_paused
                    speed = self._speed_multiplier
                    osd_enabled = self.enable_osd

                if pending_swap:
                    new_cap, n_frames, n_fps, n_dur = self._open_video_capture(pending_swap)
                    if new_cap:
                        cap.release()
                        cap = new_cap
                        self.video_path = pending_swap
                        with self._lock:
                            self._total_frames = n_frames
                            self._duration_sec = n_dur
                        current_frame_pos = 0.0
                        total_frames = n_frames
                        duration_s = n_dur
                        v_fps = n_fps
                        logger.info("[cam_id=%s] Hot-swapped to new video: %s", self.cam_id, pending_swap)

                # 2. Handle Seek Request
                if seek_req is not None and cap:
                    target_frame = int(seek_req * v_fps)
                    target_frame = max(0, min(total_frames - 1, target_frame))
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                    current_frame_pos = float(target_frame)
                    logger.debug("[cam_id=%s] Seeked to %.1fs (frame %d)", self.cam_id, seek_req, target_frame)

                # 3. Read Next Frame
                if not paused:
                    # Advance according to speed multiplier
                    ret, frame = cap.read()
                    if not ret:
                        if self.auto_loop:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            current_frame_pos = 0.0
                            ret, frame = cap.read()
                        else:
                            frame = last_frame_bgr

                    if ret and frame is not None:
                        # Resize to uniform width/height if needed
                        if frame.shape[1] != self.width or frame.shape[0] != self.height:
                            frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
                        last_frame_bgr = frame.copy()
                        current_frame_pos += speed
                        if speed > 1.0 and current_frame_pos < total_frames:
                            # Skip forward frames proportionally for speed > 1.0
                            cap.set(cv2.CAP_PROP_POS_FRAMES, int(current_frame_pos))
                else:
                    # Paused: keep using the last frame
                    frame = last_frame_bgr

                if frame is None:
                    # Fallback empty slate if no frame yet
                    frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                    cv2.putText(frame, "NO VIDEO FRAME", (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                    last_frame_bgr = frame

                # 4. Render OSD if enabled
                working_frame = frame.copy()
                cur_sec = current_frame_pos / v_fps if v_fps > 0 else 0.0
                if osd_enabled:
                    self._draw_osd(working_frame, cur_sec, duration_s, speed, paused)

                # Update live preview buffer and telemetry
                with self._lock:
                    self._current_sec = cur_sec
                    self._current_preview_bgr = working_frame

                # 5. Connect / Push to RTSP Target
                now_m = time.monotonic()
                if output_container is None and now_m >= rtsp_connect_retry_at:
                    try:
                        output_container = av.open(
                            self.target_rtsp_url,
                            mode="w",
                            format="rtsp",
                            options={"rtsp_transport": "tcp"},
                        )
                        output_stream = output_container.add_stream("libx264", rate=self.fps)
                        output_stream.width = self.width
                        output_stream.height = self.height
                        output_stream.pix_fmt = "yuv420p"
                        output_stream.codec_context.time_base = clock_tb
                        output_stream.options = {
                            "preset": "ultrafast",
                            "tune": "zerolatency",
                            "crf": "23",
                            "g": str(self.fps),  # 1s keyframe interval
                        }
                        self._is_rtsp_connected = True
                        self._last_error = ""
                        logger.info("[cam_id=%s] Connected to RTSP stream %s", self.cam_id, self.target_rtsp_url)
                    except Exception as exc:
                        self._is_rtsp_connected = False
                        self._last_error = f"RTSP connection failed: {exc}"
                        rtsp_connect_retry_at = now_m + 3.0  # Retry every 3s
                        output_container = None
                        output_stream = None

                if output_container and output_stream:
                    try:
                        av_frame = av.VideoFrame.from_ndarray(working_frame, format="bgr24")
                        pts_step = int(90_000 / self.fps)
                        av_frame.pts = pts_counter * pts_step
                        pts_counter += 1

                        for packet in output_stream.encode(av_frame):
                            output_container.mux(packet)
                        self._frames_sent += 1
                    except Exception as exc:
                        logger.warning("[cam_id=%s] RTSP mux error: %s -> reconnecting", self.cam_id, exc)
                        try:
                            output_container.close()
                        except Exception:
                            pass
                        output_container = None
                        output_stream = None
                        self._is_rtsp_connected = False
                        rtsp_connect_retry_at = now_m + 2.0

                # 6. Pacing sleep to maintain accurate target FPS
                elapsed = time.monotonic() - loop_start
                sleep_s = frame_interval_s - elapsed
                if sleep_s > 0:
                    time.sleep(sleep_s)

        finally:
            if cap:
                cap.release()
            if output_container:
                try:
                    for packet in output_stream.encode():
                        output_container.mux(packet)
                    output_container.close()
                except Exception:
                    pass
            self._is_running = False
            self._is_rtsp_connected = False
            logger.info("[cam_id=%s] Worker loop exited gracefully.", self.cam_id)
