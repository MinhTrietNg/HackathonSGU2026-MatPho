"""Mock IP Camera Generator for EdgeAI-MatPho.

Simulates a real CCTV camera by continuously publishing a live H.264 video stream
with a large high-visibility digital counter, real-time clock OSD, and fluid motion
scanner to MediaMTX RTSP.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import math
import time
from fractions import Fraction

import av
import cv2
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MOCK-CAM] %(message)s",
)
logger = logging.getLogger("mock_camera")


def run_mock_camera(
    target_url: str = "rtsp://localhost:8554/mock/cam_test",
    width: int = 1920,
    height: int = 1080,
    fps: int = 25,
    transport: str = "tcp",
) -> None:
    """Publish an animated counter CCTV feed to an RTSP server indefinitely."""
    logger.info("Starting Mock Counter Camera streaming to %s (%dx%d @ %dfps)", target_url, width, height, fps)

    clock_tb = Fraction(1, 90_000)

    while True:
        try:
            output = av.open(
                target_url,
                mode="w",
                format="rtsp",
                options={"rtsp_transport": transport},
            )
            stream = output.add_stream("libx264", rate=fps)
            stream.width = width
            stream.height = height
            stream.pix_fmt = "yuv420p"
            stream.codec_context.time_base = clock_tb
            stream.options = {
                "preset": "ultrafast",
                "tune": "zerolatency",
                "crf": "23",
                "g": str(fps),  # 1-second GOP for instant HLS cut
            }

            frame_interval = 1.0 / fps
            frame_idx = 0
            t_mono = time.monotonic()
            logger.info("Connected to MediaMTX! Live RTSP counter stream started.")

            while True:
                target_mono = t_mono + (frame_idx * frame_interval)
                sleep_s = target_mono - time.monotonic()
                if sleep_s > 0:
                    time.sleep(sleep_s)

                now = datetime.datetime.now()
                elapsed_s = int(frame_idx // fps)
                elapsed_hrs = elapsed_s // 3600
                elapsed_mins = (elapsed_s % 3600) // 60
                elapsed_secs = elapsed_s % 60

                # 1. Background: Dark Surveillance Slate
                img = np.zeros((height, width, 3), dtype=np.uint8)
                img[:, :] = (24, 26, 30)  # Dark charcoal BGR

                # Subtle grid lines
                for y in range(0, height, 120):
                    cv2.line(img, (0, y), (width, y), (35, 38, 44), 1)
                for x in range(0, width, 160):
                    cv2.line(img, (x, 0), (x, height), (35, 38, 44), 1)

                # 2. Outer Safe Frame
                cv2.rectangle(img, (40, 40), (width - 40, height - 40), (60, 65, 75), 2)
                # Corner crosshairs
                for (cx, cy) in [(40, 40), (width - 40, 40), (40, height - 40), (width - 40, height - 40)]:
                    cv2.circle(img, (cx, cy), 5, (0, 200, 255), -1)

                # 3. Top Header Bar
                cv2.rectangle(img, (40, 40), (width - 40, 110), (32, 35, 42), -1)
                cv2.line(img, (40, 110), (width - 40, 110), (70, 75, 88), 2)

                # Blinking REC Dot (1s ON, 1s OFF)
                if (frame_idx // fps) % 2 == 0:
                    cv2.circle(img, (75, 75), 10, (0, 0, 240), -1)
                else:
                    cv2.circle(img, (75, 75), 10, (60, 60, 80), -1)

                cv2.putText(img, "REC", (95, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220, 220, 220), 2, cv2.LINE_AA)
                cv2.putText(
                    img,
                    "MAT PHO - CCTV LIVE TEST STREAM",
                    (180, 83),
                    cv2.FONT_HERSHEY_DUPLEX,
                    0.9,
                    (0, 220, 255),
                    2,
                    cv2.LINE_AA,
                )

                # Real-time clock in top right
                clock_str = now.strftime("%Y-%m-%d  %H:%M:%S")
                cv2.putText(img, clock_str, (width - 440, 83), cv2.FONT_HERSHEY_DUPLEX, 0.85, (240, 240, 240), 2, cv2.LINE_AA)

                # 4. Center Main Box: Big Digital Counter Display
                center_box_w = 900
                center_box_h = 420
                cb_x1 = (width - center_box_w) // 2
                cb_y1 = (height - center_box_h) // 2 - 20
                cb_x2 = cb_x1 + center_box_w
                cb_y2 = cb_y1 + center_box_h

                cv2.rectangle(img, (cb_x1, cb_y1), (cb_x2, cb_y2), (18, 20, 24), -1)
                cv2.rectangle(img, (cb_x1, cb_y1), (cb_x2, cb_y2), (0, 180, 240), 2)

                # Big Main Counter (Đếm số tăng dần theo từng giây)
                counter_title = "COUNT (SECONDS)"
                cv2.putText(img, counter_title, (cb_x1 + 40, cb_y1 + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (140, 150, 165), 1, cv2.LINE_AA)

                count_num_str = f"{elapsed_s:06d}"
                cv2.putText(img, count_num_str, (cb_x1 + 40, cb_y1 + 175), cv2.FONT_HERSHEY_DUPLEX, 3.8, (0, 255, 120), 5, cv2.LINE_AA)

                # Sub-counters: Uptime Clock & Frame Number
                uptime_str = f"UPTIME: {elapsed_hrs:02d}:{elapsed_mins:02d}:{elapsed_secs:02d}"
                cv2.putText(img, uptime_str, (cb_x1 + 40, cb_y1 + 260), cv2.FONT_HERSHEY_DUPLEX, 1.2, (255, 220, 0), 2, cv2.LINE_AA)

                frame_str = f"FRAME:  #{frame_idx:07d}  ({fps} FPS)"
                cv2.putText(img, frame_str, (cb_x1 + 40, cb_y1 + 325), cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 200, 255), 2, cv2.LINE_AA)

                # Sub-second fraction badge
                sub_sec = int((frame_idx % fps) * (100 / fps))
                cv2.putText(img, f".{sub_sec:02d}s", (cb_x1 + 620, cb_y1 + 175), cv2.FONT_HERSHEY_DUPLEX, 1.8, (0, 200, 100), 2, cv2.LINE_AA)

                # 5. Fluid Motion Radar / Pulse Circle (mô phỏng chuyển động 25 fps)
                radar_cx = cb_x2 - 130
                radar_cy = cb_y1 + 270
                radar_r = 50
                cv2.circle(img, (radar_cx, radar_cy), radar_r, (50, 55, 65), 2)
                cv2.circle(img, (radar_cx, radar_cy), 3, (0, 255, 120), -1)
                # Rotating hand
                angle = (frame_idx % fps) * (2 * math.pi / fps)
                hand_x = int(radar_cx + (radar_r - 4) * math.cos(angle))
                hand_y = int(radar_cy + (radar_r - 4) * math.sin(angle))
                cv2.line(img, (radar_cx, radar_cy), (hand_x, hand_y), (0, 255, 120), 3, cv2.LINE_AA)

                # 6. Bottom Banner & Motion Progress Bar
                bar_y = height - 160
                cv2.rectangle(img, (100, bar_y), (width - 100, bar_y + 14), (40, 44, 52), -1)
                fill_ratio = (frame_idx % (fps * 2)) / (fps * 2)
                fill_w = int((width - 200) * fill_ratio)
                cv2.rectangle(img, (100, bar_y), (100 + fill_w, bar_y + 14), (0, 200, 255), -1)

                # Footer metadata
                footer_text = f"RESOLUTION: {width}x{height} | CODEC: H.264 ZERO-COPY | PIPELINE: ACTIVE"
                cv2.putText(img, footer_text, (100, height - 90), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (160, 170, 185), 2, cv2.LINE_AA)

                # Convert ndarray to PyAV VideoFrame
                frame = av.VideoFrame.from_ndarray(img, format="bgr24")
                pts_90k = round(frame_idx * frame_interval * 90_000)
                frame.pts = pts_90k
                frame.time_base = clock_tb
                frame.pict_type = av.video.frame.PictureType.NONE

                for packet in stream.encode(frame):
                    output.mux(packet)

                frame_idx += 1
                if frame_idx % (fps * 10) == 0:
                    logger.info("Mock camera active: %d frames (uptime %ds)", frame_idx, elapsed_s)

        except KeyboardInterrupt:
            logger.info("Stopping Mock Camera...")
            break
        except Exception as exc:
            logger.warning("Mock camera connection error: %s. Reconnecting in 3s...", exc)
            time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic RTSP Counter Camera Streamer")
    parser.add_argument("--url", default="rtsp://localhost:8554/mock/cam_test", help="Target RTSP URL to publish to")
    parser.add_argument("--width", type=int, default=1920, help="Video width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Video height (default: 1080)")
    parser.add_argument("--fps", type=int, default=25, help="Video FPS (default: 25)")
    parser.add_argument("--transport", default="tcp", choices=["tcp", "udp"], help="RTSP transport protocol")
    args = parser.parse_args()

    run_mock_camera(
        target_url=args.url,
        width=args.width,
        height=args.height,
        fps=args.fps,
        transport=args.transport,
    )


if __name__ == "__main__":
    main()
