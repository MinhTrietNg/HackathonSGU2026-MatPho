import sys
import os
import re

# Add /app to sys.path
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

from src.main import app

# Extract FastAPI routes
fastapi_routes = []
for route in app.routes:
    methods = getattr(route, "methods", None)
    path = getattr(route, "path", None)
    name = getattr(route, "name", None)
    endpoint = getattr(route, "endpoint", None)
    
    if hasattr(route, "path") and not methods:
        fastapi_routes.append({
            "verb": "WS",
            "path": route.path,
            "name": name,
            "func": f"{endpoint.__module__}.{endpoint.__name__}" if endpoint else ""
        })
    elif methods:
        for m in methods:
            if m in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                fastapi_routes.append({
                    "verb": m,
                    "path": path,
                    "name": name,
                    "func": f"{endpoint.__module__}.{endpoint.__name__}" if endpoint else ""
                })

print(f"Total routes registered in FastAPI app: {len(fastapi_routes)}")

# Read API Doc from /app/API_DOCUMENTATION_COMPLETE.md or host
doc_path = "/app/API_DOCUMENTATION_COMPLETE.md"
if not os.path.exists(doc_path):
    print(f"File {doc_path} not found")
    sys.exit(1)

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

# Remove duplicate doc entries
seen = set()
unique_doc = []
for d in doc_endpoints:
    k = (d["verb"], d["path"])
    if k not in seen:
        seen.add(k)
        unique_doc.append(d)

print(f"Total unique endpoints in documentation: {len(unique_doc)}")

def normalize_path(p):
    return re.sub(r'\{[a-zA-Z0-9_]+\}', '{*}', p).rstrip('/')

app_route_map = {}
for r in fastapi_routes:
    norm_p = normalize_path(r["path"])
    key = (r["verb"], norm_p)
    app_route_map[key] = r

matched = []
missing_in_code = []

for d in unique_doc:
    norm_doc_p = normalize_path(d["path"])
    key = (d["verb"], norm_doc_p)
    if key in app_route_map:
        matched.append((d, app_route_map[key]))
    else:
        other_verbs = [r["verb"] for r in fastapi_routes if normalize_path(r["path"]) == norm_doc_p]
        missing_in_code.append((d, other_verbs))

print("\n" + "="*80)
print(f"MATCHED ENDPOINTS: {len(matched)} / {len(unique_doc)}")
print("="*80)
for d, r in matched:
    print(f"[OK] {d['verb']:<7} {d['path']:<45} -> {r['func']}")

print("\n" + "="*80)
print(f"MISSING OR MISMATCHED IN CODE: {len(missing_in_code)}")
print("="*80)
for d, other_verbs in missing_in_code:
    print(f"[MISSING] {d['verb']:<7} {d['path']:<45} (Doc Line {d['line']}: {d['section']})")
    if other_verbs:
        print(f"          -> Found with different verbs in code: {other_verbs}")

doc_route_map = {(d["verb"], normalize_path(d["path"])): d for d in unique_doc}
unmatched_in_doc = []
for r in fastapi_routes:
    norm_app_p = normalize_path(r["path"])
    if (r["verb"], norm_app_p) not in doc_route_map:
        if r["path"] not in ["/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"]:
            unmatched_in_doc.append(r)

print("\n" + "="*80)
print(f"ROUTES IN CODE BUT NOT IN DOC: {len(unmatched_in_doc)}")
print("="*80)
for r in unmatched_in_doc:
    print(f"[EXTRA]   {r['verb']:<7} {r['path']:<45} -> {r['func']}")
