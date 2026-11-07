"""Tier 4: provider mapping, retry/fail-open, Gemini parsing with a fake transport."""

import json
import threading
import time

import cv2
import numpy as np
import pytest

from firewatch.alerts import VLMResult
from firewatch.config import VLMConfig
from firewatch.vlm import (GeminiHTTPError, GeminiVerifier, MockVerifier,
                           VerificationService, VerifyRequest, build_verifier,
                           crop_with_padding, verification_from)

IMG = np.full((240, 320, 3), 90, dtype=np.uint8)
REQ = VerifyRequest(frame=IMG, box=(50.0, 60.0, 150.0, 160.0), context="HAM",
                    severity="CRITICAL", video_ts=5.0)


def vcfg(**kw):
    base = dict(provider="mock", timeout_s=2, retries=1, mock_delay_s=0.0)
    base.update(kw)
    return VLMConfig(**base)


def test_verification_mapping():
    assert verification_from(None) == "UNVERIFIED"
    yes = VLMResult(is_fire=True, is_smoke=False, confidence=0.8, description_vi="x")
    smoke = VLMResult(is_fire=False, is_smoke=True, confidence=0.6, description_vi="x")
    no = VLMResult(is_fire=False, is_smoke=False, confidence=0.9, description_vi="x")
    assert verification_from(yes) == "VERIFIED"
    assert verification_from(smoke) == "VERIFIED"
    assert verification_from(no) == "SUPPRESSED"


def test_mock_waits_and_returns_configured_answer():
    m = MockVerifier(delay_s=0.2, is_fire=False, is_smoke=True, confidence=0.7)
    t0 = time.perf_counter()
    r = m.verify(b"", b"", "TRET", "WARNING")
    assert time.perf_counter() - t0 >= 0.2
    assert (r.is_fire, r.is_smoke, r.confidence) == (False, True, 0.7)
    assert "mock" in r.description_vi


def test_service_verified_and_suppressed_via_mock():
    done = []
    svc = VerificationService(vcfg(), build_verifier(vcfg()))
    svc.submit(REQ, done.append)
    assert svc.drain(timeout_s=5) == 0
    assert done[0].verification == "VERIFIED" and done[0].attempts == 1
    assert done[0].result.is_fire is True

    cfg2 = vcfg(mock_is_fire=False, mock_is_smoke=False)
    svc2 = VerificationService(cfg2, build_verifier(cfg2))
    done2 = []
    svc2.submit(REQ, done2.append)
    svc2.drain(timeout_s=5)
    assert done2[0].verification == "SUPPRESSED" and done2[0].result is not None


def test_disabled_or_missing_key_gives_unverified_immediately(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert build_verifier(vcfg(enabled=False)) is None
    assert build_verifier(vcfg(provider="gemini")) is None
    svc = VerificationService(vcfg(enabled=False), None)
    done = []
    fut = svc.submit(REQ, done.append)
    assert fut.done() and fut.result().verification == "UNVERIFIED"
    assert done[0].verification == "UNVERIFIED" and done[0].result is None


class _Flaky(MockVerifier):
    """Fails ``fail_times`` calls, then answers."""

    def __init__(self, fail_times):
        super().__init__(delay_s=0.0)
        self.fail_times, self.calls = fail_times, 0

    def verify(self, *a, **k):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TimeoutError("giả lập timeout")
        return super().verify(*a, **k)


def test_retry_then_success_and_fail_open():
    flaky = _Flaky(fail_times=1)
    out = VerificationService(vcfg(retries=1), flaky).run_sync(REQ)
    assert out.verification == "VERIFIED" and out.attempts == 2 and flaky.calls == 2

    dead = _Flaky(fail_times=99)
    out2 = VerificationService(vcfg(retries=1), dead).run_sync(REQ)
    assert out2.verification == "UNVERIFIED" and out2.attempts == 2
    assert out2.result is None and "TimeoutError" in out2.error


def test_service_does_not_block_caller():
    slow = vcfg(mock_delay_s=0.5)
    svc = VerificationService(slow, build_verifier(slow))
    t0 = time.perf_counter()
    fut = svc.submit(REQ, lambda o: None)
    assert time.perf_counter() - t0 < 0.1  # submit trả về ngay
    assert fut is not None and svc.drain(timeout_s=5) == 0
    assert threading.current_thread() is threading.main_thread()


def test_crop_with_padding_clips_to_image():
    crop = crop_with_padding(IMG, (0.0, 0.0, 100.0, 100.0), 0.25)
    assert crop.shape[:2] == (125, 125)
    crop2 = crop_with_padding(IMG, (300.0, 220.0, 320.0, 240.0), 1.0)
    assert crop2.shape[0] <= 40 and crop2.shape[1] <= 40


def test_gemini_request_and_parse_with_fake_transport():
    seen = {}

    class FakeGemini(GeminiVerifier):
        def _post(self, body):
            seen["body"] = body
            answer = {"is_fire": True, "is_smoke": False, "confidence": 1.7,
                      "description_vi": "Lửa bốc lên từ yên xe máy."}
            part = {"text": json.dumps(answer)}
            return {"candidates": [{"content": {"parts": [part]}}]}

    g = FakeGemini("gemini-2.5-flash", "k", timeout_s=5)
    r = g.verify(b"\xff\xd8frame", b"\xff\xd8crop", "NGOAI", "CRITICAL")
    assert r.is_fire and not r.is_smoke and r.confidence == 1.0
    parts = seen["body"]["contents"][0]["parts"]
    assert len(parts) == 3 and "sân để xe" in parts[0]["text"]
    assert parts[1]["inline_data"]["mime_type"] == "image/jpeg"
    gen = seen["body"]["generationConfig"]
    assert gen["response_mime_type"] == "application/json"
    assert set(gen["response_schema"]["required"]) == {   # NGOAI: hỏi thêm fire_type
        "is_fire", "is_smoke", "confidence", "description_vi", "fire_type"}
    assert g.url.endswith("/models/gemini-2.5-flash:generateContent")


def _answer(thoughts=0):
    part = {"text": json.dumps({"is_fire": True, "is_smoke": True, "confidence": 0.8,
                                "description_vi": "Xe máy bốc cháy."})}
    return {"candidates": [{"content": {"parts": [part]}}],
            "usageMetadata": {"candidatesTokenCount": 30,
                              "thoughtsTokenCount": thoughts}}


class _Recorder(GeminiVerifier):
    """Fake transport: records request bodies, replays scripted replies."""

    def __init__(self, replies, **kw):
        super().__init__("gemini-x-flash-lite", "k", timeout_s=5, **kw)
        self.replies, self.bodies = list(replies), []

    def _post(self, body):
        self.bodies.append(body)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_gemini_sends_thinking_off_and_output_cap():
    g = _Recorder([_answer()], thinking_budget=0, max_output_tokens=200)
    g.verify(b"f", b"c", "HAM", "CRITICAL")
    gen = g.bodies[0]["generationConfig"]
    assert gen["thinkingConfig"] == {"thinkingBudget": 0}
    assert gen["maxOutputTokens"] == 200
    assert "đúng 1 câu" in g.bodies[0]["contents"][0]["parts"][0]["text"]
    none = _Recorder([_answer()], thinking_budget=None)
    none.verify(b"f", b"c", "HAM", "CRITICAL")
    assert "thinkingConfig" not in none.bodies[0]["generationConfig"]


def test_gemini_falls_back_when_thinking_config_rejected(caplog):
    # gemini-3.5-flash-lite trả đúng thông điệp này cho thinkingBudget (đo 03/11)
    rejected = GeminiHTTPError(400, '{"error": {"code": 400, "message": "Request '
                                    'contains an invalid argument."}}')
    g = _Recorder([rejected, _answer(), _answer()], thinking_budget=0)
    with caplog.at_level("WARNING", logger="firewatch.vlm"):
        r = g.verify(b"f", b"c", "TRET", "WARNING")
    assert r.is_fire and len(g.bodies) == 2
    assert g.bodies[0]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert "thinkingConfig" not in g.bodies[1]["generationConfig"]
    assert "gửi lại" in caplog.text
    g.verify(b"f", b"c", "TRET", "WARNING")            # lần sau không gửi nữa
    assert "thinkingConfig" not in g.bodies[2]["generationConfig"]
    bad = GeminiHTTPError(400, "bad image")
    other = _Recorder([bad, bad, _answer()], thinking_budget=0)
    with pytest.raises(GeminiHTTPError):                # 400 không do thinkingConfig
        other.verify(b"f", b"c", "TRET", "WARNING")
    other.verify(b"f", b"c", "TRET", "WARNING")         # nên vẫn giữ thinkingConfig
    assert "thinkingConfig" in other.bodies[2]["generationConfig"]


def test_gemini_thinking_level_wins_over_budget():
    g = _Recorder([_answer()], thinking_budget=0, thinking_level="minimal")
    g.verify(b"f", b"c", "HAM", "CRITICAL")
    assert g.bodies[0]["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "minimal"}


def test_gemini_logs_latency_and_warns_on_thoughts(caplog):
    g = _Recorder([_answer(thoughts=0), _answer(thoughts=57)], thinking_budget=0)
    with caplog.at_level("INFO", logger="firewatch.vlm"):
        g.verify(b"f", b"c", "NGOAI", "CRITICAL")
        assert "thoughtsTokenCount=0" in caplog.text and " ms" in caplog.text
        assert not [r for r in caplog.records if r.levelname == "WARNING"]
        g.verify(b"f", b"c", "NGOAI", "CRITICAL")
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warns and "57 token suy nghĩ" in warns[0].getMessage()


def test_service_sends_images_at_640_px():
    seen = []

    class Spy(MockVerifier):
        def verify(self, frame_jpeg, crop_jpeg, context, severity, first_jpeg=None):
            seen.append((frame_jpeg, crop_jpeg))
            return super().verify(frame_jpeg, crop_jpeg, context, severity)

    big = np.random.default_rng(0).integers(0, 255, (1080, 1920, 3), dtype=np.uint8)
    req = VerifyRequest(frame=big, box=(100.0, 100.0, 1500.0, 900.0),
                        context="NGOAI", severity="CRITICAL", video_ts=1.0)
    VerificationService(vcfg(), Spy(delay_s=0.0)).run_sync(req)
    for jpg in seen[0]:
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        assert max(img.shape[:2]) == 640


def test_fire_type_asked_only_outdoors():
    g = _Recorder([_answer(), _answer()])
    g.verify(b"f", b"c", "NGOAI", "CRITICAL", first_jpeg=b"first")
    g.verify(b"f", b"c", "HAM", "CRITICAL", first_jpeg=b"first")
    out, ham = g.bodies
    assert "fire_type" in out["generationConfig"]["response_schema"]["required"]
    assert "lò than" in out["contents"][0]["parts"][0]["text"]
    assert len(out["contents"][0]["parts"]) == 4    # prompt, khung đầu, khung, crop
    assert "fire_type" not in ham["generationConfig"]["response_schema"]["properties"]
    assert "fire_type" not in ham["contents"][0]["parts"][0]["text"]


def test_fire_type_policy_never_changes_verification():
    from firewatch.vlm import apply_fire_type_policy
    fire = VLMResult(is_fire=True, is_smoke=False, confidence=0.7,
                     description_vi="Lửa trong lò than trước nhà.",
                     fire_type="CONTROLLED")
    out = apply_fire_type_policy(fire, "NGOAI")
    assert out.fire_type == "CONTROLLED" and verification_from(out) == "VERIFIED"
    assert "kiểm soát" in out.description_vi             # người trực thấy lý do
    indoor = apply_fire_type_policy(fire, "TRET")
    assert indoor.fire_type == "UNCONTROLLED"             # trong nhà luôn là sự cố
    assert verification_from(indoor) == "VERIFIED"
    missing = apply_fire_type_policy(fire.model_copy(update={"fire_type": None}),
                                     "NGOAI")
    assert missing.fire_type == "UNKNOWN"


def test_service_sends_first_frame_and_applies_policy():
    seen = {}

    class Spy(MockVerifier):
        def verify(self, frame_jpeg, crop_jpeg, context, severity, first_jpeg=None):
            seen["first"] = first_jpeg
            return super().verify(frame_jpeg, crop_jpeg, context, severity,
                                  first_jpeg)

    req = VerifyRequest(frame=IMG, box=(50.0, 60.0, 150.0, 160.0), context="NGOAI",
                        severity="CRITICAL", video_ts=5.0, first_frame=IMG)
    cfg = vcfg(mock_fire_type="CONTROLLED")
    out = VerificationService(cfg, Spy(delay_s=0.0, fire_type="CONTROLLED")
                              ).run_sync(req)
    assert seen["first"] is not None
    assert out.verification == "VERIFIED" and out.result.fire_type == "CONTROLLED"
    ham = VerificationService(cfg, build_verifier(cfg)).run_sync(REQ)   # context HAM
    assert ham.result.fire_type == "UNCONTROLLED"


def test_gemini_parse_rejects_blocked_or_malformed():
    with pytest.raises(ValueError):
        GeminiVerifier.parse({"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(ValueError):
        GeminiVerifier.parse({"candidates": [{"content": {"parts": [
            {"text": "không phải json"}]}}]})
