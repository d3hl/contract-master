"""Ordered, single-flight updates. Ambiguous delivery never causes a blind resend."""
import json
from .store import Store


class BeforeSendError(ConnectionError):
    """Transport guarantees the remote write was never attempted."""


def error_receipt(exc):
    return json.dumps({"error": str(exc), "type": type(exc).__name__})


class Outbox:
    def __init__(self, store):
        self.store = store

    def flush_one(self, transport):
        # Commit 'sending' before network I/O so a crash cannot become a fresh send.
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM outbox WHERE status!='delivered' ORDER BY sequence LIMIT 1").fetchone()
            if not row:
                return "empty"
            entry = dict(row)
            if entry["status"] == "pending":
                db.execute("UPDATE outbox SET status='sending' WHERE sequence=?", (entry["sequence"],))
        if entry["status"] != "pending":
            receipt = transport.lookup(entry)
            if receipt is None:
                return "uncertain"  # blocks later writes; preserve identity and operator recovery
        else:
            try:
                receipt = transport.send(entry)
            except BeforeSendError as exc:
                with self.store.transaction() as db:
                    db.execute("UPDATE outbox SET status='pending',receipt=? WHERE sequence=?",
                               (error_receipt(exc), entry["sequence"]))
                return "offline"
            except Exception as exc:
                with self.store.transaction() as db:
                    db.execute("UPDATE outbox SET receipt=? WHERE sequence=? AND status!='delivered'",
                               (error_receipt(exc), entry["sequence"]))
                return "uncertain"
        with self.store.transaction() as db:
            db.execute("UPDATE outbox SET status='delivered',receipt=? WHERE sequence=?",
                       (json.dumps(receipt), entry["sequence"]))
        return "delivered"

    def enqueue(self, key, issue, payload):
        with self.store.transaction() as db:
            Store.enqueue(db, key, issue, payload)
