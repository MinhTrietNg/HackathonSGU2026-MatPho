"""
Base Firestore Repository for Mắt Phố Backend
Encapsulates common database interactions, transactions, and data mappings.
"""

import logging
from typing import Optional, Dict, Any, List
from google.cloud import firestore
from ..firebase_service import get_firestore_client
from ...core.formatters import parse_iso_utc, format_iso_utc

logger = logging.getLogger("backend.repository.base")


class BaseFirestoreRepository:
    COLLECTION_NAME = ""

    def __init__(self):
        self._db = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_firestore_client()
        return self._db

    @property
    def collection(self):
        return self.db.collection(self.COLLECTION_NAME)

    def get_document(
        self, collection_path: str, doc_id: str, transaction: Optional[firestore.Transaction] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve document snapshot as dictionary."""
        doc_ref = self.db.collection(collection_path).document(doc_id)
        if transaction:
            snapshot = doc_ref.get(transaction=transaction)
        else:
            snapshot = doc_ref.get()

        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        data["id"] = snapshot.id
        return data

    def set_document(
        self,
        collection_path: str,
        doc_id: str,
        data: Dict[str, Any],
        merge: bool = True,
        transaction: Optional[firestore.Transaction] = None,
    ) -> None:
        """Write or overwrite document."""
        doc_ref = self.db.collection(collection_path).document(doc_id)
        if transaction:
            transaction.set(doc_ref, data, merge=merge)
        else:
            doc_ref.set(data, merge=merge)

    def update_document(
        self,
        collection_path: str,
        doc_id: str,
        data: Dict[str, Any],
        transaction: Optional[firestore.Transaction] = None,
    ) -> None:
        """Update specific fields of a document."""
        doc_ref = self.db.collection(collection_path).document(doc_id)
        if transaction:
            transaction.update(doc_ref, data)
        else:
            doc_ref.update(data)

    def delete_document(
        self, collection_path: str, doc_id: str, transaction: Optional[firestore.Transaction] = None
    ) -> None:
        """Delete a document."""
        doc_ref = self.db.collection(collection_path).document(doc_id)
        if transaction:
            transaction.delete(doc_ref)
        else:
            doc_ref.delete()


# Alias for backward compatibility
BaseRepository = BaseFirestoreRepository

