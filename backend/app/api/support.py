"""In-app privacy, security, technical support and contact ticketing."""

# This file manages the support and contact system available inside MediExplain+.
# Logged-in users can create tickets for privacy, security, technical or general
# support issues and can view the tickets they have submitted. Each new request
# stores the relevant contact and urgency information and is also added to the
# audit trail. Administrators have a separate endpoint for reviewing all submitted
# tickets, while normal users remain limited to their own support history.

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.core.audit import audit
from app.core.database import get_db
from app.core.security import (
    get_current_user,
    require_role,
)
from app.models import (
    SupportTicket,
    User,
    UserRole,
)
from app.schemas import (
    SupportTicketCreate,
    SupportTicketPublic,
)


router = APIRouter(
    prefix="/api/support",
    tags=["support"],
)


@router.post(
    "/tickets",
    response_model=SupportTicketPublic,
    status_code=201,
)
async def create_ticket(
    body: SupportTicketCreate,
    db: AsyncSession = Depends(
        get_db
    ),
    user: User = Depends(
        get_current_user
    ),
):
    privacy_type = (
        body.privacy_request_type
        if body.category == "contact"
        else None
    )

    ticket = SupportTicket(
        reporter_id=user.id,
        category=body.category,
        subject=body.subject,
        message=body.message,
        contact_email=str(
            body.contact_email
            or user.email
        ),
        urgency=body.urgency,
        privacy_request_type=(
            privacy_type
        ),
    )

    db.add(ticket)
    await db.flush()

    await audit(
        db,
        user.id,
        "support.ticket_created",
        "support_ticket",
        ticket.id,
        {
            "category":
                ticket.category,
            "urgency":
                ticket.urgency,
            "privacy_request_type":
                ticket
                .privacy_request_type,
        },
    )

    return ticket


@router.get(
    "/mine",
    response_model=list[
        SupportTicketPublic
    ],
)
async def my_tickets(
    db: AsyncSession = Depends(
        get_db
    ),
    user: User = Depends(
        get_current_user
    ),
):
    rows = await db.execute(
        select(
            SupportTicket
        )
        .where(
            SupportTicket.reporter_id
            == user.id
        )
        .order_by(
            SupportTicket
            .created_at
            .desc()
        )
    )

    return list(
        rows.scalars()
    )


@router.get(
    "/all",
    response_model=list[
        SupportTicketPublic
    ],
)
async def all_tickets(
    db: AsyncSession = Depends(
        get_db
    ),
    _: User = Depends(
        require_role(
            UserRole.ADMIN
        )
    ),
):
    rows = await db.execute(
        select(
            SupportTicket
        ).order_by(
            SupportTicket
            .created_at
            .desc()
        )
    )

    return list(
        rows.scalars()
    )
