from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import client_ip
from app.models import AuditLog


async def audit(db: AsyncSession, action: str, request: Request | None = None, user_id: UUID | None = None,
                **detail) -> None:
    """Add an audit row to the current transaction (the caller commits). Never pass secrets in detail."""
    db.add(AuditLog(user_id=user_id, action=action, ip=client_ip(request) if request else "", detail=detail))
