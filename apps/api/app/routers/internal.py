"""Ingest endpoints for the ML pipeline. HMAC-SHA256 over "<timestamp>.<raw body>", 5-minute window,
each signature accepted once (replay protection). Not routed by the public ingress."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.core.security import verify_signed_payload
from app.db.session import get_db
from app.schemas import IngestOut, IngestPicksIn, IngestResultsIn
from app.services import ingest

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


async def verify_signature(request: Request, x_ap_timestamp: str = Header(default=""),
                           x_ap_signature: str = Header(default="")) -> None:
    s = get_settings()
    body = await request.body()
    if not verify_signed_payload(s.ingest_hmac_secret.get_secret_value(), x_ap_timestamp, body, x_ap_signature,
                                 s.ingest_max_skew_seconds):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    first = await get_redis().set(f"ingest:sig:{x_ap_signature}", "1", ex=s.ingest_max_skew_seconds * 2, nx=True)
    if not first:
        raise HTTPException(status.HTTP_409_CONFLICT, "Replayed request")


@router.post("/ingest/picks", response_model=IngestOut, dependencies=[Depends(verify_signature)])
async def ingest_picks(body: IngestPicksIn, db: AsyncSession = Depends(get_db)) -> IngestOut:
    new, skipped = await ingest.ingest_picks(db, body.picks)
    return IngestOut(received=len(body.picks), inserted=new, skipped_existing=skipped)


@router.post("/ingest/results", response_model=IngestOut, dependencies=[Depends(verify_signature)])
async def ingest_results(body: IngestResultsIn, db: AsyncSession = Depends(get_db)) -> IngestOut:
    new, skipped = await ingest.ingest_results(db, body.results)
    return IngestOut(received=len(body.results), inserted=new, skipped_existing=skipped)
