"""Tier 4 — VLM verification of a confirmed track.

``VLMVerifier`` is the provider interface (one class per provider, swap in
``build_verifier``). ``VerificationService`` runs the call on a worker
thread so the heartbeat loop never blocks, applies timeout + retry, and
maps the answer to the event ``verification`` field:

* VLM sees fire or smoke  → ``VERIFIED``
* VLM sees neither        → ``SUPPRESSED`` (still logged as an event)
* error / timeout / off   → ``UNVERIFIED`` (alert anyway: fail-open)

Gemini is called through its REST endpoint with ``urllib`` (no extra SDK).
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .alerts import FireType, Verification, VerifierInfo, VLMResult
from .config import Context, VLMConfig, env_secret

log = logging.getLogger(__name__)

CONTEXT_DESC: dict[str, str] = {
    "HAM": "hầm giữ xe chung cư",
    "TRET": "tầng trệt / nhà xe trong nhà",
    "NGOAI": "sân để xe ngoài trời trước nhà",
}

PROMPT_VI = (
    "Bạn là bộ xác minh cảnh báo cháy cho camera an ninh tại khu để xe "
    "({context_desc}). Detector vừa nghi có {severity_desc}.\n"
    "{images_desc}\n"
    "Trả lời CHỈ bằng JSON đúng dạng: "
    '{{"is_fire": bool, "is_smoke": bool, "confidence": số 0-1, '
    '"description_vi": "đúng một câu tiếng Việt mô tả điều bạn thấy"{extra_key}}}.\n'
    "is_fire = thấy ngọn lửa thật (không phải đèn pha, đèn tín hiệu, phản chiếu, "
    "ánh nắng). is_smoke = thấy khói thật (không phải hơi nước, sương, bụi, "
    "khói xả thoáng qua). confidence = mức chắc chắn của kết luận. "
    "description_vi chỉ đúng 1 câu.{fire_type_rule}"
)

FIRE_TYPE_RULE_VI = (
    "\nfire_type chỉ một trong UNCONTROLLED | CONTROLLED | UNKNOWN. CONTROLLED = "
    "lửa có kiểm soát: lửa nằm trong hoặc trên vật chứa (lò than, bếp, thùng đốt), "
    "có người đứng thao tác bình thản gần lửa, khói trắng mỏng của than/nấu ăn, lửa "
    "không lan giữa hai khung. UNCONTROLLED = lửa trên, dưới hoặc cạnh phương tiện, "
    "khói đen dày (xăng dầu, cao su, nhựa), lửa lan rộng hơn giữa hai khung, người "
    "hoảng loạn hoặc đang dập lửa. Không chắc thì UNKNOWN. Nếu CONTROLLED, câu "
    "description_vi phải nói rõ nghi nấu nướng hoặc đốt có kiểm soát."
)

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "is_fire": {"type": "BOOLEAN"},
        "is_smoke": {"type": "BOOLEAN"},
        "confidence": {"type": "NUMBER"},
        "description_vi": {"type": "STRING"},
    },
    "required": ["is_fire", "is_smoke", "confidence", "description_vi"],
}

RESPONSE_SCHEMA_FIRE_TYPE = {
    "type": "OBJECT",
    "properties": {
        **RESPONSE_SCHEMA["properties"],
        "fire_type": {"type": "STRING",
                      "enum": ["UNCONTROLLED", "CONTROLLED", "UNKNOWN"]},
    },
    "required": [*RESPONSE_SCHEMA["required"], "fire_type"],
}

CONTROLLED_NOTE_VI = "Nghi lửa có kiểm soát (nấu nướng/đốt), người trực xác nhận: "


def classifies_fire_type(context: Context) -> bool:
    """Only open-air scenes get the controlled/uncontrolled question; indoor
    parking (HAM, TRET) is always treated as an incident."""
    return context == "NGOAI"


def build_prompt(context: Context, severity: str, two_frames: bool) -> str:
    """Prompt text for one verification (Vietnamese)."""
    images = ("Ảnh 1 là toàn khung lúc track mới xuất hiện, ảnh 2 là toàn khung "
              "lúc cảnh báo, ảnh 3 là vùng nghi ngờ ở ảnh 2 đã nới rộng."
              if two_frames else
              "Ảnh 1 là toàn khung hình, ảnh 2 là vùng nghi ngờ đã nới rộng.")
    ask = classifies_fire_type(context)
    return PROMPT_VI.format(
        context_desc=CONTEXT_DESC.get(context, context),
        severity_desc="lửa" if severity == "CRITICAL" else "khói",
        images_desc=images,
        extra_key=', "fire_type": "UNCONTROLLED|CONTROLLED|UNKNOWN"' if ask else "",
        fire_type_rule=FIRE_TYPE_RULE_VI if ask else "")


def apply_fire_type_policy(result: VLMResult, context: Context) -> VLMResult:
    """Context policy for ``fire_type``; never touches is_fire / is_smoke.

    HAM / TRET: always ``UNCONTROLLED`` whatever the model said. NGOAI: the
    model's answer, ``UNKNOWN`` when missing; a ``CONTROLLED`` description is
    guaranteed to say so, so the operator (the only one allowed to dismiss)
    sees why.
    """
    if not classifies_fire_type(context):
        return result.model_copy(update={"fire_type": "UNCONTROLLED"})
    fire_type = result.fire_type or "UNKNOWN"
    desc = result.description_vi
    if fire_type == "CONTROLLED" and "kiểm soát" not in desc.lower():
        desc = CONTROLLED_NOTE_VI + desc
    return result.model_copy(update={"fire_type": fire_type, "description_vi": desc})


# ----------------------------------------------------------------- helpers
def encode_jpeg(image: np.ndarray, max_px: int = 640, quality: int = 70) -> bytes:
    """JPEG-encode a BGR image, downscaling so the long side is ≤ ``max_px``."""
    h, w = image.shape[:2]
    scale = max_px / max(h, w)
    if scale < 1:
        image = cv2.resize(image, (round(w * scale), round(h * scale)),
                           interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("không encode được JPEG")
    return buf.tobytes()


def crop_with_padding(image: np.ndarray, box: tuple[float, float, float, float],
                      padding: float) -> np.ndarray:
    """Crop ``box`` grown by ``padding`` × its side on each edge, clipped."""
    h, w = image.shape[:2]
    x1, y1, x2, y2 = box
    pw, ph = (x2 - x1) * padding, (y2 - y1) * padding
    cx1, cy1 = max(0, int(x1 - pw)), max(0, int(y1 - ph))
    cx2, cy2 = min(w, int(round(x2 + pw))), min(h, int(round(y2 + ph)))
    if cx2 <= cx1 or cy2 <= cy1:
        return image
    return image[cy1:cy2, cx1:cx2]


def verification_from(result: VLMResult | None) -> Verification:
    """Map a VLM answer (or its absence) to the event ``verification``."""
    if result is None:
        return "UNVERIFIED"
    return "VERIFIED" if (result.is_fire or result.is_smoke) else "SUPPRESSED"


# --------------------------------------------------------------- providers
class VLMVerifier(ABC):
    """One provider. ``verify`` may block; the service runs it on a thread."""

    name = "abstract"

    @abstractmethod
    def verify(self, frame_jpeg: bytes, crop_jpeg: bytes, context: Context,
               severity: str, first_jpeg: bytes | None = None,
               timeout_s: float | None = None) -> VLMResult:
        """Judge the alert keyframe (+ crop); ``first_jpeg`` is the frame from
        when the track appeared, to see whether the fire spreads.

        ``timeout_s`` chỉ được truyền khi cờ ``verifier.ben_vung`` bật: timeout
        của riêng lượt này, thay timeout cấu hình. ``None`` giữ hành vi cũ."""


class MockVerifier(VLMVerifier):
    """Offline stand-in: waits ``delay_s`` then returns a configured answer."""

    name = "mock"

    def __init__(self, delay_s: float = 0.5, is_fire: bool = True,
                 is_smoke: bool = True, confidence: float = 0.9,
                 fire_type: FireType = "UNCONTROLLED"):
        self.delay_s, self.is_fire = delay_s, is_fire
        self.is_smoke, self.confidence = is_smoke, confidence
        self.fire_type = fire_type

    def verify(self, frame_jpeg: bytes, crop_jpeg: bytes, context: Context,
               severity: str, first_jpeg: bytes | None = None,
               timeout_s: float | None = None) -> VLMResult:
        """Chờ ``delay_s`` rồi trả lời; ``timeout_s`` ngắn hơn thì hết giờ."""
        if timeout_s is not None and self.delay_s > timeout_s:
            time.sleep(timeout_s)
            raise TimeoutError(f"mock quá {timeout_s:.1f}s")
        time.sleep(self.delay_s)
        what = ("lửa và khói" if self.is_fire and self.is_smoke else
                "lửa" if self.is_fire else "khói" if self.is_smoke else
                "không có lửa hay khói")
        return VLMResult(is_fire=self.is_fire, is_smoke=self.is_smoke,
                         confidence=self.confidence,
                         description_vi=f"[mock] Giả lập: {what} tại "
                                        f"{CONTEXT_DESC.get(context, context)}.",
                         fire_type=self.fire_type)


class GeminiHTTPError(RuntimeError):
    """Non-2xx answer from Gemini, keeping the status and (trimmed) body."""

    def __init__(self, code: int, body: str):
        super().__init__(f"HTTP {code}: {body[:200]}")
        self.code, self.body = code, body


class GeminiVerifier(VLMVerifier):
    """Gemini ``generateContent`` over REST with a JSON response schema.

    Parameters
    ----------
    model, api_key, timeout_s, api_url
        Endpoint and per-request urllib timeout.
    thinking_budget : int or None
        ``thinkingConfig.thinkingBudget`` (Gemini 2.5: 0 turns thinking off).
    thinking_level : str or None
        ``thinkingConfig.thinkingLevel`` (Gemini 3: ``minimal`` / ``low``);
        takes precedence over ``thinking_budget``. Both ``None`` omits
        ``thinkingConfig``. Gemini 3 flash-lite rejects ``thinkingBudget`` with
        a bare HTTP 400 "invalid argument", so any 400 while thinkingConfig is
        sent is retried once without it; only if that retry succeeds are later
        calls sent without thinkingConfig.
    max_output_tokens : int
        ``generationConfig.maxOutputTokens``.
    """

    name = "gemini"

    def __init__(self, model: str, api_key: str, timeout_s: float,
                 api_url: str = "https://generativelanguage.googleapis.com/v1beta",
                 thinking_budget: int | None = 0, max_output_tokens: int = 200,
                 thinking_level: str | None = None):
        self.model, self.api_key, self.timeout_s = model, api_key, timeout_s
        self.url = f"{api_url}/models/{model}:generateContent"
        self.thinking: dict[str, Any] | None = (
            {"thinkingLevel": thinking_level} if thinking_level
            else {"thinkingBudget": thinking_budget} if thinking_budget is not None
            else None)
        self.max_output_tokens = max_output_tokens

    def build_request(self, frame_jpeg: bytes, crop_jpeg: bytes, context: Context,
                      severity: str, first_jpeg: bytes | None = None
                      ) -> dict[str, Any]:
        images = ([first_jpeg] if first_jpeg else []) + [frame_jpeg, crop_jpeg]
        parts: list[dict[str, Any]] = [
            {"text": build_prompt(context, severity, two_frames=bool(first_jpeg))}]
        for img in images:
            parts.append({"inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(img).decode("ascii")}})
        gen: dict[str, Any] = {
            "temperature": 0,
            "maxOutputTokens": self.max_output_tokens,
            "response_mime_type": "application/json",
            "response_schema": (RESPONSE_SCHEMA_FIRE_TYPE
                                if classifies_fire_type(context) else RESPONSE_SCHEMA),
        }
        if self.thinking is not None:
            gen["thinkingConfig"] = dict(self.thinking)
        return {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": gen}

    def _post(self, body: dict[str, Any],
              timeout_s: float | None = None) -> dict[str, Any]:
        """HTTP call; separated so tests can inject a fake transport.

        ``timeout_s`` (cờ ``ben_vung``) thay ``self.timeout_s`` cho lượt này.
        """
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json",
                     "x-goog-api-key": self.api_key})
        han = self.timeout_s if timeout_s is None else timeout_s
        try:
            with urllib.request.urlopen(req, timeout=han) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", "replace")
            raise GeminiHTTPError(exc.code, body_text) from exc

    def _log_usage(self, response: dict[str, Any], latency_s: float) -> None:
        """Log latency and thinking tokens; thinking should be 0 when disabled."""
        usage = response.get("usageMetadata") or {}
        thoughts = int(usage.get("thoughtsTokenCount") or 0)
        log.info("Gemini %s: %.0f ms, thoughtsTokenCount=%d, output=%s token",
                 self.model, latency_s * 1000, thoughts,
                 usage.get("candidatesTokenCount", "?"))
        if thoughts > 0:
            log.warning("Gemini %s vẫn dùng %d token suy nghĩ dù thinkingConfig=%s: "
                        "cấu hình không được tôn trọng, latency sẽ cao",
                        self.model, thoughts, self.thinking)

    @staticmethod
    def parse(response: dict[str, Any]) -> VLMResult:
        """Extract the JSON answer from a ``generateContent`` response.

        Raises
        ------
        ValueError
            If the response has no candidate text or the text is not the
            expected JSON object.
        """
        try:
            text = response["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            reason = response.get("promptFeedback") or response.get("error")
            raise ValueError(f"Gemini không trả nội dung: {reason}") from exc
        data = json.loads(text)
        data["confidence"] = min(1.0, max(0.0, float(data.get("confidence", 0))))
        return VLMResult(**data)

    def verify(self, frame_jpeg: bytes, crop_jpeg: bytes, context: Context,
               severity: str, first_jpeg: bytes | None = None,
               timeout_s: float | None = None) -> VLMResult:
        body = self.build_request(frame_jpeg, crop_jpeg, context, severity,
                                  first_jpeg)
        t0 = time.perf_counter()
        # Chỉ truyền khi có, để transport giả trong test cũ (một tham số) vẫn chạy.
        han = {} if timeout_s is None else {"timeout_s": timeout_s}
        try:
            response = self._post(body, **han)
        except GeminiHTTPError as exc:
            if exc.code != 400 or "thinkingConfig" not in body["generationConfig"]:
                raise
            gen = dict(body["generationConfig"])
            sent = gen.pop("thinkingConfig")
            log.warning("Gemini %s trả HTTP 400 khi có thinkingConfig=%s (%s): "
                        "gửi lại không kèm", self.model, sent,
                        exc.body[:120].replace("\n", " "))
            response = self._post({**body, "generationConfig": gen}, **han)
            self.thinking = None    # gửi lại thành công: lỗi do thinkingConfig
            log.warning("Gemini %s: các lần sau không gửi thinkingConfig", self.model)
        self._log_usage(response, time.perf_counter() - t0)
        return self.parse(response)


def build_verifier(cfg: VLMConfig) -> VLMVerifier | None:
    """Instantiate the configured provider; ``None`` means "verify disabled"."""
    if not cfg.enabled:
        log.info("VLM tắt (vlm.enabled=false): mọi event là UNVERIFIED")
        return None
    if cfg.provider == "mock":
        log.warning("VLM provider MOCK: verification trong event là GIẢ LẬP "
                    "(is_fire=%s is_smoke=%s sau %.1fs, description_vi có tiền tố "
                    "[mock]). Đổi vlm.provider=gemini trước khi vận hành thật.",
                    cfg.mock_is_fire, cfg.mock_is_smoke, cfg.mock_delay_s)
        return MockVerifier(cfg.mock_delay_s, cfg.mock_is_fire, cfg.mock_is_smoke,
                            cfg.mock_confidence, cfg.mock_fire_type)
    key = env_secret(cfg.api_key_env)
    if not key:
        log.error("vlm.provider=gemini nhưng thiếu %s trong .env/môi trường: "
                  "VLM tắt, event sẽ là UNVERIFIED (đổi vlm.provider=mock để demo)",
                  cfg.api_key_env)
        return None
    log.info("VLM provider gemini: model %s, timeout %.0fs, retry %d, "
             "thinkingLevel %s, thinkingBudget %s, maxOutputTokens %d, ảnh %dpx q%d",
             cfg.model, cfg.timeout_s, cfg.retries, cfg.thinking_level,
             cfg.thinking_budget, cfg.max_output_tokens, cfg.max_image_px,
             cfg.jpeg_quality)
    return GeminiVerifier(cfg.model, key, cfg.timeout_s, cfg.api_url,
                          cfg.thinking_budget, cfg.max_output_tokens,
                          cfg.thinking_level)


# ----------------------------------------------------------------- service
@dataclass(slots=True)
class VerifyRequest:
    """What the service needs to verify one confirmed track."""

    frame: np.ndarray
    box: tuple[float, float, float, float]
    context: Context
    severity: str
    video_ts: float
    first_frame: np.ndarray | None = None
    """Frame of the track's earliest vote in the window (``None``: only one)."""


@dataclass(slots=True)
class VerifyOutcome:
    verification: Verification
    result: VLMResult | None
    latency_s: float
    attempts: int
    error: str | None = None
    reason: str | None = None
    """Mã ngắn của lỗi (``alerts.LY_DO``) khi không có câu trả lời; không chứa
    body HTTP hay chuỗi lỗi thô (cái đó nằm ở ``error``, chỉ để log)."""


OnDone = Callable[[VerifyOutcome], None]


def ma_loi(exc: BaseException) -> str:
    """Mã lý do ngắn cho một lỗi gọi VLM.

    Parameters
    ----------
    exc : BaseException
        Lỗi của lượt gọi cuối.

    Returns
    -------
    str
        ``http_429``, ``http_4xx``, ``http_5xx``, ``loi_phan_tich`` (trả lời
        không đọc được) hoặc ``loi_mang`` (mọi lỗi còn lại, kể cả timeout
        của một lượt gọi).
    """
    if isinstance(exc, GeminiHTTPError):
        if exc.code == 429:
            return "http_429"
        if 400 <= exc.code < 500:
            return "http_4xx"
        if exc.code >= 500:
            return "http_5xx"
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return "loi_phan_tich"
    return "loi_mang"


def trang_thai_verifier(outcome: VerifyOutcome) -> VerifierInfo:
    """Trạng thái verifier của một kết quả VLM đã có (cờ ``ben_vung`` bật).

    Có câu trả lời: ``VERIFIED`` hoặc ``REJECTED`` kèm độ trễ. VLM tắt hoặc
    thiếu key: ``VLM_OFF``. Lỗi: ``VLM_ERROR``. Hai trạng thái sau cần người
    trực tự xác thực. Không bao giờ đổi mức cảnh báo.
    """
    if outcome.result is not None:
        status = "VERIFIED" if outcome.verification == "VERIFIED" else "REJECTED"
        return VerifierInfo.tao(status, latency_s=outcome.latency_s)
    if outcome.reason == "vlm_tat":
        return VerifierInfo.tao("VLM_OFF", reason="vlm_tat")
    return VerifierInfo.tao("VLM_ERROR", reason=outcome.reason or "loi_mang")


class VerificationService:
    """Run provider calls on worker threads with timeout, retry, fail-open."""

    def __init__(self, cfg: VLMConfig, verifier: VLMVerifier | None):
        self.cfg = cfg
        self.verifier = verifier
        self._pool = ThreadPoolExecutor(max_workers=cfg.max_workers,
                                        thread_name_prefix="vlm")
        self._pending: set[Future] = set()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.verifier is not None

    def submit(self, req: VerifyRequest, on_done: OnDone | None = None) -> Future:
        """Schedule a verification and return a ``Future[VerifyOutcome]``.

        With no verifier the future is already resolved to ``UNVERIFIED``.
        ``on_done`` (optional) runs on the worker thread when the result is in.
        """
        if self.verifier is None:
            fut: Future = Future()
            fut.set_result(VerifyOutcome("UNVERIFIED", None, 0.0, 0, "vlm disabled",
                                         "vlm_tat"))
            if on_done:
                on_done(fut.result())
            return fut
        fut = self._pool.submit(self.run_sync, req)
        with self._lock:
            self._pending.add(fut)
        fut.add_done_callback(self._forget)
        if on_done:
            fut.add_done_callback(lambda f: on_done(f.result()))
        return fut

    def _forget(self, fut: Future) -> None:
        with self._lock:
            self._pending.discard(fut)
        if fut.exception() is not None:
            log.error("VLM worker lỗi không bắt được: %s", fut.exception())

    def _ma_hoa(self, req: VerifyRequest) -> tuple[bytes, bytes, bytes | None]:
        """JPEG của keyframe, vùng nghi ngờ và khung đầu track (nếu có)."""
        frame_jpeg = encode_jpeg(req.frame, self.cfg.max_image_px,
                                 self.cfg.jpeg_quality)
        crop = crop_with_padding(req.frame, req.box, self.cfg.crop_padding)
        crop_jpeg = encode_jpeg(crop, self.cfg.max_image_px, self.cfg.jpeg_quality)
        first_jpeg = (encode_jpeg(req.first_frame, self.cfg.max_image_px,
                                  self.cfg.jpeg_quality)
                      if req.first_frame is not None else None)
        return frame_jpeg, crop_jpeg, first_jpeg

    def goi_mot_lan(self, req: VerifyRequest, timeout_s: float) -> VerifyOutcome:
        """Một lượt gọi VLM, không retry, timeout cho trước (cờ ``ben_vung``).

        Chạy trên luồng của người gọi. Lỗi không ném ra ngoài mà thành
        ``UNVERIFIED`` kèm mã ``reason`` ngắn; chuỗi lỗi thô chỉ để log.

        Parameters
        ----------
        req : VerifyRequest
            Keyframe và vùng cần xác minh.
        timeout_s : float
            Timeout của lượt gọi (ngân sách còn lại trừ phần dự phòng).

        Returns
        -------
        VerifyOutcome
            ``latency_s`` là thời gian của riêng lượt gọi này.
        """
        assert self.verifier is not None
        t0 = time.perf_counter()
        try:
            frame_jpeg, crop_jpeg, first_jpeg = self._ma_hoa(req)
            result = apply_fire_type_policy(
                self.verifier.verify(frame_jpeg, crop_jpeg, req.context, req.severity,
                                     first_jpeg, timeout_s=timeout_s), req.context)
        except Exception as exc:  # noqa: BLE001 - mọi lỗi đều fail-open
            latency = time.perf_counter() - t0
            log.warning("VLM %s lỗi (%.1fs, timeout %.1fs): %s", self.verifier.name,
                        latency, timeout_s, f"{type(exc).__name__}: {exc}")
            return VerifyOutcome("UNVERIFIED", None, latency, 1,
                                 f"{type(exc).__name__}: {exc}", ma_loi(exc))
        latency = time.perf_counter() - t0
        log.info("VLM %s trả lời sau %.1fs (timeout %.1fs): fire=%s smoke=%s "
                 "conf=%.2f type=%s — %s", self.verifier.name, latency, timeout_s,
                 result.is_fire, result.is_smoke, result.confidence,
                 result.fire_type, result.description_vi)
        return VerifyOutcome(verification_from(result), result, latency, 1)

    def run_sync(self, req: VerifyRequest) -> VerifyOutcome:
        """Encode images, call the provider with retries, map the answer."""
        assert self.verifier is not None
        t0 = time.perf_counter()
        frame_jpeg, crop_jpeg, first_jpeg = self._ma_hoa(req)
        error: str | None = None
        reason: str | None = None
        attempts = 0
        for attempt in range(self.cfg.retries + 1):
            attempts = attempt + 1
            try:
                result = apply_fire_type_policy(
                    self.verifier.verify(frame_jpeg, crop_jpeg, req.context,
                                         req.severity, first_jpeg), req.context)
                latency = time.perf_counter() - t0
                log.info("VLM %s trả lời sau %.1fs (lần %d): fire=%s smoke=%s "
                         "conf=%.2f type=%s — %s", self.verifier.name, latency,
                         attempts, result.is_fire, result.is_smoke,
                         result.confidence, result.fire_type, result.description_vi)
                return VerifyOutcome(verification_from(result), result, latency,
                                     attempts)
            except Exception as exc:  # noqa: BLE001 - mọi lỗi đều fail-open
                error = f"{type(exc).__name__}: {exc}"
                reason = ma_loi(exc)
                log.warning("VLM %s lỗi lần %d/%d: %s", self.verifier.name, attempts,
                            self.cfg.retries + 1, error)
        latency = time.perf_counter() - t0
        log.warning("VLM thất bại sau %d lần (%.1fs): alert UNVERIFIED", attempts,
                    latency)
        return VerifyOutcome("UNVERIFIED", None, latency, attempts, error, reason)

    def drain(self, timeout_s: float | None = None) -> int:
        """Block until pending verifications finish; return how many remained."""
        with self._lock:
            pending = set(self._pending)
        if not pending:
            return 0
        log.info("chờ %d xác minh VLM còn dở (tối đa %.0fs)", len(pending),
                 timeout_s or -1)
        not_done = wait(pending, timeout=timeout_s).not_done
        return len(not_done)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
