"""Serve LegiScan data from a session dataset instead of per-bill API calls.

LegiScan publishes one zip per legislative session (getDatasetList /
getDataset) holding every bill as a full getBill-shaped JSON file, every
roll call with each legislator's vote, and the session's legislators.
Shape verified 2026-09-25 against the FL 2026 datasets: bill/*.json ->
{"bill": {...amendments, history, votes, supplements, sponsors...}},
vote/*.json -> {"roll_call": {..., "votes": [{people_id, vote_text}]}},
people/*.json -> {"person": {...}}. It carries no documents (bill text,
amendment text, staff analyses), so those still need the API.

One dataset download is 2 calls (list + zip). Syncing the 2026 Regular
Session's ~1,900 bills per bill costs ~1,900 getBill plus one getRollCall
per roll call -- thousands of calls, against a free tier of 10,000/month
from 2026-10-01.

DatasetClient stands in for LegiScanClient in the existing sync code
(sync_state_bill_history, _build_people_by_id): anything the dataset
holds is answered locally, anything else (getSupplement, a bill from
another session) goes to a real client, created only if needed.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import zipfile

from app.pipeline.legiscan import LegiScanClient, LegiScanError

logger = logging.getLogger(__name__)


def fetch_session_dataset(client: LegiScanClient, state: str, session_name: str) -> bytes:
    """Download the dataset zip for `session_name` (2 API calls)."""
    listing = client._call("getDatasetList", state=state).get("datasetlist") or []
    match = [d for d in listing if d.get("session_name") == session_name]
    if not match:
        names = sorted({d.get("session_name") for d in listing})
        raise LegiScanError(f"No {state} dataset named {session_name!r}; available: {names}")
    entry = match[0]
    logger.info(
        "Downloading %s dataset %s (%s bytes, built %s)",
        state, session_name, entry.get("dataset_size"), entry.get("dataset_date"),
    )
    data = client._call("getDataset", id=str(entry["session_id"]), access_key=entry["access_key"])
    return base64.b64decode(data["dataset"]["zip"])


class DatasetClient:
    """The LegiScanClient methods the sync code uses, answered from a dataset."""

    def __init__(self, zip_bytes: bytes, *, fallback: LegiScanClient | None = None) -> None:
        self._fallback = fallback
        self.fallback_calls = 0
        self.bills: dict[int, dict] = {}
        self.roll_calls: dict[int, dict] = {}
        self.people: list[dict] = []
        session_ids: set[int] = set()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for name in z.namelist():
                if not name.endswith(".json"):
                    continue
                folder = name.rsplit("/", 2)[-2]
                doc = json.loads(z.read(name))
                if folder == "bill":
                    bill = doc["bill"]
                    self.bills[int(bill["bill_id"])] = bill
                    session_id = (bill.get("session") or {}).get("session_id") or bill.get("session_id")
                    if session_id:
                        session_ids.add(int(session_id))
                elif folder == "vote":
                    roll_call = doc["roll_call"]
                    self.roll_calls[int(roll_call["roll_call_id"])] = roll_call
                elif folder == "people":
                    self.people.append(doc["person"])
        self.session_ids = sorted(session_ids)

    def _real(self) -> LegiScanClient:
        if self._fallback is None:
            self._fallback = LegiScanClient()
        self.fallback_calls += 1
        return self._fallback

    def get_bill(self, bill_id: int) -> dict:
        bill = self.bills.get(int(bill_id))
        return bill if bill is not None else self._real().get_bill(bill_id)

    def get_roll_call(self, roll_call_id: int) -> dict:
        roll_call = self.roll_calls.get(int(roll_call_id))
        return roll_call if roll_call is not None else self._real().get_roll_call(roll_call_id)

    def get_sessions(self, state: str) -> list[dict]:
        return [{"session_id": s} for s in self.session_ids]

    def get_session_people(self, session_id: int) -> list[dict]:
        return self.people

    def get_supplement(self, supplement_id: int) -> dict:
        return self._real().get_supplement(supplement_id)
