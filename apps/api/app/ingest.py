"""CLI: publish picks / graded results from the ML pipeline's CSV files.

  python -m app.ingest picks   ../../../predictions/latest_picks.csv      # direct DB write (operators)
  python -m app.ingest results ../../../predictions/graded.csv
  python -m app.ingest picks latest_picks.csv --url https://api.example.com   # signed HTTP push

With --url the rows are sent to /internal/ingest/* signed with INGEST_HMAC_SECRET (what the Modal
pipeline does). Rows already published are skipped; published rows are never changed.
"""
import argparse
import asyncio
import csv
import json
import math
import sys
import time

import httpx

from app.core.config import get_settings
from app.core.security import sign_payload
from app.db.session import get_sessionmaker
from app.schemas import IngestPick, IngestResult
from app.services import ingest

PICK_FIELDS = set(IngestPick.model_fields)
RESULT_FIELDS = set(IngestResult.model_fields)


def _clean(row: dict, fields: set) -> dict:
    out = {}
    for k, v in row.items():
        if k not in fields:
            continue
        if v in ("", "nan", "NaN", None):
            continue
        out[k] = v
    return out


def read_rows(kind: str, path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fields = PICK_FIELDS if kind == "picks" else RESULT_FIELDS
    out = []
    for r in rows:
        c = _clean(r, fields)
        if kind == "results" and "correct" in c:
            c["correct"] = str(c["correct"]).lower() == "true"
        if kind == "picks" and "odds_used" in c and (not c["odds_used"] or math.isnan(float(c["odds_used"]))):
            c.pop("odds_used")
        out.append(c)
    return out


def push(kind: str, rows: list[dict], url: str) -> dict:
    body = json.dumps({kind: rows}).encode()
    ts = str(int(time.time()))
    sig = sign_payload(get_settings().ingest_hmac_secret.get_secret_value(), ts, body)
    r = httpx.post(f"{url.rstrip('/')}/internal/ingest/{kind}", content=body, timeout=60,
                   headers={"content-type": "application/json", "x-ap-timestamp": ts, "x-ap-signature": sig})
    r.raise_for_status()
    return r.json()


async def write_direct(kind: str, rows: list[dict]) -> tuple[int, int]:
    async with get_sessionmaker()() as db:
        if kind == "picks":
            return await ingest.ingest_picks(db, [IngestPick(**r) for r in rows])
        return await ingest.ingest_results(db, [IngestResult(**r) for r in rows])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["picks", "results"])
    ap.add_argument("csv")
    ap.add_argument("--url", default=None, help="API base URL for a signed HTTP push")
    args = ap.parse_args()
    rows = read_rows(args.kind, args.csv)
    if not rows:
        print("no rows")
        return 0
    if args.url:
        print(push(args.kind, rows, args.url))
    else:
        new, skipped = asyncio.run(write_direct(args.kind, rows))
        print(f"received {len(rows)}, inserted {new}, skipped (already published) {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
