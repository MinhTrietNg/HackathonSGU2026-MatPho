"""Xuất ``docs/mau_event.json`` từ payload webhook của một lần chạy thật.

Dựng một máy nhận webhook trên localhost, chạy pipeline trên ``--source`` với
VLM giả (``vlm.provider=mock``, không gọi mạng) và ``webhook.gui_anh`` bật, rồi
ghi payload ``created`` đầu tiên nhận được. Ảnh được nén dưới
``--anh-kb`` KB để file mẫu nhỏ; ngoài cỡ ảnh, payload đúng như backend nhận.

Chạy trong thư mục ``FireWatchAI/``::

    python tools/xuat_mau_event.py --source <clip có lửa>.mp4

Event và thư mục chạy được ghi vào ``events/_mau`` và ``runs/_mau`` (đã
gitignore) rồi xoá sau khi xong.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from firewatch.config import load_config
from firewatch.pipeline import Pipeline

GOC = Path(__file__).resolve().parents[1]


class _Nhan(BaseHTTPRequestHandler):
    """Máy nhận webhook giả: giữ body của mỗi POST."""

    payload: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802 - tên do http.server quy định
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        _Nhan.payload.append(json.loads(body))
        self.send_response(202)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        """Không in log truy cập."""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True, help="clip có lửa")
    ap.add_argument("--anh-kb", type=int, default=10,
                    help="cỡ tối đa của snapshot_base64 trong file mẫu (KB)")
    ap.add_argument("--out", default=str(GOC / "docs" / "mau_event.json"))
    args = ap.parse_args()

    server = HTTPServer(("127.0.0.1", 0), _Nhan)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ["FIREWATCH_MAU_URL"] = f"http://127.0.0.1:{server.server_port}/hook"
    os.environ["FIREWATCH_MAU_TOKEN"] = "token-mau"
    cfg = load_config(GOC / "config.yaml", overrides=[
        "vlm.provider=mock", "webhook.gui_anh=true",
        f"webhook.anh_toi_da_kb={args.anh_kb}",
        "alerts.webhook_url_env=FIREWATCH_MAU_URL",
        "alerts.webhook_token_env=FIREWATCH_MAU_TOKEN",
        "alerts.events_dir=events/_mau", "output.dir=runs/_mau",
        "output.save_frames=false"])
    try:
        Pipeline(cfg, args.source).run()
        server.shutdown()
    finally:
        for d in (GOC / "events" / "_mau", GOC / "runs" / "_mau"):
            shutil.rmtree(d, ignore_errors=True)
    tao = [p for p in _Nhan.payload if p.get("type") == "created"]
    if not tao:
        print("không nhận được event created nào: clip có lửa không?")
        return 1
    Path(args.out).write_text(json.dumps(tao[0], ensure_ascii=False, indent=2)
                              + "\n", encoding="utf-8", newline="\n")
    print(f"ghi {args.out}: {len(_Nhan.payload)} payload nhận, lấy created đầu")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
