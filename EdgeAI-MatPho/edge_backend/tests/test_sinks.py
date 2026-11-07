from src.config import DecoderSettings
from src.sinks import H264Sink


def test_x264_threads_follow_the_setting(tmp_path):
    sink = H264Sink(
        str(tmp_path / "o.mkv"), 640, 360, 3.0, 26, DecoderSettings(encode_threads=1)
    )
    assert sink._stream.options["threads"] == "1"
    sink.close()


def test_default_does_not_let_x264_spawn_a_thread_per_core(tmp_path):
    sink = H264Sink(str(tmp_path / "o.mkv"), 640, 360, 3.0, 26, DecoderSettings())
    assert sink._stream.options["threads"] == "2"
    sink.close()
