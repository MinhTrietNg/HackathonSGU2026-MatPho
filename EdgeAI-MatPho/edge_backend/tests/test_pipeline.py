"""Media tests: real demux/decode/encode on generated clips.

The source is a file standing in for the RTSP input and outputs are files,
which exercises the whole RTSP -> H.264/HLS fan-out without a network.
"""

import threading
from dataclasses import replace

import pytest

from src import pipeline, sinks
from src.config import DecoderSettings, StreamSpec
from src.pipeline import SourceError, run_attempt
from src.stats import SessionState, SessionStats

from .media import (
    corrupt_packets,
    cut_head,
    make_source,
    mean_luma,
    probe,
    source_payloads,
)

# Enable AI branch in media tests to verify both Live (App HLS) and AI sub-stream branches
SETTINGS = DecoderSettings(ai_queue_size=10_000, enable_ai_branch=True)


@pytest.fixture(scope="module")
def clip_720p(tmp_path_factory):
    return make_source(tmp_path_factory.mktemp("src") / "h264_720p.mp4")


def run(tmp_path, source, settings=SETTINGS, stop=None):
    spec = StreamSpec(
        "cam_t", str(source), str(tmp_path / "app.mkv"), str(tmp_path / "ai.mkv")
    )
    stats = SessionStats()
    run_attempt(spec, settings, stats, stop or threading.Event())
    return spec, stats


class TestLiveBranchRemux:
    def test_app_stream_is_a_bit_exact_copy(self, clip_720p, tmp_path):
        spec, stats = run(tmp_path, clip_720p)
        app = probe(tmp_path / "app.mkv")
        assert app.codec == "h264" and (app.width, app.height) == (1280, 720)
        assert app.payloads == source_payloads(clip_720p)
        assert stats.live_mode == "copy"
        assert stats.live_packets_out == app.packets == 200

    def test_app_stream_decodes_to_all_frames(self, clip_720p, tmp_path):
        run(tmp_path, clip_720p)
        assert probe(tmp_path / "app.mkv").frames == 200

    def test_app_stream_has_original_keyframe_cadence(self, clip_720p, tmp_path):
        run(tmp_path, clip_720p)
        assert probe(tmp_path / "app.mkv").keyframes == 8


class TestAiBranch:
    def test_size_codec_and_rate(self, clip_720p, tmp_path):
        _, stats = run(tmp_path, clip_720p)
        ai = probe(tmp_path / "ai.mkv")
        assert ai.codec == "h264"
        assert (ai.width, ai.height) == (640, 360)
        assert ai.frames == pytest.approx(24, abs=2)
        assert stats.ai_frames_dropped == 0
        assert stats.ai_frames_encoded == ai.frames

    def test_frame_spacing_follows_source_clock(self, clip_720p, tmp_path):
        run(tmp_path, clip_720p)
        times = probe(tmp_path / "ai.mkv").times
        gaps = [b - a for a, b in zip(times, times[1:])]
        assert all(abs(g - 1 / 3) < 0.05 for g in gaps), gaps
        assert times[-1] - times[0] == pytest.approx(7.7, abs=0.5)

    def test_picture_content_survives(self, clip_720p, tmp_path):
        run(tmp_path, clip_720p)
        assert mean_luma(tmp_path / "ai.mkv") > 5.0

    def test_keyframe_every_second_for_fast_join(self, clip_720p, tmp_path):
        run(tmp_path, clip_720p)
        ai = probe(tmp_path / "ai.mkv")
        assert ai.keyframes >= ai.frames // 4

    def test_configurable_rate_and_size(self, clip_720p, tmp_path):
        settings = replace(SETTINGS, ai_fps=5.0, ai_max_edge=320)
        run(tmp_path, clip_720p, settings)
        ai = probe(tmp_path / "ai.mkv")
        assert (ai.width, ai.height) == (320, 180)
        assert ai.frames == pytest.approx(40, abs=3)

    def test_small_source_is_not_upscaled(self, tmp_path):
        small = make_source(tmp_path / "small.mp4", 320, 240, 25, 4)
        run(tmp_path, small)
        ai = probe(tmp_path / "ai.mkv")
        assert (ai.width, ai.height) == (320, 240)

    def test_low_rate_source_is_passed_at_its_own_rate(self, tmp_path):
        slow = make_source(tmp_path / "slow.mp4", 640, 360, 2, 6, gop=2)
        run(tmp_path, slow)
        assert probe(tmp_path / "ai.mkv").frames == pytest.approx(12, abs=1)


class TestHevcSource:
    def test_live_branch_transcodes_to_h264_at_source_size(self, tmp_path):
        hevc = make_source(
            tmp_path / "hevc.mp4", 640, 360, 25, 3, codec="libx265"
        )
        _, stats = run(tmp_path, hevc)
        app = probe(tmp_path / "app.mkv")
        assert stats.live_mode == "transcode"
        assert app.codec == "h264"
        assert (app.width, app.height) == (640, 360)
        assert app.frames == pytest.approx(75, abs=2)
        ai = probe(tmp_path / "ai.mkv")
        assert ai.codec == "h264" and ai.frames == pytest.approx(9, abs=2)


class TestRobustness:
    def test_corrupt_packets_do_not_disturb_the_live_branch(self, tmp_path):
        clean = make_source(tmp_path / "clean.mp4")
        bad = corrupt_packets(clean, tmp_path / "bad.mp4", {60, 61, 62})
        _, stats = run(tmp_path, bad)
        assert stats.packets_in == 200
        assert stats.live_packets_out == 200
        ai = probe(tmp_path / "ai.mkv")
        assert ai.frames >= 20

    def _spec_with_broken_ai(self, clip, tmp_path):
        return StreamSpec(
            "cam_t",
            str(clip),
            str(tmp_path / "app.mkv"),
            str(tmp_path / "missing_dir" / "ai.mkv"),
        )

    def test_ai_branch_failure_does_not_stop_the_live_branch(
        self, clip_720p, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(pipeline, "AI_RESTART_INTERVAL_S", 0.0)
        stats = SessionStats()
        run_attempt(
            self._spec_with_broken_ai(clip_720p, tmp_path),
            SETTINGS, stats, threading.Event(),
        )
        assert probe(tmp_path / "app.mkv").payloads == source_payloads(clip_720p)
        assert stats.ai_frames_encoded == 0
        assert stats.ai_restarts >= 1

    def test_failed_ai_branch_is_not_rebuilt_before_the_interval(
        self, clip_720p, tmp_path
    ):
        stats = SessionStats()
        run_attempt(
            self._spec_with_broken_ai(clip_720p, tmp_path),
            SETTINGS, stats, threading.Event(),
        )
        assert stats.ai_restarts == 0
        assert probe(tmp_path / "app.mkv").frames == 200

    def test_waiting_for_a_key_frame_is_visible(
        self, tmp_path, monkeypatch, caplog
    ):
        full = make_source(tmp_path / "full.mp4", 640, 360, 25, 6, gop=250)
        joined = cut_head(full, tmp_path / "joined.mp4", skip=30)
        monkeypatch.setattr(pipeline, "KEYFRAME_WARN_S", 0.0)
        with caplog.at_level("WARNING", logger="stream-worker.pipeline"):
            _, stats = run(tmp_path, joined)
        assert stats.awaiting_keyframe is True
        assert stats.snapshot()["awaiting_keyframe"] is True
        assert "no key frame" in caplog.text
        assert stats.live_packets_out == 0 and stats.last_error is None

    def test_key_frame_wait_clears_once_a_key_frame_arrives(
        self, clip_720p, tmp_path
    ):
        _, stats = run(tmp_path, clip_720p)
        assert stats.awaiting_keyframe is False

    def test_live_branch_discarding_everything_is_an_error(
        self, clip_720p, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(sinks.CopySink, "write", lambda self, packet: False)
        with pytest.raises(SourceError, match="none forwarded"):
            run(tmp_path, clip_720p)

    def test_live_output_is_released_if_setup_fails_half_way(
        self, clip_720p, tmp_path, monkeypatch
    ):
        class SpyLive:
            mode = "copy"
            closed = False

            def close(self):
                type(self).closed = True

        def boom(*args, **kwargs):
            raise RuntimeError("cannot build AI branch")

        monkeypatch.setattr(pipeline, "make_live_branch", lambda *a, **k: SpyLive())
        monkeypatch.setattr(pipeline, "AiBranch", boom)
        with pytest.raises(RuntimeError, match="cannot build"):
            run(tmp_path, clip_720p)
        assert SpyLive.closed is True

    def test_returns_immediately_when_stop_is_set(self, clip_720p, tmp_path):
        stop = threading.Event()
        stop.set()
        _, stats = run(tmp_path, clip_720p, stop=stop)
        assert stats.packets_in == 0

    def test_stop_mid_stream_ends_cleanly_with_decodable_output(
        self, tmp_path
    ):
        long_clip = make_source(tmp_path / "long.mp4", 640, 360, 25, 30)
        stop = threading.Event()
        spec = StreamSpec(
            "cam_t", str(long_clip), str(tmp_path / "app.mkv"),
            str(tmp_path / "ai.mkv"),
        )
        stats = SessionStats()
        worker = threading.Thread(
            target=run_attempt, args=(spec, SETTINGS, stats, stop)
        )
        worker.start()
        while stats.packets_in < 100 and worker.is_alive():
            pass
        stop.set()
        worker.join(10)
        assert not worker.is_alive()
        assert 100 <= stats.packets_in < 750
        assert probe(tmp_path / "app.mkv").frames > 50

    def test_missing_source_raises(self, tmp_path):
        with pytest.raises(OSError):
            run(tmp_path, tmp_path / "does_not_exist.mp4")

    def test_libav_interrupt_is_reported_as_a_timeout(self, tmp_path, monkeypatch):
        import av

        from src import pipeline

        def fake_run(*args):
            raise av.error.ExitError(1414092869, "Immediate exit requested")

        monkeypatch.setattr(pipeline, "_run", fake_run)
        with pytest.raises(TimeoutError, match="no data from source"):
            run(tmp_path, tmp_path / "unused.mp4")

    def test_source_without_video_is_rejected(self, tmp_path):
        import av

        audio_only = tmp_path / "a.wav"
        out = av.open(str(audio_only), "w")
        out.add_stream("pcm_s16le", rate=8000, layout="mono")
        out.close()
        with pytest.raises((SourceError, OSError, ValueError)):
            run(tmp_path, audio_only)


def test_state_is_running_after_connect(clip_720p, tmp_path):
    _, stats = run(tmp_path, clip_720p)
    assert stats.state is SessionState.RUNNING
    assert stats.source.codec == "h264"
    assert stats.frames_decoded >= 198
