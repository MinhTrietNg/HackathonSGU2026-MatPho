import pytest

from src.config import (
    ConfigError,
    DecoderSettings,
    StreamSpec,
    redact_text,
    redact_url,
    validate_cam_id,
)


class TestCamId:
    @pytest.mark.parametrize("cam_id", ["cam_001", "A-b_9", "x" * 64])
    def test_valid(self, cam_id):
        assert validate_cam_id(cam_id) == cam_id

    @pytest.mark.parametrize(
        "cam_id", ["", "cam/001", "../x", "cam 1", "cam?x=1", "x" * 65, "cám"]
    )
    def test_invalid(self, cam_id):
        with pytest.raises(ConfigError):
            validate_cam_id(cam_id)


class TestRedactUrl:
    def test_masks_password_keeps_rest(self):
        url = "rtsp://admin:s3cret@192.168.1.10:554/live/ch1?x=1"
        out = redact_url(url)
        assert "s3cret" not in out
        assert out == "rtsp://admin:***@192.168.1.10:554/live/ch1?x=1"

    def test_no_credentials_untouched(self):
        url = "rtsp://mediamtx:8554/live/cam_001"
        assert redact_url(url) == url

    def test_user_without_password_untouched(self):
        url = "rtsp://admin@host/live"
        assert redact_url(url) == url

    def test_ipv6_host(self):
        out = redact_url("rtsp://u:p@[::1]:8554/x")
        assert out == "rtsp://u:***@[::1]:8554/x"


class TestRedactText:
    def test_masks_every_url_in_text(self):
        text = "open 'rtsp://a:p1@h1/x' then rtsps://b:p2@h2:322/y failed"
        out = redact_text(text)
        assert "p1" not in out and "p2" not in out
        assert "rtsp://a:***@h1/x" in out and "rtsps://b:***@h2:322/y" in out

    def test_masks_reencoded_or_truncated_urls(self):
        out = redact_text("error for rtsp://admin:p%40ss@10.0.0.5:554/Streaming")
        assert "p%40ss" not in out

    def test_password_containing_raw_at_sign(self):
        out = redact_text("failed rtsp://u:p@ss@10.0.0.5:554/x")
        assert "p@ss" not in out and "ss@" not in out
        assert out == "failed rtsp://u:***@10.0.0.5:554/x"

    def test_leaves_credential_free_text_alone(self):
        text = "rtsp://mediamtx:8554/live/cam_001: connection refused"
        assert redact_text(text) == text


class TestSettings:
    def test_defaults_are_valid(self):
        s = DecoderSettings()
        assert (s.ai_fps, s.ai_max_edge, s.rtsp_transport) == (3.0, 640, "tcp")
        assert s.app_path_template == "live/{cam_id}"
        assert s.source_path_template == "source/{cam_id}"
        assert s.ai_path_template == "ai/{cam_id}"
        assert s.enable_ai_branch is False

    def test_from_env_overrides_and_reuses_existing_keys(self):
        s = DecoderSettings.from_env(
            {
                "MEDIAMTX_RTSP_URL": "rtsp://edge:8554/",
                "SUBSTREAM_TARGET_FPS": "5",
                "SUBSTREAM_MAX_EDGE": "960",
                "RTSP_TRANSPORT": "UDP",
                "DECODE_THREADS": "0",
                "ENABLE_AI_BRANCH": "true",
            }
        )
        assert s.mediamtx_rtsp_url == "rtsp://edge:8554"
        assert (s.ai_fps, s.ai_max_edge, s.rtsp_transport) == (5.0, 960, "udp")
        assert s.decode_threads == 0
        assert s.enable_ai_branch is True

    def test_from_env_empty_uses_defaults(self):
        assert DecoderSettings.from_env({}) == DecoderSettings()

    def test_from_env_rejects_garbage(self):
        with pytest.raises(ConfigError, match="SUBSTREAM_TARGET_FPS"):
            DecoderSettings.from_env({"SUBSTREAM_TARGET_FPS": "fast"})

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"mediamtx_rtsp_url": "http://x"},
            {"app_path_template": "live/fixed"},
            {"ai_path_template": "live/{cam_id}"},  # equals app_path_template
            {"source_path_template": "live/{cam_id}"},  # equals app_path_template
            {"rtsp_transport": "sctp"},
            {"ai_fps": 0},
            {"ai_fps": 31},
            {"ai_max_edge": 32},
            {"ai_crf": 52},
            {"ai_queue_size": 0},
            {"decode_threads": -1},
            {"read_timeout_s": 0},
            {"backoff_initial_s": 10, "backoff_max_s": 1},
        ],
    )
    def test_validation(self, kwargs):
        with pytest.raises(ConfigError):
            DecoderSettings(**kwargs)


class TestSecretsAndNormalisation:
    def test_spec_repr_does_not_expose_the_camera_password(self):
        spec = StreamSpec.for_camera(
            "cam_1", DecoderSettings(), "rtsp://admin:s3cret@10.0.0.5/live"
        )
        assert "s3cret" not in repr(spec) and "s3cret" not in str(spec)
        assert spec.source_url == "rtsp://admin:s3cret@10.0.0.5/live"

    def test_trailing_slash_of_the_base_url_is_ignored(self):
        s = DecoderSettings(mediamtx_rtsp_url="rtsp://h:8554/")
        assert s.url_for("live/{cam_id}", "c") == "rtsp://h:8554/live/c"

    def test_stop_timeout_covers_connect_read_and_teardown(self):
        s = DecoderSettings(open_timeout_s=10, read_timeout_s=5)
        assert s.stop_timeout_s >= 10 + 5

    def test_encode_threads_validated_and_read_from_env(self):
        assert DecoderSettings.from_env({"ENCODE_THREADS": "1"}).encode_threads == 1
        with pytest.raises(ConfigError):
            DecoderSettings(encode_threads=-1)


class TestStreamSpec:
    def test_derives_all_urls_for_hls_and_ai(self):
        spec = StreamSpec.for_camera("cam_001", DecoderSettings())
        assert spec.source_url == "rtsp://mediamtx:8554/source/cam_001"
        assert spec.app_url == "rtsp://mediamtx:8554/live/cam_001"
        assert spec.ai_url == "rtsp://mediamtx:8554/ai/cam_001"

    def test_explicit_source_url(self):
        spec = StreamSpec.for_camera(
            "cam_001", DecoderSettings(), "rtsp://192.168.1.50:554/path"
        )
        assert spec.source_url == "rtsp://192.168.1.50:554/path"
        assert spec.app_url == "rtsp://mediamtx:8554/live/cam_001"

    def test_rejects_non_rtsp_source(self):
        with pytest.raises(ConfigError):
            StreamSpec.for_camera("cam_001", DecoderSettings(), "http://x/y")

    def test_rejects_loop_onto_own_output(self):
        s = DecoderSettings()
        with pytest.raises(ConfigError, match="loop"):
            StreamSpec.for_camera("cam_001", s, "rtsp://mediamtx:8554/live/cam_001")

    def test_rejects_bad_cam_id(self):
        with pytest.raises(ConfigError):
            StreamSpec.for_camera("../etc", DecoderSettings())
