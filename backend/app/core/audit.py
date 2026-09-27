"""Central audit logging helpers."""
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AuditLog

async def audit(
    db: AsyncSession,
    actor_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    ))
