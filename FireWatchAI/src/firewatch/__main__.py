"""Command line entry point: ``python -m firewatch run|serve``."""

from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .config import load_config


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="firewatch",
                                description="FireWatch v3 — phát hiện cháy/khói xe")
    p.add_argument("--version", action="version", version=f"firewatch {__version__}")
    p.add_argument("--config", default=None,
                   help="đường dẫn config.yaml (mặc định: tìm từ thư mục hiện tại)")
    p.add_argument("-v", "--verbose", action="store_true", help="log DEBUG")
    p.add_argument("--set", dest="overrides", action="append", default=[],
                   metavar="SECTION.KEY=VALUE",
                   help="ghi đè config tại chỗ, ví dụ --set voting.k_enter=3 "
                        "(dùng nhiều lần được)")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="chạy pipeline trên một nguồn video")
    run.add_argument("--source", required=True,
                     help="file video | 0 (webcam) | rtsp://...")
    run.add_argument("--realtime", action="store_true",
                     help="file: phát lại đúng tốc độ thật khi demo")
    run.add_argument("--show", action="store_true", help="mở cửa sổ xem trực tiếp")
    run.add_argument("--weights", default=None, help="ghi đè detector.weights")
    run.add_argument("--max-heartbeats", type=int, default=None,
                     help="dừng sau N heartbeat (chạy thử nhanh)")

    serve = sub.add_parser("serve", help="API FastAPI + WebSocket; --source để chạy "
                                         "pipeline nền và đẩy event realtime")
    serve.add_argument("--source", default=None,
                       help="tuỳ chọn: file video | 0 | rtsp:// chạy song song")
    serve.add_argument("--realtime", action="store_true",
                       help="file: phát lại đúng tốc độ thật (nên bật khi demo)")
    serve.add_argument("--host", default=None, help="ghi đè server.host")
    serve.add_argument("--port", type=int, default=None, help="ghi đè server.port")
    serve.add_argument("--exit-on-pipeline-stop", action="store_true",
                       help="pipeline lỗi hay nguồn live kết thúc thì dừng serve với "
                            "mã 1, để supervisor khởi động lại (dùng trong container)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S",
    )
    cfg = load_config(args.config, overrides=args.overrides)
    if args.overrides:
        logging.getLogger(__name__).info("ghi đè config: %s", args.overrides)
    if args.cmd == "run":
        from .pipeline import Pipeline

        summary = Pipeline(cfg, args.source, realtime=args.realtime or None,
                           show=args.show or None, max_heartbeats=args.max_heartbeats,
                           weights=args.weights).run()
        return 1 if summary.live_source_lost else 0
    if args.cmd == "serve":
        from .server import serve

        return serve(cfg, source=args.source, realtime=args.realtime,
                     host=args.host, port=args.port,
                     exit_on_pipeline_stop=args.exit_on_pipeline_stop)
    return 1


if __name__ == "__main__":
    sys.exit(main())
