"""
Sample Video Generator for RTSP Virtual Camera Studio.
Generates synthetic MP4 benchmark videos (Normal Street & Fire Incident)
so testing and AI detection can be verified immediately without physical cameras.
"""

from __future__ import annotations

import os
import math
import logging
from fractions import Fraction
from pathlib import Path
import numpy as np
import cv2
import av

logger = logging.getLogger("rtsp_studio.sample_generator")


def generate_sample_video(
    output_path: str,
    duration_s: int = 15,
    fps: int = 25,
    width: int = 1280,
    height: int = 720,
    has_fire: bool = False,
) -> str:
    """
    Generate an animated H.264 MP4 video.
    If has_fire=True, starts peaceful then spawns an expanding fire & smoke pattern at second 5.
    """
    p = Path(output_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    output = av.open(str(p), mode="w", format="mp4")
    stream = output.add_stream("libx264", rate=fps)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    stream.options = {"preset": "ultrafast", "crf": "23"}

    total_frames = int(duration_s * fps)
    clock_tb = Fraction(1, fps)
    stream.codec_context.time_base = clock_tb

    for frame_idx in range(total_frames):
        current_time_s = frame_idx / fps
        img = np.zeros((height, width, 3), dtype=np.uint8)

        # 1. Dark Cityscape / Street Background
        img[:, :] = (30, 32, 38)
        # Grid lines representing road lanes
        for y in range(0, height, 100):
            cv2.line(img, (0, y), (width, y), (45, 48, 56), 1)
        for x in range(0, width, 120):
            cv2.line(img, (x, 0), (x, height), (45, 48, 56), 1)

        # Road surface
        road_top = int(height * 0.55)
        cv2.rectangle(img, (0, road_top), (width, height), (22, 24, 28), -1)
        cv2.line(img, (0, road_top), (width, road_top), (100, 105, 115), 2)

        # Moving simulated vehicle (box sliding horizontally)
        car_x = int((frame_idx * 15) % (width + 200)) - 100
        car_y = int(height * 0.7)
        cv2.rectangle(img, (car_x, car_y), (car_x + 90, car_y + 40), (180, 100, 50), -1)
        cv2.circle(img, (car_x + 20, car_y + 40), 8, (15, 15, 15), -1)
        cv2.circle(img, (car_x + 70, car_y + 40), 8, (15, 15, 15), -1)

        # 2. Fire Simulation (if has_fire and current_time_s >= 5.0)
        if has_fire and current_time_s >= 4.0:
            fire_progress = min(1.0, (current_time_s - 4.0) / 4.0)  # Grows over 4s
            fx = int(width * 0.65)
            fy = int(height * 0.52)
            fire_radius = int(25 + 75 * fire_progress)

            # Pulsing flame layers (Orange/Yellow/Red BGR)
            pulse = math.sin(frame_idx * 0.8) * 6
            cv2.circle(img, (fx, fy), int(fire_radius + 15 + pulse), (0, 70, 200), -1)   # Red-Orange outer
            cv2.circle(img, (fx, fy - 10), int(fire_radius + pulse), (0, 140, 255), -1)  # Orange middle
            cv2.circle(img, (fx, fy - 15), int(fire_radius * 0.55), (20, 220, 255), -1) # Yellow core

            # Smoke rising
            smoke_y = int(fy - 50 - ((frame_idx * 4) % 180))
            cv2.circle(img, (fx + 10, smoke_y), 35, (90, 95, 100), -1)

            # Warning banner
            cv2.putText(
                img,
                "[SIMULATION: FIRE & SMOKE DETECTED]",
                (int(width * 0.3), 80),
                cv2.FONT_HERSHEY_DUPLEX,
                0.9,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        # 3. Timecode OSD inside video content
        mins = int(current_time_s // 60)
        secs = int(current_time_s % 60)
        tc_text = f"SCENE TC: {mins:02d}:{secs:02d} / {int(duration_s//60):02d}:{int(duration_s%60):02d}"
        cv2.putText(img, tc_text, (50, height - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)

        # Encode frame
        frame = av.VideoFrame.from_ndarray(img, format="bgr24")
        frame.pts = frame_idx
        for packet in stream.encode(frame):
            output.mux(packet)

    for packet in stream.encode():
        output.mux(packet)

    output.close()
    logger.info("Generated sample video: %s (duration=%ds, fire=%s)", p, duration_s, has_fire)
    return str(p)


def ensure_default_sample_videos(target_dir: str | Path) -> dict[str, str]:
    """Ensure two default sample videos exist: street_normal.mp4 and street_fire.mp4."""
    d = Path(target_dir).resolve()
    d.mkdir(parents=True, exist_ok=True)

    normal_path = d / "street_normal.mp4"
    fire_path = d / "street_fire.mp4"

    if not normal_path.exists():
        generate_sample_video(str(normal_path), duration_s=12, has_fire=False)

    if not fire_path.exists():
        generate_sample_video(str(fire_path), duration_s=12, has_fire=True)

    return {
        "normal": str(normal_path),
        "fire": str(fire_path),
    }
