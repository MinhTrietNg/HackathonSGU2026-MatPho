"""Run the detector on a video and write an annotated copy (boxes on every frame).

Unlike ``python -m firewatch run`` (one heartbeat per second, voting, alerts),
this draws raw detections on *every* frame, which is what you want to eyeball
a model on a new clip. Also saves the top-N frames by confidence as JPEGs and
a JSON summary next to the video.

Usage::

    python tools/annotate_video.py --source clip.mp4 [--out result/clip_v2.mp4]
                                   [--weights models/firewatch-v2.0.pt] [--every 1]
                                   [--conf 0.25] [--top 3]
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from firewatch.annotate import draw_detections, write_jpeg  # noqa: E402
from firewatch.config import load_config  # noqa: E402
from firewatch.detector import Detector  # noqa: E402

log = logging.getLogger("annotate_video")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", required=True, help="video đầu vào")
    ap.add_argument("--out", default=None,
                    help="mp4 đầu ra (mặc định result/<tên>_<weights>.mp4)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--weights", default=None, help="ghi đè detector.weights")
    ap.add_argument("--every", type=int, default=1,
                    help="detect mỗi N khung, khung giữa dùng lại box")
    ap.add_argument("--conf", type=float, default=None, help="ghi đè conf_threshold")
    ap.add_argument("--top", type=int, default=3,
                    help="số khung conf cao nhất lưu .jpg")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    cfg = load_config(args.config)
    if args.weights:
        cfg.detector.weights = Path(args.weights)
    if args.conf is not None:
        cfg.detector.conf_threshold = args.conf
    cfg.detector.warmup = True
    det = Detector(cfg.detector, cfg)

    src = Path(args.source)
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        log.error("không mở được %s", src)
        return 2
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = Path(args.out) if args.out else (
        cfg.root / "result" / f"{src.stem[:40]}_{det.weights.stem}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    log.info("%s: %dx%d @ %.1f fps, %d khung; weights %s; detect mỗi %d khung",
             src.name, w, h, fps, n_total, det.weights.name, args.every)

    dets: list = []
    infer_ms: list[float] = []
    frames_with: dict[str, int] = {"fire": 0, "smoke": 0}
    max_conf: dict[str, float] = {"fire": 0.0, "smoke": 0.0}
    best: list[tuple[float, int, float]] = []   # (conf, idx, t)
    timeline: list[dict] = []
    idx, t_log = 0, time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / fps
        if idx % args.every == 0:
            res = det.detect(frame)
            dets = res.detections
            infer_ms.append(res.infer_ms)
            if dets:
                top = max(d.conf for d in dets)
                best.append((top, idx, t))
                for cls in frames_with:
                    cls_d = [d for d in dets if d.cls_name == cls]
                    if cls_d:
                        frames_with[cls] += 1
                        max_conf[cls] = max(max_conf[cls], max(d.conf for d in cls_d))
                timeline.append({"t": round(t, 2),
                                 "boxes": [d.to_dict() for d in dets]})
        counts = {c: sum(1 for d in dets if d.cls_name == c) for c in ("fire", "smoke")}
        banner = (f"{t:6.2f}s  fire {counts['fire']}  smoke {counts['smoke']}  "
                  f"| {det.weights.name} conf>={cfg.detector.conf_threshold}")
        writer.write(draw_detections(frame, dets, banner))
        idx += 1
        if time.time() - t_log > 10:
            log.info("  %d/%d khung, %.0f ms/khung", idx, n_total,
                     statistics.fmean(infer_ms) if infer_ms else 0)
            t_log = time.time()
    writer.release()
    cap.release()

    # Khung conf cao nhất -> jpg (đọc lại đúng khung để vẽ box của khung đó)
    best.sort(reverse=True)
    saved = []
    picked: list[int] = []
    for conf, fidx, t in best:
        if any(abs(fidx - p) < fps for p in picked):   # cách nhau >= 1 s
            continue
        picked.append(fidx)
        cap = cv2.VideoCapture(str(src))
        cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            continue
        d = det.detect(frame).detections
        p = out.with_name(f"{out.stem}_top{len(saved) + 1}_{t:05.1f}s.jpg")
        if write_jpeg(p, draw_detections(frame, d, f"{t:.2f}s  max conf {conf:.2f}")):
            saved.append(p.name)
        if len(saved) >= args.top:
            break

    n_det = max(len(infer_ms), 1)
    summary = {
        "source": str(src), "output": str(out), "weights": det.weights.name,
        "backend": cfg.detector.backend, "imgsz": cfg.detector.imgsz,
        "conf_threshold": cfg.detector.conf_threshold,
        "frames": idx, "fps": round(fps, 2), "duration_s": round(idx / fps, 1),
        "frames_detected": len(infer_ms),
        "frames_with_fire": frames_with["fire"],
        "frames_with_smoke": frames_with["smoke"],
        "pct_frames_with_fire": round(100 * frames_with["fire"] / n_det, 1),
        "pct_frames_with_smoke": round(100 * frames_with["smoke"] / n_det, 1),
        "max_conf": {k: round(v, 3) for k, v in max_conf.items()},
        "infer_ms_mean": round(statistics.fmean(infer_ms), 1) if infer_ms else 0,
        "top_frames": saved,
        "timeline": timeline,
    }
    out.with_suffix(".json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    brief = {k: v for k, v in summary.items() if k != "timeline"}
    log.info("xong: %s", json.dumps(brief, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
