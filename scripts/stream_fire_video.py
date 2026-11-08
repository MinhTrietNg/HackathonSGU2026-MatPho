"""
Stream Fire Test Video to MediaMTX / EAG.
Feeds a real CCTV video (electric bike explosion in Nhat Tan) into MediaMTX RTSP
to test the end-to-end AI detection & EAG 2-phase alert relay.
"""

from __future__ import annotations

import os
import sys
import time
import datetime
import argparse
import logging
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("stream_fire_video")


def run_streamer(
    video_path: str,
    target_url: str = "rtsp://localhost:8554/source/cam_01",
    cam_id: str = "cam_01",
    cam_name: str = "Xe Dap Dien No (Nhat Tan)",
    target_fps: int = 25,
    enable_osd: bool = True,
    auto_loop: bool = True,
) -> None:
    p = Path(video_path).resolve()
    if not p.is_file():
        logger.error("File video khong ton tai: %s", p)
        sys.exit(1)

    logger.info("======================================================================")
    logger.info("  KHOI DONG PHAT VIDEO CHAY THUC TE VAO KHOI EAG")
    logger.info("======================================================================")
    logger.info("  * Video nguon : %s (%s MB)", p.name, round(p.stat().st_size / (1024 * 1024), 2))
    logger.info("  * RTSP Target : %s", target_url)
    logger.info("  * Camera ID   : %s (%s)", cam_id, cam_name)
    logger.info("  * Toc do FPS  : %d FPS (Auto Loop: %s)", target_fps, auto_loop)
    logger.info("  * HLS Playback: http://localhost:8888/live/%s/index.m3u8", cam_id)
    logger.info("----------------------------------------------------------------------")
    logger.info("Nhan Ctrl+C de dung stream bat ky luc nao.")
    logger.info("======================================================================")

    clock_tb = Fraction(1, 90_000)
    frame_interval = 1.0 / target_fps

    while True:
        cap = cv2.VideoCapture(str(p))
        if not cap.isOpened():
            logger.error("Khong the mo video: %s. Thu lai sau 3s...", p)
            time.sleep(3.0)
            continue

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        v_fps = cap.get(cv2.CAP_PROP_FPS) or target_fps
        duration_s = total_frames / v_fps if v_fps > 0 else 0.0
        v_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
        v_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720

        logger.info("Thong so video: %dx%d, %d frames (~%.1f giay, ban goc %.1f FPS)", v_width, v_height, total_frames, duration_s, v_fps)

        try:
            output = av.open(
                target_url,
                mode="w",
                format="rtsp",
                options={"rtsp_transport": "tcp"},
            )
            stream = output.add_stream("libx264", rate=target_fps)
            stream.width = v_width
            stream.height = v_height
            stream.pix_fmt = "yuv420p"
            stream.codec_context.time_base = clock_tb
            stream.options = {
                "preset": "ultrafast",
                "tune": "zerolatency",
                "crf": "23",
                "g": str(target_fps),
            }

            logger.info("[OK] Da ket noi thanh cong voi MediaMTX: %s", target_url)

            frame_idx = 0
            t_mono = time.monotonic()
            last_log_t = t_mono

            while True:
                target_mono = t_mono + (frame_idx * frame_interval)
                sleep_s = target_mono - time.monotonic()
                if sleep_s > 0:
                    time.sleep(sleep_s)

                ret, frame = cap.read()
                if not ret or frame is None:
                    if auto_loop:
                        logger.info("Video het, tu dong lap lai tu dau...")
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            break
                    else:
                        logger.info("Phat het video, ket thuc.")
                        break

                if frame.shape[1] != v_width or frame.shape[0] != v_height:
                    frame = cv2.resize(frame, (v_width, v_height), interpolation=cv2.INTER_LINEAR)

                # Optional OSD overlay
                if enable_osd:
                    cur_s = int((frame_idx % total_frames) / target_fps)
                    dur_s = int(duration_s)
                    cur_m, cur_rem = divmod(cur_s, 60)
                    dur_m, dur_rem = divmod(dur_s, 60)
                    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # Banner
                    cv2.rectangle(frame, (15, 15), (v_width - 15, 60), (20, 22, 28), -1)
                    cv2.rectangle(frame, (15, 15), (v_width - 15, 60), (70, 75, 88), 1)
                    # Blinking dot
                    dot_c = (0, 0, 240) if (frame_idx // target_fps) % 2 == 0 else (50, 50, 70)
                    cv2.circle(frame, (35, 38), 8, dot_c, -1)
                    cv2.putText(frame, "CCTV TEST", (50, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 2)
                    cv2.putText(frame, f"{cam_name} [{cam_id}]", (180, 44), cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 220, 255), 2)
                    cv2.putText(frame, f"TC {cur_m:02d}:{cur_rem:02d}/{dur_m:02d}:{dur_rem:02d}", (v_width - 360, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 128), 2)
                    cv2.putText(frame, now_str, (v_width - 200, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1)

                av_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
                pts_90k = round(frame_idx * frame_interval * 90_000)
                av_frame.pts = pts_90k
                av_frame.time_base = clock_tb
                av_frame.pict_type = av.video.frame.PictureType.NONE

                for packet in stream.encode(av_frame):
                    output.mux(packet)

                frame_idx += 1
                now_m = time.monotonic()
                if now_m - last_log_t >= 3.0:
                    last_log_t = now_m
                    cur_s = int((frame_idx % total_frames) / target_fps)
                    cur_m, cur_rem = divmod(cur_s, 60)
                    dur_m, dur_rem = divmod(int(duration_s), 60)
                    logger.info("[STREAMING] Frame %d | Timecode %02d:%02d / %02d:%02d | RTSP: %s", frame_idx, cur_m, cur_rem, dur_m, dur_rem, target_url)

        except Exception as exc:
            logger.warning("RTSP Mux loi (%s). Thu ket noi lai sau 2s...", exc)
            time.sleep(2.0)
        finally:
            cap.release()
            try:
                output.close()
            except Exception:
                pass


def main() -> None:
    default_video = r"C:\Users\P.C.Tai\Downloads\vietnamnet_2423486_xe_dap_dien_no_truoc_cua_nha_nhat_tan.mp4"

    parser = argparse.ArgumentParser(description="Push video to MediaMTX RTSP for EAG AI Testing.")
    parser.add_argument("--video", default=default_video, help="Path to MP4 video file")
    parser.add_argument("--target", default="rtsp://localhost:8554/source/cam_01", help="Target RTSP URL")
    parser.add_argument("--cam-id", default="cam_01", help="Camera ID")
    parser.add_argument("--cam-name", default="Xe Dap Dien No (Nhat Tan)", help="Camera Name")
    parser.add_argument("--fps", type=int, default=25, help="Streaming FPS")
    parser.add_argument("--no-loop", action="store_true", help="Do not loop video")
    parser.add_argument("--no-osd", action="store_true", help="Disable OSD overlay")
    args = parser.parse_args()

    try:
        run_streamer(
            video_path=args.video,
            target_url=args.target,
            cam_id=args.cam_id,
            cam_name=args.cam_name,
            target_fps=args.fps,
            enable_osd=not args.no_osd,
            auto_loop=not args.no_loop,
        )
    except KeyboardInterrupt:
        logger.info("\nDa dung stream boi nguoi dung (Ctrl+C).")


if __name__ == "__main__":
    main()
