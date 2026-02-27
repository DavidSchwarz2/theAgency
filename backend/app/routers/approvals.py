"""REST API router for approval management."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Approval, ApprovalStatus
from app.schemas.pipeline import ApprovalResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    db: Annotated[AsyncSession, Depends(get_db)],
    include_all: bool = False,
) -> list[ApprovalResponse]:
    """List approvals. By default returns only pending approvals.

    Pass `?include_all=true` to return all approvals regardless of status.
    """
    stmt = select(Approval).options(selectinload(Approval.step))
    if not include_all:
        stmt = stmt.where(Approval.status == ApprovalStatus.pending)

    result = await db.execute(stmt)
    approvals = result.scalars().all()

    return [
        ApprovalResponse(
            id=a.id,
            pipeline_id=a.step.pipeline_id,
            step_id=a.step_id,
            status=a.status,
            comment=a.comment,
            decided_by=a.decided_by,
            decided_at=a.decided_at,
        )
        for a in approvals
    ]
