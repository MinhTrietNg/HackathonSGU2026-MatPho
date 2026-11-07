import sys
import os
import re

if "/app" not in sys.path:
    sys.path.insert(0, "/app")

from src.main import app

openapi = app.openapi()
paths = openapi.get("paths", {})
print(f"Total paths in OpenAPI schema: {len(paths)}")

fastapi_endpoints = []
for path, methods in sorted(paths.items()):
    for method, details in methods.items():
        summary = details.get("summary") or details.get("operationId") or ""
        fastapi_endpoints.append({
            "verb": method.upper(),
            "path": path,
            "summary": summary
        })

print(f"Total method-path endpoints in FastAPI: {len(fastapi_endpoints)}")

# Also add WebSockets from app.routes
for r in app.routes:
    if hasattr(r, "path") and r.path and not getattr(r, "methods", None):
        fastapi_endpoints.append({
            "verb": "WS",
            "path": r.path,
            "summary": "WebSocket Endpoint"
        })

# Read API Documentation
doc_path = "/tmp/API_DOCUMENTATION_COMPLETE.md"
if not os.path.exists(doc_path):
    # Try looking in other locations
    alt_paths = ["/app/API_DOCUMENTATION_COMPLETE.md", "backend/API_DOCUMENTATION_COMPLETE.md"]
    for p in alt_paths:
        if os.path.exists(p):
            doc_path = p
            break

with open(doc_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

doc_endpoints = []
current_sec = ""
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("### ") or stripped.startswith("## "):
        current_sec = stripped
    
    matches = re.findall(r'`?(GET|POST|PUT|PATCH|DELETE|WS|WEBSOCKET)\s+([/][a-zA-Z0-9_\-\/{}]*)`?', line, re.IGNORECASE)
    for verb, path in matches:
        verb = verb.upper()
        if verb == "WEBSOCKET":
            verb = "WS"
        if path.startswith("/api/") or path in ["/health", "/health/detailed", "/health/error-test"]:
            doc_endpoints.append({
                "verb": verb,
                "path": path,
                "section": current_sec,
                "line": i + 1
            })

# Deduplicate doc endpoints preserving order
seen = set()
unique_doc = []
for d in doc_endpoints:
    k = (d["verb"], d["path"])
    if k not in seen:
        seen.add(k)
        unique_doc.append(d)

print(f"Total unique endpoints in API_DOCUMENTATION_COMPLETE.md: {len(unique_doc)}")

def normalize_path(p):
    return re.sub(r'\{[a-zA-Z0-9_]+\}', '{*}', p).rstrip('/')

app_map = {}
for ep in fastapi_endpoints:
    norm_p = normalize_path(ep["path"])
    app_map[(ep["verb"], norm_p)] = ep

matched = []
missing = []

for d in unique_doc:
    norm_p = normalize_path(d["path"])
    key = (d["verb"], norm_p)
    if key in app_map:
        matched.append((d, app_map[key]))
    else:
        # Check if exists with different verb
        other_verbs = [ep["verb"] for ep in fastapi_endpoints if normalize_path(ep["path"]) == norm_p]
        missing.append((d, other_verbs))

print("\n" + "="*80)
print(f"AUDIT SUMMARY: MATCHED {len(matched)} / {len(unique_doc)}")
print("="*80)

print(f"\n--- 1. MATCHED ENDPOINTS ({len(matched)}) ---")
for d, ep in matched:
    print(f"[OK] {d['verb']:<7} {d['path']:<50} | {ep['summary']}")

print(f"\n--- 2. MISSING OR MISMATCHED ENDPOINTS IN CODE ({len(missing)}) ---")
for d, other_verbs in missing:
    print(f"[MISSING] {d['verb']:<7} {d['path']:<50} | Line {d['line']:<4} | {d['section']}")
    if other_verbs:
        print(f"          -> But path exists with other verbs: {other_verbs}")

# Endpoints in FastAPI app but not in doc
doc_set = {(d["verb"], normalize_path(d["path"])) for d in unique_doc}
extra_in_app = []
for ep in fastapi_endpoints:
    norm_p = normalize_path(ep["path"])
    if (ep["verb"], norm_p) not in doc_set:
        if ep["path"] not in ["/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"]:
            extra_in_app.append(ep)

print(f"\n--- 3. ENDPOINTS IN FASTAPI APP NOT IN DOC ({len(extra_in_app)}) ---")
for ep in extra_in_app:
    print(f"[EXTRA]   {ep['verb']:<7} {ep['path']:<50} | {ep['summary']}")
