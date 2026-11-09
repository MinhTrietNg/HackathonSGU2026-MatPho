#!/usr/bin/env python3
"""
Wipe Firestore + Firebase Storage to an empty state before a demo (no seeding).

Dry-run by default: only counts what would be deleted. Pass --yes to delete.

    python scripts/clean_db.py          # count only
    python scripts/clean_db.py --yes    # delete for real

Kept on purpose:
  - edge_nodes: public HLS URL of the Edge node, used when Redis is empty.
  - _health:    health-check ping doc.
"""

import argparse
import os
import sys
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore, storage

BACKEND_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = Path(
    os.getenv("FIREBASE_CREDENTIALS_PATH", BACKEND_DIR / "credentials" / "firebase-service-account.json")
)
BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET", "matpho-c7e77.firebasestorage.app")

KEEP_COLLECTIONS = {"edge_nodes", "_health"}
STORAGE_PREFIXES = ["fire_alerts/", "cameras/"]


def count_docs(ref) -> int:
    """Count docs in a collection, including all nested subcollections."""
    total = 0
    for doc in ref.list_documents():
        if doc.get().exists:
            total += 1
        for sub in doc.collections():
            total += count_docs(sub)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Wipe Firestore + Storage for demo.")
    parser.add_argument("--yes", action="store_true", help="actually delete (default: dry-run)")
    args = parser.parse_args()

    if not CREDENTIALS_PATH.exists():
        print(f"❌ Không thấy service account: {CREDENTIALS_PATH}")
        sys.exit(1)

    firebase_admin.initialize_app(
        credentials.Certificate(str(CREDENTIALS_PATH)),
        {"storageBucket": BUCKET_NAME},
    )
    db = firestore.client()
    bucket = storage.bucket()
    mode = "XOÁ THẬT" if args.yes else "DRY-RUN (chỉ đếm)"
    print(f"🔥 Project: {db.project} · Bucket: {BUCKET_NAME} · Chế độ: {mode}\n")

    # Firestore: every root collection except the keep-list, subcollections included.
    print("[Firestore]")
    for col in db.collections():
        if col.id in KEEP_COLLECTIONS:
            print(f"  ⏭️  Giữ lại [{col.id}]")
            continue
        n = count_docs(col)
        if args.yes:
            db.recursive_delete(col)
        print(f"  {'🗑️ ' if args.yes else '•'} [{col.id}]: {n} doc (kể cả subcollection)")

    # Storage: uploaded alert images and camera thumbnails.
    print("\n[Storage]")
    for prefix in STORAGE_PREFIXES:
        blobs = list(bucket.list_blobs(prefix=prefix))
        if args.yes and blobs:
            bucket.delete_blobs(blobs)
        print(f"  {'🗑️ ' if args.yes else '•'} {prefix}: {len(blobs)} file")

    if args.yes:
        print("\n✅ Đã dọn xong. Nhớ: đăng xuất app trên máy demo, đăng ký lại, restart backend.")
    else:
        print("\nℹ️  Chưa xoá gì. Chạy lại với --yes để xoá thật.")


if __name__ == "__main__":
    main()
