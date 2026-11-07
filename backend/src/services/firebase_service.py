"""
Firebase Admin SDK Connection Singleton
"""

import os
from pathlib import Path
from typing import Optional
import firebase_admin
from firebase_admin import credentials, firestore, storage

_firebase_app: Optional[firebase_admin.App] = None
_firestore_client = None
_storage_bucket = None


def init_firebase() -> firebase_admin.App:
    global _firebase_app, _firestore_client, _storage_bucket
    if _firebase_app is not None:
        if _firestore_client is None:
            try:
                _firestore_client = firestore.client(_firebase_app)
            except Exception:
                pass
        return _firebase_app

    try:
        _firebase_app = firebase_admin.get_app()
        if _firestore_client is None:
            try:
                _firestore_client = firestore.client(_firebase_app)
            except Exception:
                pass
        if _storage_bucket is None:
            try:
                _storage_bucket = storage.bucket(app=_firebase_app)
            except Exception:
                _storage_bucket = None
        return _firebase_app
    except ValueError:
        pass

    # Resolve credentials path
    cred_path = None
    gac_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if gac_path and Path(gac_path).exists():
        cred_path = Path(gac_path)
    else:
        cred_env_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        if cred_env_path and Path(cred_env_path).exists():
            cred_path = Path(cred_env_path)
        else:
            current_file = Path(__file__).resolve()
            candidates = [
                Path("./credentials/firebase-service-account.json"),
                Path("/app/credentials/firebase-service-account.json"),
                current_file.parents[2] / "credentials" / "firebase-service-account.json",
                current_file.parents[3] / "credentials" / "firebase-service-account.json",
                Path("/credentials/firebase-service-account.json"),
            ]
            for cand in candidates:
                if cand.exists():
                    cred_path = cand
                    break

    storage_bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "matpho-c7e77.firebasestorage.app")

    if cred_path and cred_path.exists():
        cred = credentials.Certificate(str(cred_path))
        _firebase_app = firebase_admin.initialize_app(cred, {
            "storageBucket": storage_bucket_name
        })
    else:
        # Running on Google Cloud Run or GCP environment with Application Default Credentials (ADC)
        _firebase_app = firebase_admin.initialize_app(options={
            "storageBucket": storage_bucket_name
        })
    _firestore_client = firestore.client()
    try:
        _storage_bucket = storage.bucket()
    except Exception:
        _storage_bucket = None

    return _firebase_app


def get_firestore_client():
    global _firestore_client
    if _firestore_client is None:
        init_firebase()
    if _firestore_client is None:
        try:
            _firestore_client = firestore.client()
        except Exception:
            pass
    return _firestore_client


def get_storage_bucket():
    global _storage_bucket
    if _storage_bucket is None:
        init_firebase()
    return _storage_bucket
