"""Load and validate ``config.yaml`` into typed objects.

Every tunable of the pipeline lives in one YAML file. This module turns it
into pydantic models so a typo in a key or a wrong type fails at start-up,
not in the middle of a demo. Relative paths are resolved against the
directory that contains the config file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Context = Literal["HAM", "TRET", "NGOAI"]


class _Strict(BaseModel):
    """Base model that rejects unknown keys (catches typos in YAML)."""

    model_config = ConfigDict(extra="forbid")


class CameraConfig(_Strict):
    id: str = "cam01"
    context: Context = "HAM"


class SourceConfig(_Strict):
    kind: Literal["auto", "file", "webcam", "rtsp"] = "auto"
    realtime: bool = False
    loop: bool = False
    reconnect_s: float = Field(2.0, ge=0)
    """Initial wait before reopening a live source; doubles up to 30 s."""
    max_reconnects: int = Field(0, ge=0)
    """Give up after this many consecutive failed reopen attempts; 0 = never."""
    read_timeout_s: float = Field(10.0, gt=0)
    """Open/read timeout for RTSP/HTTP streams so a dead link cannot hang."""


class HeartbeatConfig(_Strict):
    interval_s: float = Field(1.0, gt=0)
    ring_buffer: int = Field(5, ge=1)


class DetectorConfig(_Strict):
    weights: Path = Path("models/firewatch-v2.0.pt")
    fallback_weights: Path = Path("models/yolo26n.pt")
    backend: Literal["pt", "onnx"] = "pt"
    device: str = "cpu"
    imgsz: int = Field(640, ge=32)
    conf_threshold: float = Field(0.25, ge=0, le=1)
    conf_by_class: dict[str, float] = Field(default_factory=dict)
    """Per-class override of ``conf_threshold`` (e.g. lower for smoke)."""
    iou_nms: float = Field(0.5, ge=0, le=1)
    classes: list[str] = Field(default_factory=lambda: ["fire", "smoke"])
    class_aliases: dict[str, str] = Field(default_factory=dict)
    """Rename raw checkpoint class names (e.g. ``{"Fire": "fire"}``); names are
    lower-cased anyway, so this is for genuinely different wording."""
    max_det: int = Field(50, ge=1)
    warmup: bool = True
    require_classes: bool = False
    """Refuse to run when the loaded weights lack the configured classes.
    Always enforced for live sources and ``serve`` regardless of this flag."""


class OutputConfig(_Strict):
    dir: Path = Path("runs")
    save_frames: bool = True
    show: bool = False
    log_every_heartbeat: bool = True
    keep_runs: int = Field(30, ge=0)
    """Keep only the newest N run folders under ``dir``; 0 keeps everything."""


class VotingConfig(_Strict):
    window_m: int = Field(10, ge=1)
    k_enter: int = Field(6, ge=1)
    k_exit: int = Field(2, ge=1)
    k_fire: int = Field(2, ge=1)
    """Heartbeats in the window that must contain a *fire* box before the
    track counts as CRITICAL; below that it stays WARNING (smoke)."""
    iou_match: float = Field(0.3, ge=0, le=1)
    max_misses: int = Field(10, ge=1)
    cooldown_s: float = Field(60.0, ge=0)
    scene_cooldown_s: float = Field(60.0, ge=0)
    """After any alert, other tracks of the same camera stay silent this long
    unless they carry a higher severity. 0 disables. A track blocked by it
    keeps a pending flag and alerts as soon as the window closes."""
    realert_s: float = Field(60.0, ge=0)
    """While a track stays CONFIRMED, repeat the alert every this many seconds
    (STILL_BURNING). 0 disables repeats."""

    @model_validator(mode="after")
    def _consistent_thresholds(self) -> "VotingConfig":
        if not (1 <= self.k_exit <= self.k_enter <= self.window_m):
            raise ValueError(
                "voting: cần 1 <= k_exit <= k_enter <= window_m "
                f"(hiện k_exit={self.k_exit}, k_enter={self.k_enter}, "
                f"window_m={self.window_m})")
        if self.k_fire > self.k_enter:
            raise ValueError(f"voting.k_fire ({self.k_fire}) không được lớn hơn "
                             f"k_enter ({self.k_enter})")
        return self


class VLMConfig(_Strict):
    enabled: bool = True
    provider: Literal["gemini", "mock"] = "mock"
    model: str = "gemini-2.5-flash"
    api_url: str = "https://generativelanguage.googleapis.com/v1beta"
    api_key_env: str = "GEMINI_API_KEY"
    timeout_s: float = Field(10.0, gt=0)
    retries: int = Field(1, ge=0)
    grace_s: float = Field(2.0, ge=0)
    """Wall-clock budget to wait for the VLM before the alert goes out as
    UNVERIFIED; the verdict is patched onto the same event when it arrives."""
    thinking_budget: int | None = Field(None, ge=0)
    """Gemini 2.5 ``thinkingConfig.thinkingBudget`` (0 = no thinking);
    ``None`` = not sent. Gemini 3 models reject it (HTTP 400)."""
    thinking_level: Literal["minimal", "low", "medium", "high"] | None = "minimal"
    """Gemini 3 ``thinkingConfig.thinkingLevel``; wins over thinking_budget;
    ``None`` = not sent."""
    max_output_tokens: int = Field(200, ge=16)
    crop_padding: float = Field(0.25, ge=0)
    max_image_px: int = Field(640, ge=64)
    jpeg_quality: int = Field(70, ge=10, le=100)
    max_workers: int = Field(2, ge=1)
    mock_delay_s: float = Field(0.5, ge=0)
    mock_is_fire: bool = True
    mock_is_smoke: bool = True
    mock_confidence: float = Field(0.9, ge=0, le=1)
    mock_fire_type: Literal["UNCONTROLLED", "CONTROLLED", "UNKNOWN"] = "UNCONTROLLED"
    """Mock answer for ``vlm.fire_type`` (only kept for NGOAI, see vlm.py)."""


class CauDaoConfig(_Strict):
    """Cầu dao của verifier (ADR 2026-11-07-verifier-ben-vung)."""

    loi_lien_tiep: int = Field(3, ge=1)
    """Số yêu cầu xác minh thất bại liên tiếp thì mở cầu dao."""
    mo_s: float = Field(60.0, gt=0)
    """Cầu dao mở chừng này giây, sau đó cho đúng một lượt gọi thử."""


class VerifierConfig(_Strict):
    """Verifier bền vững, sau cờ ``ben_vung`` (mặc định tắt).

    Cờ tắt, hoặc thiếu khối ``verifier`` trong ``config.yaml``: hành vi, log và
    JSON của event y hệt trước khi có cờ.
    """

    ben_vung: bool = False
    ngan_sach_s: float = Field(10.0, gt=0)
    """Ngân sách nền tính từ lúc Voting quyết; quá hạn thì ``VLM_TIMEOUT``."""
    hang_cho_toi_da: int = Field(8, ge=1)
    """Số mục tối đa đang chờ gọi VLM, khoá theo ``event_id``."""
    cau_dao: CauDaoConfig = CauDaoConfig()


class AlertsConfig(_Strict):
    events_dir: Path = Path("events")
    snapshot_jpeg_quality: int = Field(90, ge=1, le=100)
    keep_days: float = Field(0, ge=0)
    """Delete event JSON + snapshot older than this many days at start-up;
    0 keeps everything."""
    notify_suppressed: bool = True
    """Push SUPPRESSED events to WebSocket/webhook too (they are always kept
    on disk for eval). False = only VERIFIED/UNVERIFIED reach the app."""
    webhook_url_env: str = "FIREWATCH_WEBHOOK_URL"
    webhook_token_env: str = "FIREWATCH_WEBHOOK_TOKEN"
    webhook_timeout_s: float = Field(5.0, gt=0)
    webhook_retries: int = Field(1, ge=0)
    save_raw_keyframe: bool = True
    """Also save the keyframe without boxes/banner (``<stem>_goc.jpg``) next to
    the snapshot, so dismissed alerts can be reused as clean hard negatives."""
    hitl_negatives_dir: Path = Path("data/hitl_negatives")
    """Where "dismiss — controlled fire" acks export keyframe + metadata."""
    escalation_s: float = Field(120.0, ge=0)
    """``serve``: a CRITICAL event nobody acknowledged is pushed again (same
    event_id, WebSocket + webhook) every this many seconds; 0 = off."""


class WebhookConfig(_Strict):
    """Nội dung payload webhook; URL và token đọc từ ``.env`` theo
    ``alerts.webhook_url_env`` / ``alerts.webhook_token_env``."""

    gui_anh: bool = False
    """Gửi kèm ``snapshot_base64``: keyframe gốc (không vẽ box) JPEG base64, chỉ
    trong payload webhook, không ghi file, không qua WebSocket."""
    anh_toi_da_kb: int = Field(200, ge=10)
    """Cỡ JPEG tối đa (KB): hạ chất lượng rồi thu nhỏ cho tới khi đủ nhỏ."""


class ServerConfig(_Strict):
    host: str = "0.0.0.0"
    port: int = Field(8000, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    """Origins allowed to call the REST API from a browser (React dashboard).
    ``["*"]`` is fine for the hackathon LAN; narrow it for anything public."""


class DataConfig(_Strict):
    clips_dir: Path = Path("data/raw/clips/moi")
    labels_dir: Path = Path("data/raw/clips/moi/labels")
    frames_dir: Path = Path("data/interim/frames_moi")
    extract_fps: float = Field(1.0, gt=0)
    split: tuple[float, float, float] = (0.7, 0.15, 0.15)
    seed: int = 42
    max_frames_per_clip: int = Field(0, ge=0)

    @field_validator("split")
    @classmethod
    def _sums_to_one(cls, v: tuple[float, float, float]) -> tuple[float, float, float]:
        if abs(sum(v) - 1.0) > 1e-6 or min(v) < 0:
            raise ValueError("data.split phải là 3 tỷ lệ không âm có tổng bằng 1")
        return v


class TrainConfig(_Strict):
    base_weights: Path = Path("models/firewatch-v1.0.pt")
    data_yaml: Path = Path("data/processed/datafirewatch/data.yaml")
    epochs: int = Field(50, ge=1)
    batch: int = Field(16, ge=1)
    imgsz: int = Field(640, ge=32)
    device: str = "cpu"
    patience: int = Field(20, ge=0)
    workers: int = Field(8, ge=0)
    cache: Literal["false", "ram", "disk"] = "false"
    seed: int = 42
    project: Path = Path("runs/train")
    name: str = "fire_smoke"


FinetuneTarget = Literal["fire", "smoke", "drop", "skip"]
"""drop = bỏ box, ảnh vẫn dùng; skip = bỏ CẢ ẢNH (nhãn lớp đó không tin được)."""


class FinetuneSource(_Strict):
    """One labelled source feeding scripts/build_finetune_set.py."""

    name: str
    role: Literal["domain", "hard_neg", "base"]
    format: Literal["yolo", "voc"] = "yolo"
    images: Path
    labels: Path | None = None
    """Label folder; ``None`` means labels sit next to the images."""
    classes: dict[str, FinetuneTarget]
    """Raw class id (YOLO) or name (VOC) -> fire / smoke / drop / skip."""
    manifest: Path | None = None
    """frames_manifest.csv from prepare_data: keeps labeled=1 rows, groups by clip."""
    group_regex: str | None = None
    """Regex on the image stem whose first group is the split group."""
    group_namespace: str | None = None
    """Sources sharing a namespace share split groups (e.g. fire and
    pre-ignition frames of one clip must land in the same split)."""
    require_label: bool = True
    """Skip images without a label file (unlabelled is not the same as empty)."""
    max_images: int = Field(0, ge=0)
    pool: int = Field(0, ge=0)
    """0 = every image; N = a fixed subset of N images (chosen by a hash of the
    file name) seen by both audit_data.py and the builder, for very large
    public sets such as FASDD."""
    keep_near_dups: bool = False
    """Do not drop near-duplicates *within* this source (audit ``dup_dist``),
    e.g. a benchmark's official train split used as published; leakage to
    held-out data and group merging still apply."""
    pool_by_prefix: dict[str, int] = Field(default_factory=dict)
    """Cap per file-name prefix (``{"smoke_": 4000}``), applied before ``pool``
    with the same hash order, to rebalance a public set whose name encodes
    the scene class (FASDD: fire_ / smoke_ / bothFireAndSmoke_ / neither...).
    Files matching no prefix are kept."""
    prefix: str = ""
    """Short name used in output file names (``<prefix>-<stem>``) for sources
    without a catalog clip id; empty = ``name``."""
    enabled: bool = True
    label_status: str = "verified"
    """Default status written to the dataset manifest (verified / pseudo / ...)."""
    status_csv: Path | None = None
    """CSV ``image,label_status`` overriding the default per image."""
    license: str = ""
    """Usage terms recorded per image in the dataset manifest and datasheet."""

    @field_validator("classes", mode="before")
    @classmethod
    def _keys_to_str(cls, v: dict) -> dict:
        return {str(k): val for k, val in (v or {}).items()}


class AuditHeldout(_Strict):
    """Data that must never reach training; used for the leakage check."""

    name: str
    images: Path | None = None
    videos: Path | None = None
    """Folder searched recursively for clips; frames hashed in memory."""
    catalog: Path | None = None
    """With ``videos``: only the clips listed in this CSV (``duong_dan``
    relative to ``videos``), and when it has a ``vai_tro`` column only rows
    whose role is ``role``. Lets clips moved to test by the catalog be held
    out without moving files."""
    role: str = "test"
    fps: float = Field(1.0, gt=0)
    scene_dist: int | None = Field(None, ge=0, le=16)
    """Also drop training images of the same *scene* as this held-out set:
    dHash within this distance (looser than ``audit.leak_dist``) and
    thumbnail correlation ≥ ``scene_corr``. For held-out videos whose other
    frames are known to circulate in public datasets (e.g. FIRESENSE and
    VisiFire inside FASDD): a fixed camera gives near-identical frames at
    every moment, which the strict leak check misses."""
    scene_corr: float = Field(0.85, ge=0, le=1)


class AuditConfig(_Strict):
    out_dir: Path = Path("data/interim/audit")
    min_side: int = Field(128, ge=1)
    """Images whose short side is below this are dropped."""
    dup_dist: int = Field(2, ge=0, le=16)
    """dHash bits: near-identical images inside one source (keep one)."""
    thin_dist: int = Field(3, ge=0, le=16)
    """dHash bits: consecutive frames of one clip that add nothing new."""
    merge_dist: int = Field(4, ge=0, le=16)
    """dHash bits: same scene under two group names -> merge the groups."""
    merge_scene_dist: int | None = Field(None, ge=0, le=16)
    """Looser second merge pass (dHash within this distance and thumbnail
    correlation ≥ ``min_corr``) so frames of one camera filed as separate
    images in public sets never straddle train and val."""
    leak_dist: int = Field(4, ge=0, le=16)
    """dHash bits: training image this close to a held-out frame is dropped."""
    min_corr: float = Field(0.90, ge=0, le=1)
    """Every dHash candidate must also have thumbnail correlation ≥ this."""
    thin_sources: list[str] = Field(default_factory=list)
    """Sources made of video frames, thinned in time order."""
    heldout: list[AuditHeldout] = Field(default_factory=list)


class GrayVariantConfig(_Strict):
    """Extra black-and-white copy of every image (night / IR camera look)."""

    enabled: bool = False
    mode: Literal["ir", "gray"] = "ir"
    """``ir``: grayscale plus mild random gamma, contrast, blur and sensor
    noise (``firewatch.irsim``); ``gray``: plain grayscale."""
    suffix: str = "_xam"
    """Appended to the image stem; the copy keeps the original's labels and
    split."""
    fraction: float = Field(1.0, ge=0, le=1)
    """Share of the base train originals that get a copy (domain originals
    always do; see ``firewatch.trainlists.wants_copy``)."""
    max_bright_outside: float = Field(1.0, ge=0, le=1)
    """Drop a copy whose pixels outside the boxes are clipped to white above
    this share (``firewatch.irsim.bright_outside``)."""


class CameraVariantConfig(_Strict):
    """Extra copy of every image through one camera-processing effect."""

    enabled: bool = False
    suffix: str = "_cam"
    weights: dict[str, float] = Field(default_factory=lambda: {
        "dem_mau": 1.0, "nen_thap": 1.0, "loa_sang": 1.0, "ong_kinh": 1.0,
        "mo": 1.0, "osd": 0.5})
    """Relative frequency of each effect of ``firewatch.camsim``."""
    osd_prob: float = Field(0.3, ge=0, le=1)
    """Chance of burning a timestamp in on top of another effect."""
    fraction: float = Field(1.0, ge=0, le=1)
    """Share of the base train originals that get a copy."""
    small_fire_px: float = Field(8.0, ge=0)
    """No low-bitrate effect when a fire box is shorter than this at 640 px."""

    @field_validator("weights")
    @classmethod
    def _known(cls, v: dict[str, float]) -> dict[str, float]:
        known = {"dem_mau", "nen_thap", "loa_sang", "ong_kinh", "mo", "osd"}
        if not v or set(v) - known or any(x < 0 for x in v.values()) \
                or sum(v.values()) <= 0:
            raise ValueError(f"camera_variant.weights chỉ nhận {sorted(known)}, "
                             "giá trị không âm, tổng > 0")
        return v


class RegroupConfig(_Strict):
    """Merge split groups of public images cut from one clip / camera
    (``firewatch.scenegroup``) before the train / val split."""

    enabled: bool = False
    corr_any: float = Field(0.98, ge=0, le=1)
    corr_seq: float = Field(0.90, ge=0, le=1)
    seq_window: int = Field(20, ge=0)


class TrainListConfig(_Strict):
    """train.txt / val.txt written from the manifest (``firewatch.trainlists``)."""

    enabled: bool = False
    clip_target: int = Field(20, ge=1)
    """Domain positive originals per clip per epoch the repeats aim for."""
    caps: dict[str, int] = Field(default_factory=dict)
    """Largest repeat by catalog ``camera`` or ``context`` (e.g. cctv: 4)."""
    camera_max: dict[str, int] = Field(default_factory=dict)
    """Upper bound by camera whatever the context (e.g. tin_tuc: 2)."""
    default_cap: int = Field(1, ge=1)
    neg_domain_repeat: int = Field(1, ge=1)


class FinetuneConfig(_Strict):
    out_dir: Path = Path("data/processed/datafirewatch")
    audit_dir: Path | None = None
    """When set, exclusions.csv and groups.csv from audit_data.py are applied."""
    frame_exclusions: list[Path] = Field(default_factory=list)
    """CSVs with an ``image`` column (file name) of frames never to use, e.g.
    khung_rac.csv from scripts/clean_clips.py (frames inside junk segments)."""
    catalog: Path | None = None
    """data/catalog/clips.csv from scripts/build_catalog.py: standard clip id,
    country, context, camera, time of day per original clip name."""
    dataset_name: str = "finetune"
    dataset_version: str = "0.0"
    review_queue: Path | None = None
    """CSV of frames held back for human review (reported in the datasheet)."""
    keep_domain: bool = False
    """With ``target_total``: keep every domain image (positive and negative)
    and fill the rest of the total with base images, ignoring ``ratios``."""
    gray_variant: GrayVariantConfig = GrayVariantConfig()
    camera_variant: CameraVariantConfig = CameraVariantConfig()
    val_domain_copies: bool = True
    """Synthetic copies of domain val images (listed apart, never in val.txt
    when ``lists`` is enabled)."""
    regroup: RegroupConfig = RegroupConfig()
    lists: TrainListConfig = TrainListConfig()
    base_min_fire_px: float = Field(0.0, ge=0)
    """Drop base images with a fire box shorter than this at 640 px (a fifth
    of D-Fire boxes under 16 px sat on objects that do not burn)."""
    base_min_long_side: int = Field(0, ge=0)
    """Drop base images whose long side is below this (upscaled > 2x)."""
    general_detector: bool = False
    """Datasheet wording: a general fire / smoke detector trained from COCO
    for public benchmarks (v2.0) instead of the tier-1 fine-tune of
    FireWatch-v1.0 (``models/firewatch-v1.0.pt``) for the parking-lot context
    (v0.x / v1.x)."""
    heldout_skip: list[str] = Field(default_factory=list)
    """Names in ``audit.heldout`` this profile does NOT hold out, e.g. a
    public benchmark's test split when its official train split is used in
    full (the benchmark's own train/test leakage then stays as published and
    must be reported next to a cleaned subset)."""
    fill_neg_from_base: bool = True
    """When domain negatives fall short of their ratio, top up with negative
    images (no fire/smoke box) from base sources, reported as ``neg_fill``."""
    val_ratio: float = Field(0.15, ge=0, lt=1)
    seed: int = 42
    target_total: int = Field(0, ge=0)
    """0 = keep every domain positive and size the rest by ``ratios``."""
    ratios: dict[str, float] = Field(default_factory=lambda: {
        "pos_domain": 0.35, "neg_domain": 0.35, "base": 0.30})
    link: bool = True
    """Hard-link images instead of copying when on the same drive."""
    sources: list[FinetuneSource] = Field(default_factory=list)

    @field_validator("ratios")
    @classmethod
    def _ratio_keys(cls, v: dict[str, float]) -> dict[str, float]:
        need = {"pos_domain", "neg_domain", "base"}
        if set(v) != need or any(x < 0 for x in v.values()) or sum(v.values()) <= 0:
            raise ValueError(f"finetune.ratios cần đúng các khoá {sorted(need)}, "
                             "giá trị không âm")
        total = sum(v.values())
        return {k: x / total for k, x in v.items()}


class EvalModel(_Strict):
    name: str
    weights: Path
    source: str = ""


class EvalFramesConfig(_Strict):
    images_dir: Path = Path("data/external/dfire/test/images")
    labels_dir: Path = Path("data/external/dfire/test/labels")
    manifest: Path | None = None
    """CSV from prepare_data.py (image, context, split...) for per-context metrics."""
    split: str = "test"
    conf_report: float = Field(0.25, ge=0, le=1)
    conf_min: float = Field(0.001, ge=0, le=1)
    iou: float = Field(0.5, ge=0, le=1)
    limit: int = Field(0, ge=0)
    seed: int = 42


class EvalEventsConfig(_Strict):
    clips_dir: Path = Path("data/eval/vn_test")
    tolerance_s: float = Field(30.0, ge=0)


class EvalConfig(_Strict):
    models: list[EvalModel] = Field(default_factory=list)
    frames: EvalFramesConfig = EvalFramesConfig()
    events: EvalEventsConfig = EvalEventsConfig()
    reports_dir: Path = Path("reports")


class Config(_Strict):
    """Whole ``config.yaml``; ``root`` is the directory it was loaded from."""

    camera: CameraConfig = CameraConfig()
    source: SourceConfig = SourceConfig()
    heartbeat: HeartbeatConfig = HeartbeatConfig()
    detector: DetectorConfig = DetectorConfig()
    output: OutputConfig = OutputConfig()
    voting: VotingConfig = VotingConfig()
    vlm: VLMConfig = VLMConfig()
    verifier: VerifierConfig = VerifierConfig()
    alerts: AlertsConfig = AlertsConfig()
    webhook: WebhookConfig = WebhookConfig()
    server: ServerConfig = ServerConfig()
    data: DataConfig = DataConfig()
    train: TrainConfig = TrainConfig()
    finetune: FinetuneConfig = FinetuneConfig()
    datasets: dict[str, FinetuneConfig] = Field(default_factory=dict)
    """Extra named dataset profiles (same schema as ``finetune``), selected
    with ``--profile`` in build_finetune_set.py and audit_data.py."""
    audit: AuditConfig = AuditConfig()
    eval: EvalConfig = EvalConfig()
    root: Path = Field(default_factory=Path.cwd, exclude=True)

    @model_validator(mode="after")
    def _ngan_sach_dai_hon_cua_so(self) -> "Config":
        if self.verifier.ben_vung and self.verifier.ngan_sach_s <= self.vlm.grace_s:
            raise ValueError(
                f"verifier.ngan_sach_s ({self.verifier.ngan_sach_s}) phải lớn hơn "
                f"vlm.grace_s ({self.vlm.grace_s}) khi verifier.ben_vung bật")
        return self

    def with_profile(self, name: str | None) -> "Config":
        """Copy of the config whose ``finetune`` is dataset profile ``name``.

        Parameters
        ----------
        name : str or None
            Key of ``datasets``; ``None`` returns ``self`` unchanged.

        Returns
        -------
        Config
            Config to hand to the dataset scripts.

        Raises
        ------
        KeyError
            When ``name`` is not a configured profile.
        """
        if name is None:
            return self
        if name not in self.datasets:
            raise KeyError(f"không có datasets.{name} trong config "
                           f"(có: {', '.join(sorted(self.datasets)) or 'không'})")
        return self.model_copy(update={"finetune": self.datasets[name]})

    def resolve(self, path: Path) -> Path:
        """Return ``path`` made absolute relative to the config directory."""
        return path if path.is_absolute() else (self.root / path).resolve()

    def rel(self, path: Path) -> str:
        """Path shown relative to the repo root (for reports), posix style."""
        try:
            return Path(path).resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return Path(path).as_posix()


def find_config(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: cwd) until a ``config.yaml`` is found.

    Raises
    ------
    FileNotFoundError
        If no ``config.yaml`` exists in ``start`` or any parent.
    """
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        candidate = folder / "config.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("không tìm thấy config.yaml từ thư mục hiện tại trở lên")


def apply_overrides(raw: dict, overrides: list[str] | None) -> dict:
    """Apply ``section.key=value`` overrides (from ``--set``) to a raw config.

    Values are parsed as YAML, so ``--set voting.k_enter=3`` gives an int and
    ``--set detector.classes=[fire]`` a list.

    Raises
    ------
    ValueError
        If an override is not of the form ``a.b=value``.
    """
    for item in overrides or []:
        if "=" not in item:
            raise ValueError(f"--set cần dạng section.key=value, nhận: {item!r}")
        dotted, value = item.split("=", 1)
        keys = dotted.strip().split(".")
        node = raw
        for k in keys[:-1]:
            node = node.setdefault(k, {})
            if not isinstance(node, dict):
                raise ValueError(f"--set {dotted}: {k} không phải là một section")
        node[keys[-1]] = yaml.safe_load(value)
    return raw


def load_config(path: str | Path | None = None,
                overrides: list[str] | None = None) -> Config:
    """Read ``config.yaml`` (and ``.env`` next to it) and validate it.

    Parameters
    ----------
    path : str or Path, optional
        Explicit config path. When omitted the file is searched upward
        from the current directory.
    overrides : list of str, optional
        ``section.key=value`` items applied on top of the file.
    """
    cfg_path = Path(path) if path else find_config()
    cfg_path = cfg_path.resolve()
    load_dotenv(cfg_path.parent / ".env", override=False)
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    raw = apply_overrides(raw, overrides)
    return Config(**raw, root=cfg_path.parent)


def env_secret(name: str) -> str | None:
    """Return a secret from the environment, treating empty strings as unset."""
    value = os.environ.get(name, "").strip()
    return value or None
