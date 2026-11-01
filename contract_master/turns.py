"""One coordinator turn at a time, whether Orca scheduled it or a person started it.

Orca does not serialize automation runs and marks a manually started run completed
while its session is still working, so run status cannot fence turns. Each turn
holds this lease from start to end; a lease left by a crashed turn expires.
"""
import secrets
import time
from datetime import datetime, timezone
from .contracts import ContractError

DEFAULT_MINUTES = 60


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds")


class TurnLease:
    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock

    def _current(self, db):
        return db.execute("SELECT lease, expires FROM turn_lease WHERE id=1").fetchone()

    def start(self, minutes=DEFAULT_MINUTES):
        now = self.clock()
        with self.store.transaction() as db:
            row = self._current(db)
            if row and row["expires"] > now:
                raise ContractError("Another coordinator turn holds the lease until " + iso(row["expires"]))
            lease = secrets.token_hex(12)
            db.execute("INSERT OR REPLACE INTO turn_lease VALUES(1,?,?)", (lease, now + minutes * 60))
        return {"lease": lease, "expires": iso(now + minutes * 60)}

    def renew(self, lease, minutes=DEFAULT_MINUTES):
        now = self.clock()
        with self.store.transaction() as db:
            row = self._current(db)
            # An expired lease nobody took over is still ours; a replaced one is not.
            if not row or row["lease"] != lease:
                raise ContractError("Turn lease lost; stop this turn without further writes")
            db.execute("UPDATE turn_lease SET expires=? WHERE id=1", (now + minutes * 60,))
        return {"lease": lease, "expires": iso(now + minutes * 60)}

    def require(self, db, lease):
        """Fence a write inside the caller's open transaction; never opens its own."""
        row = self._current(db)
        if not row or row["lease"] != lease or row["expires"] <= self.clock():
            raise ContractError("Turn lease lost or not held; stop without writes")

    def end(self, lease):
        with self.store.transaction() as db:
            released = db.execute("DELETE FROM turn_lease WHERE id=1 AND lease=?", (lease,)).rowcount
        return {"released": bool(released)}

    def check(self):
        """Raise while a live lease exists, so the automation precheck exits non-zero."""
        with self.store.transaction() as db:
            row = self._current(db)
        if row and row["expires"] > self.clock():
            raise ContractError("Coordinator turn in progress until " + iso(row["expires"]))
        return {"free": True}
