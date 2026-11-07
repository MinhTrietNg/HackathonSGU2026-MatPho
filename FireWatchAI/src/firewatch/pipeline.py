"""Main loop that chains the tiers:

    source → heartbeat → detect → voting → VLM verify → alert

Every heartbeat is logged with both the video timestamp and wall-clock
time; frames with detections are saved as annotated JPEGs; each alert
becomes an event (JSON + keyframe) in ``events/``; a run summary is written.

Alert timing: an alert never waits more than ``vlm.grace_s`` for the VLM.
If the verdict is late the event goes out as ``UNVERIFIED`` and is patched
(same ``event_id``) when the verdict arrives.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import queue
import shutil
import statistics
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2

from .acks import MUTING_ACTIONS, Ack, AckStore
from .alerts import Event, EventStore
from .annotate import draw_detections, draw_tracks, write_jpeg
from .config import Config
from .detector import DetectResult, Detector, Detection
from .sources import Heartbeat, HeartbeatSampler, open_source
from .vlm import VerificationService, VerifyOutcome, VerifyRequest, build_verifier
from .voting import Severity, TrackEvent, VotingEngine, union

log = logging.getLogger(__name__)


@dataclass
class RunSummary:
    """Counters collected over one `run`."""

    source: str
    weights: str
    out_dir: str
    frames_read: int = 0
    heartbeats: int = 0
    heartbeats_with_det: int = 0
    detections_by_class: dict[str, int] = field(default_factory=dict)
    infer_ms: list[float] = field(default_factory=list)
    transitions: dict[str, int] = field(default_factory=dict)
    alerts: list[dict] = field(default_factory=list)
    wall_s: float = 0.0
    video_s: float = 0.0
    live_source_lost: bool = False
    """True when a webcam/RTSP source ended on its own (exit code 1)."""

    def to_dict(self) -> dict:
        ms = self.infer_ms or [0.0]
        return {
            "source": self.source,
            "weights": self.weights,
            "out_dir": self.out_dir,
            "frames_read": self.frames_read,
            "heartbeats": self.heartbeats,
            "heartbeats_with_det": self.heartbeats_with_det,
            "detections_by_class": self.detections_by_class,
            "transitions": self.transitions,
            "alerts": self.alerts,
            "n_alerts": len(self.alerts),
            "infer_ms_mean": round(statistics.fmean(ms), 1),
            "infer_ms_p95": round(sorted(ms)[int(0.95 * (len(ms) - 1))], 1),
            "infer_fps": round(1000 / statistics.fmean(ms), 2) if self.infer_ms else 0,
            "video_s": round(self.video_s, 2),
            "wall_s": round(self.wall_s, 2),
            "speed_x_realtime": round(self.video_s / self.wall_s, 2)
            if self.wall_s else 0,
            "live_source_lost": self.live_source_lost,
        }


class PipelineHealth:
    """Thread-safe liveness info shared with the API's ``/health``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_wall = time.time()
        self.last_heartbeat_wall: float | None = None
        self.heartbeats = 0
        self.alerts = 0
        self.finished = False
        self.error: str | None = None
        self.source_live = False
        self.heartbeat_interval_s = 1.0

    def beat(self) -> None:
        with self._lock:
            self.last_heartbeat_wall = time.time()
            self.heartbeats += 1

    def snapshot(self) -> dict:
        with self._lock:
            age = (time.time() - self.last_heartbeat_wall
                   if self.last_heartbeat_wall else None)
            stale_after = max(3 * self.heartbeat_interval_s, 10.0)
            if self.error:
                status = "dead"
            elif self.finished:
                status = "dead" if self.source_live else "finished"
            elif age is None:
                status = "starting"
            elif age > stale_after:
                status = "stale"
            else:
                status = "ok"
            return {"status": status, "heartbeats": self.heartbeats,
                    "alerts": self.alerts,
                    "last_heartbeat_age_s": round(age, 1) if age is not None else None,
                    "uptime_s": round(time.time() - self.started_wall, 1),
                    "source_live": self.source_live, "error": self.error}


@dataclass
class _PendingAlert:
    """An alert waiting for (or already sent ahead of) its VLM verdict."""

    future: Future
    deadline_wall: float
    kind: str
    track_id: int
    severity: Severity
    ts: float
    detections: list[Detection]
    image: object
    started_at: datetime
    event: Event | None = None
    record: dict | None = None


class Pipeline:
    """Run the FireWatch tiers over one video source."""

    def __init__(self, cfg: Config, source_spec: str, *, realtime: bool | None = None,
                 show: bool | None = None, max_heartbeats: int | None = None,
                 weights: str | None = None, store: EventStore | None = None,
                 strict: bool = False, health: PipelineHealth | None = None,
                 acks: AckStore | None = None):
        self.cfg = cfg
        self.source_spec = source_spec
        self.realtime = realtime
        self.show = cfg.output.show if show is None else show
        self.max_heartbeats = max_heartbeats
        self.store = store
        self.strict = strict
        self.health = health
        self.explicit_weights = weights is not None
        self._pending: list[_PendingAlert] = []
        self.acks = acks
        self._ack_queue: queue.SimpleQueue[Ack] = queue.SimpleQueue()
        self._event_track: dict[str, int] = {}
        """event_id -> track_id of events created by this run (for acks)."""
        if weights:
            cfg.detector.weights = Path(weights)

    def run(self) -> RunSummary:
        cfg = self.cfg
        if self.explicit_weights and not cfg.resolve(cfg.detector.weights).is_file():
            raise SystemExit(f"--weights không tồn tại: {cfg.detector.weights}")
        source = open_source(self.source_spec, cfg.source, realtime=self.realtime)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        runs_root = cfg.resolve(cfg.output.dir)
        _prune_runs(runs_root, cfg.output.keep_runs)
        out_dir = runs_root / f"{source.name}_{stamp}"
        out_dir.mkdir(parents=True, exist_ok=True)
        file_log = _attach_file_log(out_dir / "run.log",
                                    cfg.output.log_toi_da_mb, cfg.output.log_so_ban)
        if self.health:
            self.health.source_live = source.is_live
            self.health.heartbeat_interval_s = cfg.heartbeat.interval_s

        detector = Detector(cfg.detector, cfg)
        if detector.keep_ids is None and (self.strict or source.is_live
                                          or cfg.detector.require_classes):
            raise SystemExit(
                f"weights {detector.weights.name} không có class "
                f"{cfg.detector.classes}: từ chối chạy live/serve vì sẽ không bao "
                "giờ báo cháy. Đặt models/firewatch-v2.0.pt (xem models/README.md) "
                "hoặc --weights đúng file.")
        sampler = HeartbeatSampler(cfg.heartbeat.interval_s, cfg.heartbeat.ring_buffer)
        voting = VotingEngine(cfg.voting)
        store = self._event_store()
        verifier = VerificationService(cfg.vlm, build_verifier(cfg.vlm))
        summary = RunSummary(source=self.source_spec, weights=str(detector.weights),
                             out_dir=str(out_dir))
        log.info("bắt đầu: nguồn=%s T=%.2fs imgsz=%d conf=%.2f k=%d/%d lưu=%s",
                 self.source_spec, cfg.heartbeat.interval_s, cfg.detector.imgsz,
                 cfg.detector.conf_threshold, cfg.voting.k_enter, cfg.voting.window_m,
                 out_dir)
        t_wall0 = time.perf_counter()
        last_ts = 0.0
        stopped_by_us = False
        if self.acks is not None:
            self.acks.subscribe(self._ack_queue.put)
        try:
            with source:
                for frame in source:
                    summary.frames_read += 1
                    last_ts = frame.video_ts
                    hb = sampler.push(frame)
                    if hb is None:
                        continue
                    result = detector.detect(hb.frame.image)
                    self._apply_acks(voting)
                    events = voting.update(hb.seq, hb.frame.video_ts,
                                           result.detections, frame=hb.frame)
                    for ev in events:
                        self._on_track_event(ev, summary, verifier)
                    self._flush_pending(store, summary)
                    self._record(summary, hb, result, voting, out_dir)
                    if self.health:
                        self.health.beat()
                    if self.show and not self._show(hb, result, voting):
                        log.info("người dùng bấm q, dừng")
                        stopped_by_us = True
                        break
                    if (self.max_heartbeats is not None
                            and summary.heartbeats >= self.max_heartbeats):
                        log.info("đủ %d heartbeat, dừng", self.max_heartbeats)
                        stopped_by_us = True
                        break
        except BaseException as exc:
            if self.health:
                self.health.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if self.acks is not None:
                self.acks.unsubscribe(self._ack_queue.put)
            if self.show:
                cv2.destroyAllWindows()
            budget = cfg.vlm.timeout_s * (cfg.vlm.retries + 1) + 2
            left = verifier.drain(timeout_s=budget)
            if left:
                log.warning("%d xác minh VLM chưa xong sau %.0fs, giữ UNVERIFIED", left,
                            budget)
            self._flush_pending(store, summary, final=True)
            verifier.shutdown()
            if self.health:
                self.health.finished = True
            logging.getLogger().removeHandler(file_log)
            file_log.close()
        summary.wall_s = time.perf_counter() - t_wall0
        summary.video_s = last_ts
        summary.live_source_lost = source.is_live and not stopped_by_us
        if summary.live_source_lost:
            log.error("nguồn live %s đã kết thúc ngoài ý muốn", self.source_spec)
        (out_dir / "summary.json").write_text(
            json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")
        log.info("xong: %d heartbeat, %d alert, infer %.0f ms TB, x%.1f thời gian thực",
                 summary.heartbeats, len(summary.alerts),
                 summary.to_dict()["infer_ms_mean"],
                 summary.to_dict()["speed_x_realtime"])
        return summary

    def _event_store(self) -> EventStore:
        """The store given by ``serve`` (shared with the API), else a new one.

        Checked with ``is None``: an empty :class:`EventStore` is falsy (it
        has ``__len__``), so ``self.store or ...`` used to create a second
        store whenever the events folder was empty and live events never
        reached the API / WebSocket.
        """
        if self.store is not None:
            return self.store
        return EventStore(self.cfg.alerts, self.cfg.camera, self.cfg)

    # ------------------------------------------------------------------ tiers
    def _on_track_event(self, ev: TrackEvent, summary: RunSummary,
                        verifier: VerificationService) -> None:
        """Queue tier 4 (VLM) for a transition that deserves an alert."""
        if ev.kind != "NEW":
            summary.transitions[ev.kind] = summary.transitions.get(ev.kind, 0) + 1
        if not ev.alert:
            return
        vote = self._vote_for_alert(ev)
        if vote is None or vote.frame is None:
            return
        box = vote.detections[0].xyxy
        for d in vote.detections[1:]:
            box = union(box, d.xyxy)
        first = next(ev.track.iter_votes(), None)
        first_img = (first.frame.image if first is not None and first is not vote
                     and first.frame is not None else None)
        fut = verifier.submit(VerifyRequest(vote.frame.image, box,
                                            self.cfg.camera.context,
                                            ev.severity.value, ev.ts, first_img))
        self._pending.append(_PendingAlert(
            future=fut, deadline_wall=time.time() + self.cfg.vlm.grace_s,
            kind=ev.kind, track_id=ev.track.track_id, severity=ev.severity, ts=ev.ts,
            detections=list(vote.detections), image=vote.frame.image,
            started_at=datetime.fromtimestamp(vote.frame.wall_time).astimezone()))

    @staticmethod
    def _vote_for_alert(ev: TrackEvent):
        """Keyframe for the alert: for CRITICAL prefer the latest vote that
        actually contains a fire box, otherwise the highest-confidence vote."""
        track = ev.track
        if ev.severity is Severity.CRITICAL:
            for v in reversed(list(track.iter_votes())):
                if any(d.cls_name == "fire" for d in v.detections):
                    return v
        return track.best_vote or track.latest_vote

    def _flush_pending(self, store: EventStore, summary: RunSummary,
                       final: bool = False) -> None:
        """Tier 5: emit events whose verdict is in, or whose grace expired."""
        now = time.time()
        for p in list(self._pending):
            if p.future.done():
                outcome: VerifyOutcome = p.future.result()
                if p.event is None:
                    self._emit(store, summary, p, outcome)
                else:
                    store.update(p.event.event_id, verification=outcome.verification,
                                 vlm=outcome.result)
                    if p.record is not None:
                        p.record.update({"verification": outcome.verification,
                                         "vlm_latency_s": round(outcome.latency_s, 2),
                                         "vlm_attempts": outcome.attempts,
                                         "vlm_error": outcome.error, "updated": True})
                self._pending.remove(p)
            elif p.event is None and (final or now >= p.deadline_wall):
                late = VerifyOutcome("UNVERIFIED", None, now - (p.deadline_wall
                                                                - self.cfg.vlm.grace_s),
                                     0, "vlm chưa trả lời trong grace_s")
                self._emit(store, summary, p, late)
                if final:
                    self._pending.remove(p)

    def _emit(self, store: EventStore, summary: RunSummary, p: _PendingAlert,
              outcome: VerifyOutcome) -> None:
        p.event = store.create(severity=p.severity.value,
                               verification=outcome.verification, video_ts=p.ts,
                               detections=p.detections, image=p.image,
                               vlm=outcome.result, started_at=p.started_at)
        p.record = {"event_id": p.event.event_id, "kind": p.kind,
                    "severity": p.event.severity,
                    "verification": p.event.verification,
                    "video_ts_sec": p.event.video_ts_sec, "track_id": p.track_id,
                    "vlm_latency_s": round(outcome.latency_s, 2),
                    "vlm_attempts": outcome.attempts, "vlm_error": outcome.error,
                    "updated": False}
        summary.alerts.append(p.record)
        self._event_track[p.event.event_id] = p.track_id
        if self.health:
            self.health.alerts += 1

    def _apply_acks(self, voting: VotingEngine) -> None:
        """Apply operator acks on the pipeline thread (the engine is not
        thread-safe): confirm / dismiss mute STILL_BURNING of the track."""
        while True:
            try:
                ack = self._ack_queue.get_nowait()
            except queue.Empty:
                return
            track_id = self._event_track.get(ack.event_id)
            if ack.action not in MUTING_ACTIONS or track_id is None:
                continue
            if voting.mute(track_id):
                log.info("track#%d: người trực trả lời event %s (%s) -> tắt nhắc "
                         "STILL_BURNING; leo thang vẫn báo", track_id,
                         ack.event_id[:8], ack.action)

    # ---------------------------------------------------------------- helpers
    def _record(self, summary: RunSummary, hb: Heartbeat, result: DetectResult,
                voting: VotingEngine, out_dir: Path) -> None:
        summary.heartbeats += 1
        summary.infer_ms.append(result.infer_ms)
        ts = hb.frame.video_ts
        if result.detections:
            summary.heartbeats_with_det += 1
            for name, n in result.by_class().items():
                summary.detections_by_class[name] = (
                    summary.detections_by_class.get(name, 0) + n)
            boxes = ", ".join(
                f"{d.cls_name} {d.conf:.2f}@[{','.join(str(int(v)) for v in d.xyxy)}]"
                for d in result.detections)
            log.info("[video %7.2fs] hb#%04d %d det (%.0f ms): %s", ts, hb.seq,
                     len(result.detections), result.infer_ms, boxes)
            if self.cfg.output.save_frames:
                write_jpeg(out_dir / f"hb{hb.seq:05d}_{ts:07.2f}s.jpg",
                           self._annotated(hb, result, voting))
        elif self.cfg.output.log_every_heartbeat:
            log.info("[video %7.2fs] hb#%04d 0 det (%.0f ms)", ts, hb.seq,
                     result.infer_ms)

    def _annotated(self, hb: Heartbeat, result: DetectResult, voting: VotingEngine):
        banner = f"{hb.frame.video_ts:7.2f}s hb#{hb.seq}"
        if voting.confirmed:
            sev = max((t.severity for t in voting.confirmed), key=lambda s: s.rank)
            banner += f"  {sev.value}"
        img = draw_detections(hb.frame.image, result.detections, banner)
        return draw_tracks(img, voting.tracks, self.cfg.voting.window_m,
                           self.cfg.voting.k_enter)

    def _show(self, hb: Heartbeat, result: DetectResult, voting: VotingEngine) -> bool:
        """Display the annotated heartbeat; return False when the user quits."""
        cv2.imshow("FireWatch v3 (q=thoat)", self._annotated(hb, result, voting))
        return (cv2.waitKey(1) & 0xFF) != ord("q")


def _prune_runs(root: Path, keep: int) -> int:
    """Delete the oldest run folders so at most ``keep - 1`` remain (the new
    run makes ``keep``). ``keep == 0`` disables."""
    if keep <= 0 or not root.is_dir():
        return 0
    runs = sorted((p for p in root.iterdir() if p.is_dir()),
                  key=lambda p: p.stat().st_mtime)
    n = 0
    for old in runs[: max(0, len(runs) - (keep - 1))]:
        try:
            shutil.rmtree(old)
            n += 1
        except OSError as exc:
            log.warning("không xoá được run cũ %s: %s", old.name, exc)
    if n:
        log.info("retention: xoá %d thư mục run cũ trong %s (giữ %d)", n, root, keep)
    return n


def _attach_file_log(path: Path, toi_da_mb: float = 20.0,
                     so_ban: int = 5) -> logging.Handler:
    """Mirror the root logger to ``path`` for the duration of one run.

    File xoay vòng theo kích thước: đầy ``toi_da_mb`` MB thì đổi thành
    ``run.log.1`` (cũ hơn thành ``.2``...), giữ ``so_ban`` bản cũ, nên một lần
    ``serve`` chạy nhiều ngày không làm đầy đĩa. ``toi_da_mb = 0`` thì không xoay.
    """
    fh = logging.handlers.RotatingFileHandler(
        path, maxBytes=int(toi_da_mb * 1024 * 1024), backupCount=so_ban,
        encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(fh)
    return fh
