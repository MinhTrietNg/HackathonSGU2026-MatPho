import re
import os

doc_path = "backend/API_DOCUMENTATION_COMPLETE.md"
with open(doc_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

endpoints_in_doc = []
current_sec = ""

for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("### ") or stripped.startswith("## "):
        current_sec = stripped
    
    # Match patterns like:
    # - `POST /api/v1/auth/register-otp`
    # - **Endpoint**: `GET /api/v1/cameras`
    # - `WS /api/v1/ws`
    # - `GET /health`
    matches = re.findall(r'`?(GET|POST|PUT|PATCH|DELETE|WS|WEBSOCKET)\s+([/][a-zA-Z0-9_\-\/{}]*)`?', line, re.IGNORECASE)
    for verb, path in matches:
        verb = verb.upper()
        if verb == "WEBSOCKET":
            verb = "WS"
        # filter out generic placeholders or markdown anomalies
        if path.startswith("/api/") or path in ["/health", "/health/detailed", "/health/error-test"]:
            endpoints_in_doc.append((verb, path, current_sec, i + 1))

# Unique endpoints preserving order
seen = set()
unique_endpoints = []
for ep in endpoints_in_doc:
    key = (ep[0], ep[1])
    if key not in seen:
        seen.add(key)
        unique_endpoints.append(ep)

print(f"Total unique endpoints extracted from doc: {len(unique_endpoints)}")
for verb, path, sec, lineno in unique_endpoints:
    print(f"{verb:<7} {path:<50} | Line {lineno:<4} | {sec}")
