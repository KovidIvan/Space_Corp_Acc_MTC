"""Shared request dependencies for authenticated dashboard endpoints."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Owner


def require_owner(request: Request, db: Annotated[Session, Depends(get_db)]) -> Owner:
    """Resolve the signed-in local owner or reject the request."""
    if "session" not in request.scope:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Dashboard is not configured")

    owner_id = request.session.get("owner_id")
    owner = db.get(Owner, owner_id) if owner_id else None
    if owner is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return owner
