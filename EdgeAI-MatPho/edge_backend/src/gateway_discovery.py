"""
Gateway & Public Stream Discovery for Edge Node
Discovers the public HTTPS / WebRTC base URLs for MediaMTX when running behind
Edge HTTPS Gateway (Cloudflare Tunnel, Custom Domain, or LAN Fallback).
"""

from __future__ import annotations

import os
import re
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger("edge.gateway_discovery")

_TRYCLOUDFLARE_REGEX = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def extract_tunnel_url_from_text(text: str) -> Optional[str]:
    """Find the latest https://*.trycloudflare.com in text or logs."""
    if not text:
        return None
    matches = _TRYCLOUDFLARE_REGEX.findall(text)
    if matches:
        return matches[-1]  # Return the latest tunnel url in the log
    return None


def extract_tunnel_url_from_file(log_path: str | Path) -> Optional[str]:
    """Read a logfile and search for quick tunnel URL."""
    p = Path(log_path)
    if not p.is_file():
        return None
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        return extract_tunnel_url_from_text(content)
    except Exception as exc:
        logger.debug("Failed to read tunnel log file %s: %s", log_path, exc)
        return None


def discover_public_hls_url(
    fallback_url: str = "http://localhost:8888",
    candidate_log_paths: Optional[List[str]] = None,
) -> str:
    """
    Resolve the best public HLS base URL:
    1. Direct override: EDGE_PUBLIC_HLS_URL env var
    2. Cloudflare tunnel log file (in /app/data/tunnel.log, ./data/tunnel.log, tunnel.log)
    3. Fallback: fallback_url (e.g. MEDIAMTX_HLS_URL or http://localhost:8888)
    """
    # 1. Direct env override
    env_override = os.getenv("EDGE_PUBLIC_HLS_URL", "").strip().rstrip("/")
    if env_override:
        return env_override

    # 2. Check candidate log paths
    default_paths = [
        os.getenv("TUNNEL_LOG_PATH", ""),
        "/app/data/tunnel.log",
        "./data/tunnel.log",
        "tunnel.log",
        "../tunnel.log",
    ]
    paths_to_check = candidate_log_paths if candidate_log_paths is not None else default_paths
    for candidate in paths_to_check:
        if not candidate:
            continue
        found = extract_tunnel_url_from_file(candidate)
        if found:
            return found.rstrip("/")

    # 3. Fallback to provided fallback_url or env MEDIAMTX_HLS_URL
    clean_fallback = (fallback_url or os.getenv("MEDIAMTX_HLS_URL", "http://localhost:8888")).strip().rstrip("/")
    return clean_fallback
